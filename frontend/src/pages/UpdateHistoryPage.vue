<template>
  <q-page class="search-container">
    <div class="q-pa-md">
      <!-- Summary tiles -->
      <div class="row q-col-gutter-md q-mb-md">
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered :class="schedule.scheduled ? 'bg-blue-1' : 'bg-orange-1'">
            <q-card-section>
              <div class="text-caption text-grey-7">Next scheduled run</div>
              <div class="text-h6">{{ schedule.next_run || 'Not scheduled' }}</div>
              <div class="text-caption text-grey-7">
                <template v-if="schedule.scheduled">
                  daily at {{ schedule.time_of_day }} {{ schedule.timezone }} · in {{ countdown }}
                </template>
                <template v-else>No cron entry found</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-caption text-grey-7">Last run</div>
              <div class="text-h6">{{ lastRun ? lastRun.started_at : '—' }}</div>
              <div v-if="lastRun" class="text-caption" :class="lastRun.success ? 'text-green' : 'text-red'">
                {{ lastRun.success ? 'Succeeded' : 'Failed' }} · {{ lastRun.triggered_by }}
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-caption text-grey-7">Runs recorded</div>
              <div class="text-h6">{{ runs.length }}</div>
              <div class="text-caption text-grey-7">{{ failureCount }} failed</div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-caption text-grey-7">Avg duration</div>
              <div class="text-h6">{{ avgDuration }}</div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <q-card>
        <q-card-section class="row items-center justify-between">
          <div>
            <div class="text-h6">Daily Update History</div>
            <div class="text-subtitle2 text-grey-7">
              Every trigger of /api/download/daily, scheduled or manual
            </div>
          </div>
          <q-btn
            color="primary"
            icon="refresh"
            label="Refresh"
            :loading="loading"
            @click="loadHistory"
          />
        </q-card-section>

        <q-card-section>
          <q-table
            :rows="runs"
            :columns="columns"
            row-key="id"
            :loading="loading"
            :pagination="{ rowsPerPage: 20, sortBy: 'started_at', descending: true }"
            no-data-label="No runs recorded yet"
          >
            <template v-slot:body-cell-success="props">
              <q-td :props="props">
                <q-chip
                  dense
                  :color="props.value ? 'green' : 'red'"
                  text-color="white"
                  :label="props.value ? 'Success' : 'Failed'"
                />
              </q-td>
            </template>

            <template v-slot:body-cell-triggered_by="props">
              <q-td :props="props">
                <q-chip
                  dense
                  outline
                  :color="props.value === 'cron' ? 'primary' : 'grey-8'"
                  :icon="props.value === 'cron' ? 'schedule' : 'touch_app'"
                  :label="props.value"
                />
              </q-td>
            </template>

            <template v-slot:body-cell-files_downloaded="props">
              <q-td :props="props">
                {{ props.row.files_downloaded }} / {{ props.row.files_expected }}
              </q-td>
            </template>

            <template v-slot:body-cell-bytes_freed="props">
              <q-td :props="props">{{ formatBytes(props.value) }}</q-td>
            </template>

            <template v-slot:body-cell-message="props">
              <q-td :props="props">
                <div class="message-cell">{{ props.value }}</div>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>

      <!-- Raw cron log -->
      <q-card class="q-mt-md">
        <q-card-section class="row items-center justify-between">
          <div>
            <div class="text-h6">Cron Log</div>
            <div class="text-subtitle2 text-grey-7">
              {{ logPath || 'daily_update.log' }}
              <span v-if="logMeta.exists">
                · {{ formatBytes(logMeta.size) }} · updated {{ logMeta.modified }}
              </span>
            </div>
          </div>
          <div class="row items-center q-gutter-sm">
            <q-select
              v-model="logLines"
              :options="[100, 200, 500, 1000, 2000]"
              dense
              outlined
              style="min-width: 110px"
              label="Lines"
              @update:model-value="loadLog"
            />
            <q-btn
              color="primary"
              icon="refresh"
              label="Refresh"
              :loading="logLoading"
              @click="loadLog"
            />
          </div>
        </q-card-section>

        <q-card-section>
          <q-banner v-if="!logMeta.exists" dense class="bg-grey-2">
            <template v-slot:avatar><q-icon name="info" color="grey-7" /></template>
            {{ logMeta.message || 'No log yet.' }}
          </q-banner>
          <pre v-else class="log-view">{{ logContent }}</pre>
        </q-card-section>
      </q-card>
    </div>
  </q-page>
</template>

<script>
import { defineComponent, ref, computed, onMounted } from 'vue'
import { useQuasar } from 'quasar'
import { api } from 'boot/axios'

export default defineComponent({
  name: 'UpdateHistoryPage',

  setup () {
    const $q = useQuasar()
    const runs = ref([])
    const loading = ref(false)
    const logContent = ref('')
    const logMeta = ref({ exists: false, message: '' })
    const logPath = ref('')
    const logLines = ref(200)
    const logLoading = ref(false)
    const schedule = ref({ scheduled: false, next_run: null, time_of_day: '', timezone: '' })

    const columns = [
      { name: 'started_at', label: 'Started', field: 'started_at', align: 'left', sortable: true },
      { name: 'success', label: 'Result', field: 'success', align: 'center', sortable: true },
      { name: 'triggered_by', label: 'Trigger', field: 'triggered_by', align: 'center', sortable: true },
      { name: 'duration_seconds', label: 'Duration (s)', field: 'duration_seconds', align: 'right', sortable: true },
      { name: 'files_downloaded', label: 'Downloaded', field: 'files_downloaded', align: 'center' },
      { name: 'files_parsed', label: 'Parsed', field: 'files_parsed', align: 'center', sortable: true },
      { name: 'files_pruned', label: 'Pruned', field: 'files_pruned', align: 'center', sortable: true },
      { name: 'bytes_freed', label: 'Freed', field: 'bytes_freed', align: 'right', sortable: true },
      { name: 'message', label: 'Message', field: 'message', align: 'left' }
    ]

    const formatBytes = (bytes) => {
      if (!bytes) return '—'
      const units = ['B', 'KB', 'MB', 'GB']
      let value = bytes
      let unit = 0
      while (value >= 1024 && unit < units.length - 1) {
        value /= 1024
        unit++
      }
      return `${value.toFixed(1)} ${units[unit]}`
    }

    const lastRun = computed(() => runs.value[0] || null)
    const failureCount = computed(() => runs.value.filter(r => !r.success).length)

    const avgDuration = computed(() => {
      const timed = runs.value.filter(r => r.duration_seconds)
      if (!timed.length) return '—'
      const mean = timed.reduce((sum, r) => sum + r.duration_seconds, 0) / timed.length
      return `${mean.toFixed(1)} s`
    })

    const countdown = computed(() => {
      const secs = schedule.value.seconds_until
      if (!secs && secs !== 0) return '—'
      const h = Math.floor(secs / 3600)
      const m = Math.floor((secs % 3600) / 60)
      return h > 0 ? `${h}h ${m}m` : `${m}m`
    })

    const totalFreed = computed(() =>
      formatBytes(runs.value.reduce((sum, r) => sum + (r.bytes_freed || 0), 0))
    )

    const loadHistory = async () => {
      loading.value = true
      try {
        const response = await api.get('/download/history', { params: { limit: 200 } })
        if (response.data.success) {
          runs.value = response.data.runs
          if (response.data.schedule) {
            schedule.value = response.data.schedule
          }
        }
      } catch (error) {
        $q.notify({
          type: 'negative',
          message: 'Failed to load update history: ' +
            (error.response?.data?.message || error.message),
          timeout: 5000
        })
      } finally {
        loading.value = false
      }
    }

    const loadLog = async () => {
      logLoading.value = true
      try {
        const response = await api.get('/download/log', { params: { lines: logLines.value } })
        if (response.data.success) {
          logContent.value = response.data.content
          logPath.value = response.data.path
          logMeta.value = response.data
        }
      } catch (error) {
        $q.notify({
          type: 'negative',
          message: 'Failed to load cron log: ' +
            (error.response?.data?.message || error.message),
          timeout: 5000
        })
      } finally {
        logLoading.value = false
      }
    }

    const refreshAll = () => {
      loadHistory()
      loadLog()
    }

    onMounted(refreshAll)

    return {
      runs,
      loading,
      columns,
      lastRun,
      failureCount,
      avgDuration,
      totalFreed,
      schedule,
      countdown,
      formatBytes,
      loadHistory,
      logContent,
      logMeta,
      logPath,
      logLines,
      logLoading,
      loadLog,
      refreshAll
    }
  }
})
</script>

<style scoped>
.log-view {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  max-height: 480px;
  overflow: auto;
  font-family: 'Roboto Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre;
  margin: 0;
}

.message-cell {
  max-width: 420px;
  white-space: normal;
  word-break: break-word;
}
</style>
