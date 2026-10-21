<template>
  <q-page class="search-container">
    <div class="q-pa-md">
      <q-card>
        <q-card-section>
          <div class="text-h6">Search History</div>
          <div class="text-subtitle2 text-grey-7">
            Recent IP address searches and their results
          </div>
        </q-card-section>

        <q-card-section>
          <q-table
            :rows="searchHistory"
            :columns="columns"
            row-key="id"
            :loading="loading"
            class="history-table"
            :pagination="{ rowsPerPage: 20 }"
          >
            <template v-slot:body-cell-ip_address="props">
              <q-td :props="props">
                <q-chip 
                  dense 
                  color="primary" 
                  text-color="white"
                  clickable
                  @click="searchAgain(props.value)"
                >
                  {{ props.value }}
                </q-chip>
              </q-td>
            </template>

            <template v-slot:body-cell-results_found="props">
              <q-td :props="props">
                <q-icon 
                  :name="props.value ? 'check_circle' : 'cancel'"
                  :color="props.value ? 'green' : 'red'"
                  size="sm"
                />
              </q-td>
            </template>

            <template v-slot:body-cell-matches="props">
              <q-td :props="props">
                <div class="q-gutter-xs">
                  <q-chip 
                    dense 
                    color="blue" 
                    text-color="white" 
                    size="sm"
                    v-if="props.row.ltm_matches > 0"
                  >
                    LTM: {{ props.row.ltm_matches }}
                  </q-chip>
                  <q-chip 
                    dense 
                    color="orange" 
                    text-color="white" 
                    size="sm"
                    v-if="props.row.firewall_matches > 0"
                  >
                    FW: {{ props.row.firewall_matches }}
                  </q-chip>
                </div>
              </q-td>
            </template>

            <template v-slot:body-cell-actions="props">
              <q-td :props="props">
                <q-btn
                  flat
                  round
                  color="primary"
                  icon="search"
                  size="sm"
                  @click="searchAgain(props.row.ip_address)"
                >
                  <q-tooltip>Search Again</q-tooltip>
                </q-btn>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>
  </q-page>
</template>

<script>
import { defineComponent, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from 'boot/axios'
import { Notify } from 'quasar'

export default defineComponent({
  name: 'HistoryPage',

  setup () {
    const router = useRouter()
    const searchHistory = ref([])
    const loading = ref(false)

    const columns = [
      {
        name: 'ip_address',
        required: true,
        label: 'IP Address',
        align: 'left',
        field: 'ip_address',
        sortable: true
      },
      {
        name: 'search_date',
        label: 'Search Date',
        align: 'left',
        field: 'search_date',
        sortable: true,
        format: (val) => {
          return new Date(val).toLocaleString()
        }
      },
      {
        name: 'results_found',
        label: 'Results Found',
        align: 'center',
        field: 'results_found',
        sortable: true
      },
      {
        name: 'matches',
        label: 'Matches',
        align: 'left',
        field: row => `${row.ltm_matches + row.firewall_matches}`,
        sortable: true
      },
      {
        name: 'actions',
        label: 'Actions',
        align: 'center',
        field: 'actions'
      }
    ]

    const loadHistory = async () => {
      loading.value = true
      try {
        const response = await api.get('/search/history', {
          params: { limit: 50 }
        })

        if (response.data.success) {
          searchHistory.value = response.data.history
        }
      } catch (error) {
        Notify.create({
          type: 'negative',
          message: 'Failed to load search history: ' + (error.response?.data?.message || error.message),
          timeout: 5000
        })
      } finally {
        loading.value = false
      }
    }

    const searchAgain = (ipAddress) => {
      // Navigate to search page with the IP pre-filled
      router.push({ 
        path: '/', 
        query: { ip: ipAddress }
      })
    }

    onMounted(() => {
      loadHistory()
    })

    return {
      searchHistory,
      loading,
      columns,
      searchAgain
    }
  }
})
</script>