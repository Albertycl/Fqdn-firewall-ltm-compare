<template>
  <q-layout view="lHh Lpr lFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" @click="toggleLeftDrawer" />

        <q-toolbar-title>
          Network Configuration Portal
        </q-toolbar-title>

      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" bordered class="bg-grey-1">
      <q-list>
        <q-item clickable v-ripple to="/" exact>
          <q-item-section avatar><q-icon name="search" /></q-item-section>
          <q-item-section>Search</q-item-section>
        </q-item>
        <q-item clickable v-ripple to="/update-history">
          <q-item-section avatar><q-icon name="update" /></q-item-section>
          <q-item-section>Daily Update History</q-item-section>
        </q-item>

        <q-separator class="q-my-sm" />

        <q-item-label header class="flex items-center justify-between">
          <span>Parsed Configuration Files</span>
          <q-btn 
            flat 
            dense 
            round 
            size="sm" 
            :icon="allExpanded ? 'unfold_less' : 'unfold_more'"
            :title="allExpanded ? 'Collapse All' : 'Expand All'"
            @click="toggleAllGroups"
            class="text-primary"
          />
        </q-item-label>

        <div v-if="parsedFiles.length === 0" class="q-pa-md text-center">
          <q-icon name="info" size="24px" color="grey-5" />
          <div class="text-grey-7 q-mt-sm">No files parsed yet</div>
        </div>

        <!-- New Server Section Header -->
        <q-separator v-if="newServerFiles.length > 0" class="q-my-sm" />
        <q-item-label v-if="newServerFiles.length > 0" header class="text-positive">
          <q-icon name="cloud_done" size="sm" class="q-mr-sm" />
          Downloaded - {{ newServerFiles.length }} configs
        </q-item-label>

        <!-- Alpha Group -->
        <q-expansion-item
          v-if="alphaFiles.length > 0"
          v-model="alphaExpanded"
          icon="layers"
          label="Alpha"
          header-class="text-teal"
          class="config-group"
        >
          <q-item v-for="file in alphaFiles" :key="file.filename" class="file-item grouped-item">
            <q-item-section avatar>
              <div class="vendor-logo-container">
                <img v-if="getVendorLogo(file.filename)" :src="getVendorLogo(file.filename)"
                  :alt="getVendorName(file.filename)" class="vendor-logo" />
                <q-icon v-else :name="getFileIcon(file.filename)" :color="getFileColor(file.filename)" size="md" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="file-name">{{ getDisplayName(file.filename) }}</q-item-label>
              <q-item-label caption class="file-date">
                {{ formatFileDate(file.filename) }}
                <span v-if="formatFileTime(file.filename)" class="file-time">
                  &nbsp;{{ formatFileTime(file.filename) }}
                </span>
              </q-item-label>
              <q-item-label caption class="file-size" v-if="file.size">
                {{ formatFileSize(file.size) }}
              </q-item-label>
              <q-item-label caption v-if="file.source_url" class="source-link">
                <a :href="file.source_url" target="_blank" class="source-url-link">
                  <q-icon name="link" size="12px" class="q-mr-xs" />
                  View Source
                </a>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip :color="getStatusColor(file.status)" text-color="white" size="sm"
                :icon="getStatusIcon(file.status)">
                {{ getStatusText(file.status) }}
              </q-chip>
            </q-item-section>
          </q-item>
        </q-expansion-item>

        <!-- Bravo Group -->
        <q-expansion-item
          v-if="bravoFiles.length > 0"
          v-model="bravoExpanded"
          icon="wb_sunny"
          label="Bravo"
          header-class="text-amber"
          class="config-group"
        >
          <q-item v-for="file in bravoFiles" :key="file.filename" class="file-item grouped-item">
            <q-item-section avatar>
              <div class="vendor-logo-container">
                <img v-if="getVendorLogo(file.filename)" :src="getVendorLogo(file.filename)"
                  :alt="getVendorName(file.filename)" class="vendor-logo" />
                <q-icon v-else :name="getFileIcon(file.filename)" :color="getFileColor(file.filename)" size="md" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="file-name">{{ getDisplayName(file.filename) }}</q-item-label>
              <q-item-label caption class="file-date">
                {{ formatFileDate(file.filename) }}
                <span v-if="formatFileTime(file.filename)" class="file-time">
                  &nbsp;{{ formatFileTime(file.filename) }}
                </span>
              </q-item-label>
              <q-item-label caption class="file-size" v-if="file.size">
                {{ formatFileSize(file.size) }}
              </q-item-label>
              <q-item-label caption v-if="file.source_url" class="source-link">
                <a :href="file.source_url" target="_blank" class="source-url-link">
                  <q-icon name="link" size="12px" class="q-mr-xs" />
                  View Source
                </a>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip :color="getStatusColor(file.status)" text-color="white" size="sm"
                :icon="getStatusIcon(file.status)">
                {{ getStatusText(file.status) }}
              </q-chip>
            </q-item-section>
          </q-item>
        </q-expansion-item>

        <!-- Charlie Group -->
        <q-expansion-item
          v-if="charlieFiles.length > 0"
          v-model="charlieExpanded"
          icon="cloud"
          label="Charlie"
          header-class="text-secondary"
          class="config-group"
        >
          <q-item v-for="file in charlieFiles" :key="file.filename" class="file-item grouped-item">
            <q-item-section avatar>
              <div class="vendor-logo-container">
                <img v-if="getVendorLogo(file.filename)" :src="getVendorLogo(file.filename)"
                  :alt="getVendorName(file.filename)" class="vendor-logo" />
                <q-icon v-else :name="getFileIcon(file.filename)" :color="getFileColor(file.filename)" size="md" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="file-name">{{ getDisplayName(file.filename) }}</q-item-label>
              <q-item-label caption class="file-date">
                {{ formatFileDate(file.filename) }}
                <span v-if="formatFileTime(file.filename)" class="file-time">
                  &nbsp;{{ formatFileTime(file.filename) }}
                </span>
              </q-item-label>
              <q-item-label caption class="file-size" v-if="file.size">
                {{ formatFileSize(file.size) }}
              </q-item-label>
              <q-item-label caption v-if="file.source_url" class="source-link">
                <a :href="file.source_url" target="_blank" class="source-url-link">
                  <q-icon name="link" size="12px" class="q-mr-xs" />
                  View Source
                </a>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip :color="getStatusColor(file.status)" text-color="white" size="sm"
                :icon="getStatusIcon(file.status)">
                {{ getStatusText(file.status) }}
              </q-chip>
            </q-item-section>
          </q-item>
        </q-expansion-item>

        <!-- Delta Group -->
        <q-expansion-item
          v-if="deltaFiles.length > 0"
          v-model="deltaExpanded"
          icon="business"
          label="Delta"
          header-class="text-primary"
          class="config-group"
        >
          <q-item v-for="file in deltaFiles" :key="file.filename" class="file-item grouped-item">
            <q-item-section avatar>
              <div class="vendor-logo-container">
                <img v-if="getVendorLogo(file.filename)" :src="getVendorLogo(file.filename)"
                  :alt="getVendorName(file.filename)" class="vendor-logo" />
                <q-icon v-else :name="getFileIcon(file.filename)" :color="getFileColor(file.filename)" size="md" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="file-name">{{ getDisplayName(file.filename) }}</q-item-label>
              <q-item-label caption class="file-date">
                {{ formatFileDate(file.filename) }}
                <span v-if="formatFileTime(file.filename)" class="file-time">
                  &nbsp;{{ formatFileTime(file.filename) }}
                </span>
              </q-item-label>
              <q-item-label caption class="file-size" v-if="file.size">
                {{ formatFileSize(file.size) }}
              </q-item-label>
              <q-item-label caption v-if="file.source_url" class="source-link">
                <a :href="file.source_url" target="_blank" class="source-url-link">
                  <q-icon name="link" size="12px" class="q-mr-xs" />
                  View Source
                </a>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip :color="getStatusColor(file.status)" text-color="white" size="sm"
                :icon="getStatusIcon(file.status)">
                {{ getStatusText(file.status) }}
              </q-chip>
            </q-item-section>
          </q-item>
        </q-expansion-item>

        <!-- UAT Group -->
        <q-expansion-item
          v-if="uatFiles.length > 0"
          v-model="uatExpanded"
          icon="bug_report"
          label="UAT"
          header-class="text-orange"
          class="config-group"
        >
          <q-item v-for="file in uatFiles" :key="file.filename" class="file-item grouped-item">
            <q-item-section avatar>
              <div class="vendor-logo-container">
                <img v-if="getVendorLogo(file.filename)" :src="getVendorLogo(file.filename)"
                  :alt="getVendorName(file.filename)" class="vendor-logo" />
                <q-icon v-else :name="getFileIcon(file.filename)" :color="getFileColor(file.filename)" size="md" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="file-name">{{ getDisplayName(file.filename) }}</q-item-label>
              <q-item-label caption class="file-date">
                {{ formatFileDate(file.filename) }}
                <span v-if="formatFileTime(file.filename)" class="file-time">
                  &nbsp;{{ formatFileTime(file.filename) }}
                </span>
              </q-item-label>
              <q-item-label caption class="file-size" v-if="file.size">
                {{ formatFileSize(file.size) }}
              </q-item-label>
              <q-item-label caption v-if="file.source_url" class="source-link">
                <a :href="file.source_url" target="_blank" class="source-url-link">
                  <q-icon name="link" size="12px" class="q-mr-xs" />
                  View Source
                </a>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip :color="getStatusColor(file.status)" text-color="white" size="sm"
                :icon="getStatusIcon(file.status)">
                {{ getStatusText(file.status) }}
              </q-chip>
            </q-item-section>
          </q-item>
        </q-expansion-item>

        <!-- ADMIN Group -->
        <q-expansion-item
          v-if="adminFiles.length > 0"
          v-model="adminExpanded"
          icon="admin_panel_settings"
          label="ADMIN"
          header-class="text-green"
          class="config-group"
        >
          <q-item v-for="file in adminFiles" :key="file.filename" class="file-item grouped-item">
            <q-item-section avatar>
              <div class="vendor-logo-container">
                <img v-if="getVendorLogo(file.filename)" :src="getVendorLogo(file.filename)"
                  :alt="getVendorName(file.filename)" class="vendor-logo" />
                <q-icon v-else :name="getFileIcon(file.filename)" :color="getFileColor(file.filename)" size="md" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="file-name">{{ getDisplayName(file.filename) }}</q-item-label>
              <q-item-label caption class="file-date">
                {{ formatFileDate(file.filename) }}
                <span v-if="formatFileTime(file.filename)" class="file-time">
                  &nbsp;{{ formatFileTime(file.filename) }}
                </span>
              </q-item-label>
              <q-item-label caption class="file-size" v-if="file.size">
                {{ formatFileSize(file.size) }}
              </q-item-label>
              <q-item-label caption v-if="file.source_url" class="source-link">
                <a :href="file.source_url" target="_blank" class="source-url-link">
                  <q-icon name="link" size="12px" class="q-mr-xs" />
                  View Source
                </a>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip :color="getStatusColor(file.status)" text-color="white" size="sm"
                :icon="getStatusIcon(file.status)">
                {{ getStatusText(file.status) }}
              </q-chip>
            </q-item-section>
          </q-item>
        </q-expansion-item>

        <!-- Old Server Section Header -->
        <q-separator v-if="oldServerFiles.length > 0" class="q-my-sm" />
        <q-item-label v-if="oldServerFiles.length > 0" header class="text-grey-7">
          <q-icon name="cloud_off" size="sm" class="q-mr-sm" />
          Other - {{ oldServerFiles.length }} configs
        </q-item-label>

        <!-- LoadTest removed - decommissioned -->
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script>
import { defineComponent, ref, onMounted, computed } from 'vue'
import { api } from 'boot/axios'
import { Notify } from 'quasar'

export default defineComponent({
  name: 'MainLayout',

  setup() {

    const leftDrawerOpen = ref(false)
    const downloading = ref(false)
    const parsedFiles = ref([])
    const allExpanded = ref(false)
    
    // Individual expansion states
    const alphaExpanded = ref(false)
    const bravoExpanded = ref(false)
    const charlieExpanded = ref(false)
    const deltaExpanded = ref(false)
    const uatExpanded = ref(false)
    const adminExpanded = ref(false)


    const toggleLeftDrawer = () => {
      leftDrawerOpen.value = !leftDrawerOpen.value
    }

    const toggleAllGroups = () => {
      allExpanded.value = !allExpanded.value
      alphaExpanded.value = allExpanded.value
      bravoExpanded.value = allExpanded.value
      charlieExpanded.value = allExpanded.value
      deltaExpanded.value = allExpanded.value
      uatExpanded.value = allExpanded.value
      adminExpanded.value = allExpanded.value
    }

    const getInfrastructureName = (filename) => {
      if (filename.includes('DELTA-LTM')) return 'A-Delta LTM'
      if (filename.includes('DELTA-FW01_') && !filename.includes('ADMIN')) return 'B-Delta PROD FW'
      if (filename.includes('DELTA-ADMIN-FW01')) return 'C-Delta Admin FW'
      if (filename.includes('CHARLIE-LTM')) return 'D-Charlie LTM'
      if (filename.includes('CHARLIE-FW01')) return 'E-Charlie FW'
      if (filename.includes('BRAVO-LTM')) return 'F-Bravo LTM'
      if (filename.includes('BRAVO-FW01')) return 'G-Bravo FW'
      if (filename.includes('ALPHA-UAT-SLB')) return 'H-Alpha UAT SLB'
      if (filename.includes('ALPHA-FW01')) return 'I-Alpha FW'
      if (filename.includes('ALPHA-LTM01')) return 'I2-Alpha LTM'
      if (filename.includes('H2SLB01.TRZ.PRD')) return 'J-H2SLB TRZ PRD'
      if (filename.includes('ADMIN-LTM')) return 'K-Admin LTM'
      if (filename.includes('UAT-FW01')) return 'L-UAT FW'
      if (filename.includes('UAT-SLB01')) return 'L2-UAT SLB'
      if (filename.includes('ADMIN-FW01') && !filename.includes('DELTA')) return 'O-Admin FW'
      return 'Z-Unknown'
    }

    const getTodayDate = () => {
      // Get today's date in GMT+8 timezone (formatted as YYYY-MM-DD)
      const now = new Date()
      const gmt8Offset = 8 * 60 // GMT+8 in minutes
      const localOffset = now.getTimezoneOffset() // Local timezone offset in minutes
      const gmt8Time = new Date(now.getTime() + (gmt8Offset + localOffset) * 60 * 1000)

      const year = gmt8Time.getFullYear()
      const month = String(gmt8Time.getMonth() + 1).padStart(2, '0')
      const day = String(gmt8Time.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }

    const loadParsedFiles = async () => {
      try {
        const response = await api.get('/config/status')
        if (response.data.success && response.data.files) {
          const existingFiles = response.data.files.filter(file => file.exists).map(file => ({
            filename: file.filename,
            status: file.status,
            size: file.size,
            modified: file.modified,
            file_type: file.file_type,
            source_url: file.source_url,
            infraName: getInfrastructureName(file.filename)
          }))

          // Group by infrastructure name and keep only the most recent file for each
          const filesByInfra = {}
          existingFiles.forEach(file => {
            const infraKey = file.infraName
            if (!filesByInfra[infraKey] || new Date(file.modified) > new Date(filesByInfra[infraKey].modified)) {
              filesByInfra[infraKey] = file
            }
          })

          // Convert back to array and sort by infrastructure name
          let allFiles = Object.values(filesByInfra).sort((a, b) => a.infraName.localeCompare(b.infraName))

          // Filter out deprecated configs that have been replaced
          parsedFiles.value = allFiles.filter(file => {
            // Exclude H2SLB (replaced by ALPHA-LTM01)
            if (file.filename.includes('H2SLB01.TRZ.PRD')) return false
            // Exclude ALPHA-UAT-SLB (replaced by UAT-SLB01)
            if (file.filename.includes('ALPHA-UAT-SLB')) return false
            return true
          })

          // Check if any configs are not from today
          const todayDate = getTodayDate()
          const outdatedFiles = parsedFiles.value.filter(file => {
            if (file.filename.includes('LoadTest')) return false
            const fileDate = formatFileDate(file.filename)
            return fileDate !== todayDate && fileDate !== 'Unknown date'
          })

          if (outdatedFiles.length > 0) {
            // Show notification with details about outdated configs
            // List the specific configs that are outdated
            const outdatedList = outdatedFiles.map(f => {
              const displayName = getDisplayName(f.filename)
              const fileDate = formatFileDate(f.filename)
              return `• ${displayName} (${fileDate})`
            }).join('<br>')

            Notify.create({
              type: 'warning',
              message: `⚠️ Config files are not from today!`,
              caption: `${outdatedFiles.length} config(s) using old dates instead of ${todayDate}:<br><br>${outdatedList}`,
              timeout: 10000,
              position: 'top',
              actions: [
                {
                  label: 'Dismiss',
                  color: 'white'
                }
              ],
              html: true
            })
          }
        }
      } catch (error) {
        console.error('Failed to load parsed files:', error)
      }
    }

    const getVendorLogo = (filename) => {
      // Fortinet FortiGate - Delta Production and Management firewalls
      if (filename.includes('DELTA-FW') || filename.includes('DELTA-ADMIN-FW')) {
        return 'data:image/svg+xml;charset=utf-8,%3Csvg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Crect width="32" height="32" fill="white"/%3E%3Cg%3E%3Crect x="2" y="2" width="6" height="4" rx="2" fill="%23EE3333"/%3E%3Crect x="13" y="2" width="6" height="4" rx="0" fill="%23EE3333"/%3E%3Crect x="24" y="2" width="6" height="4" rx="2" fill="%23EE3333"/%3E%3Crect x="2" y="8" width="6" height="4" rx="0" fill="%23EE3333"/%3E%3Crect x="24" y="8" width="6" height="4" rx="0" fill="%23EE3333"/%3E%3Crect x="2" y="26" width="6" height="4" rx="2" fill="%23EE3333"/%3E%3Crect x="13" y="26" width="6" height="4" rx="0" fill="%23EE3333"/%3E%3Crect x="24" y="26" width="6" height="4" rx="2" fill="%23EE3333"/%3E%3C/g%3E%3Ctext x="16" y="20" fill="%23EE3333" font-family="Arial,sans-serif" font-size="5" font-weight="bold" text-anchor="middle"%3EFORTINET%3C/text%3E%3C/svg%3E'
      }

      // Palo Alto Networks - Other firewalls (Bravo, Charlie, Alpha, etc.)
      if (filename.includes('FW') || filename.includes('firewall')) {
        return 'data:image/svg+xml;charset=utf-8,%3Csvg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Crect width="32" height="32" fill="white"/%3E%3Cg%3E%3Ctext x="16" y="14" fill="%23000000" font-family="Arial,sans-serif" font-size="7" font-weight="bold" text-anchor="middle"%3Epaloalto%3C/text%3E%3Ctext x="16" y="22" fill="%23000000" font-family="Arial,sans-serif" font-size="4" font-weight="normal" text-anchor="middle" letter-spacing="0.5px"%3ENETWORKS%3C/text%3E%3Ccircle cx="26" cy="6" r="1.5" fill="none" stroke="%23000000" stroke-width="0.5"/%3E%3Ctext x="26" y="8" fill="%23000000" font-family="Arial,sans-serif" font-size="3" font-weight="normal" text-anchor="middle"%3E%C2%AE%3C/text%3E%3C/g%3E%3C/svg%3E'
      }

      // F5 LTM - Red circle with f5 text like image #2
      if (filename.includes('LTM') || filename.includes('SLB') || filename.includes('H2SLB')) {
        return 'data:image/svg+xml;charset=utf-8,%3Csvg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Ccircle cx="16" cy="16" r="16" fill="%23ED1033"/%3E%3Ctext x="16" y="22" fill="white" font-family="Arial,sans-serif" font-size="16" font-weight="bold" text-anchor="middle"%3Ef5%3C/text%3E%3C/svg%3E'
      }

      // Fortinet - Red grid pattern like image #3 (for any FortiGate configs if they exist)
      if (filename.includes('FORTI') || filename.includes('FortiGate')) {
        return 'data:image/svg+xml;charset=utf-8,%3Csvg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Crect width="32" height="32" fill="white"/%3E%3Crect x="3" y="3" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="9" y="3" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="15" y="3" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="21" y="3" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="9" y="9" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="15" y="9" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="3" y="15" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="9" y="15" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="15" y="15" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="21" y="15" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="3" y="21" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="9" y="21" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="15" y="21" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3Crect x="21" y="21" width="4" height="4" rx="1" fill="%23EE3333"/%3E%3C/svg%3E'
      }

      return null // Use default icon
    }

    const getVendorName = (filename) => {
      if (filename.includes('DELTA-FW') || filename.includes('DELTA-ADMIN-FW')) return 'Fortinet FortiGate'
      if (filename.includes('FW') || filename.includes('firewall')) return 'Palo Alto Networks'
      if (filename.includes('LTM') || filename.includes('SLB') || filename.includes('H2SLB')) return 'F5 Networks'
      if (filename.includes('FORTI') || filename.includes('FortiGate')) return 'Fortinet'
      return 'Network Device'
    }

    const getFileIcon = (filename) => {
      if (filename.includes('LTM') || filename.includes('SLB') || filename.includes('H2SLB')) return 'network_check'
      if (filename.includes('FW')) return 'security'
      return 'description'
    }

    const getFileColor = (filename) => {
      if (filename.includes('LTM') || filename.includes('SLB') || filename.includes('H2SLB')) return 'blue'
      if (filename.includes('FW')) return 'orange'
      return 'grey'
    }

    const getDisplayName = (filename) => {
      if (filename.includes('DELTA-LTM')) return 'Delta LTM Configuration'
      if (filename.includes('DELTA-FW01_') && !filename.includes('ADMIN')) return 'Delta Production Firewall'
      if (filename.includes('DELTA-ADMIN-FW01')) return 'Delta Management Firewall'
      if (filename.includes('CHARLIE-LTM')) return 'Charlie LTM Configuration'
      if (filename.includes('CHARLIE-FW01')) return 'Charlie Firewall Configuration'
      if (filename.includes('BRAVO-LTM')) return 'Bravo LTM Configuration'
      if (filename.includes('BRAVO-FW01')) return 'Bravo Firewall Configuration'
      if (filename.includes('ALPHA-UAT-SLB')) return 'Alpha UAT SLB Configuration'
      if (filename.includes('UAT-SLB01')) return 'UAT SLB Configuration'
      if (filename.includes('ALPHA-FW01')) return 'Alpha Firewall Configuration'
      if (filename.includes('ALPHA-LTM01')) return 'Alpha LTM Configuration'
      if (filename.includes('ADMIN-LTM')) return 'Admin LTM Configuration'
      if (filename.includes('H2SLB01.TRZ.PRD')) return 'H2SLB Production Configuration'
      if (filename.includes('UAT-FW01')) return 'UAT Firewall Configuration'
      if (filename.includes('ADMIN-FW01') && !filename.includes('DELTA')) return 'Admin Firewall Configuration'
      return filename
    }

    const formatFileDate = (filename) => {
      const dateMatch = filename.match(/(\d{8})/)
      if (dateMatch) {
        const dateStr = dateMatch[1]
        const year = dateStr.substring(0, 4)
        const month = dateStr.substring(4, 6)
        const day = dateStr.substring(6, 8)
        return `${year}-${month}-${day}`
      }
      return 'Unknown date'
    }

    const formatFileTime = (filename) => {
      // Extract time from filename pattern like "20260304-0500.txt"
      const timeMatch = filename.match(/-(\d{4})\.txt$/)
      if (timeMatch) {
        const timeStr = timeMatch[1]
        const hours = timeStr.substring(0, 2)
        const minutes = timeStr.substring(2, 4)
        return `${hours}:${minutes}`
      }
      return null
    }

    const formatFileSize = (bytes) => {
      if (bytes === 0) return '0 Bytes'
      const k = 1024
      const sizes = ['Bytes', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }

    const getStatusColor = (status) => {
      switch (status) {
        case 'parsed': return 'green'
        case 'pending': return 'orange'
        default: return 'grey'
      }
    }

    const getStatusIcon = (status) => {
      switch (status) {
        case 'parsed': return 'check_circle'
        case 'pending': return 'pending'
        default: return 'help'
      }
    }

    const getStatusText = (status) => {
      switch (status) {
        case 'parsed': return 'Parsed'
        case 'pending': return 'Pending'
        default: return 'Unknown'
      }
    }

    const downloadConfigs = async () => {
      downloading.value = true
      try {
        // The daily route is GET-only and reads auto_parse from the query string.
        // Download plus re-parse can exceed the 90s axios default, so allow the
        // full gunicorn --timeout window (300s) for this one call.
        const response = await api.get('/download/daily', {
          params: { auto_parse: true },
          timeout: 300000
        })
        if (response.data.success) {
          Notify.create({
            type: 'positive',
            message: 'Configs downloaded and parsed successfully',
            timeout: 3000
          })

          // Reload parsed files list
          await loadParsedFiles()
        }
      } catch (error) {
        Notify.create({
          type: 'negative',
          message: 'Failed to download configs: ' + (error.response?.data?.message || error.message),
          timeout: 5000
        })
      } finally {
        downloading.value = false
      }
    }

    // Computed properties for grouped files
    const deltaFiles = computed(() => {
      return parsedFiles.value.filter(file => 
        file.filename.includes('DELTA-LTM') || 
        (file.filename.includes('DELTA-FW01_') && !file.filename.includes('ADMIN')) ||
        file.filename.includes('DELTA-ADMIN-FW01')
      ).sort((a, b) => a.infraName.localeCompare(b.infraName))
    })

    const charlieFiles = computed(() => {
      return parsedFiles.value.filter(file => 
        file.filename.includes('CHARLIE-LTM') ||
        file.filename.includes('CHARLIE-FW01')
      ).sort((a, b) => a.infraName.localeCompare(b.infraName))
    })

    const adminFiles = computed(() => {
      return parsedFiles.value.filter(file => 
        (file.filename.includes('ADMIN-LTM') && !file.filename.includes('DELTA')) ||
        (file.filename.includes('ADMIN-FW01') && !file.filename.includes('DELTA'))
      ).sort((a, b) => a.infraName.localeCompare(b.infraName))
    })

    const uatFiles = computed(() => {
      return parsedFiles.value.filter(file =>
        file.filename.includes('UAT-FW01') ||
        file.filename.includes('UAT-SLB01')
      ).sort((a, b) => a.infraName.localeCompare(b.infraName))
    })


    const alphaFiles = computed(() => {
      return parsedFiles.value.filter(file =>
        file.filename.includes('ALPHA-FW01') ||
        file.filename.includes('ALPHA-LTM01')
      ).sort((a, b) => a.infraName.localeCompare(b.infraName))
    })

    const bravoFiles = computed(() => {
      return parsedFiles.value.filter(file => 
        file.filename.includes('BRAVO-LTM') ||
        file.filename.includes('BRAVO-FW01')
      ).sort((a, b) => a.infraName.localeCompare(b.infraName))
    })

    // Separate files by server
    const newServerFiles = computed(() => {
      return parsedFiles.value.filter(file =>
        file.source_url
      )
    })

    const oldServerFiles = computed(() => {
      return parsedFiles.value.filter(file =>
        !file.source_url
      )
    })

    onMounted(() => {
      loadParsedFiles()
    })

    return {
      leftDrawerOpen,
      downloading,
      parsedFiles,
      newServerFiles,
      oldServerFiles,
      deltaFiles,
      charlieFiles,
      adminFiles,
      uatFiles,
      alphaFiles,
      bravoFiles,
      allExpanded,
      alphaExpanded,
      bravoExpanded,
      charlieExpanded,
      deltaExpanded,
      uatExpanded,
      adminExpanded,
      toggleLeftDrawer,
      toggleAllGroups,
      downloadConfigs,
      getVendorLogo,
      getVendorName,
      getFileIcon,
      getFileColor,
      getDisplayName,
      formatFileDate,
      formatFileTime,
      formatFileSize,
      getStatusColor,
      getStatusIcon,
      getStatusText
    }
  }
})
</script>

<style scoped>
.file-item {
  border-bottom: 1px solid #e0e0e0;
  transition: background-color 0.2s ease;
}

.file-item:hover {
  background-color: #f5f5f5;
}

.file-name {
  font-weight: 500;
  color: #1976d2;
}

.file-date {
  font-size: 0.85em;
  color: #666;
}

.file-time {
  font-size: 0.9em;
  color: #1976d2;
  font-weight: 500;
  margin-left: 4px;
}

.file-size {
  font-size: 0.8em;
  color: #999;
  margin-top: 2px;
}

.q-drawer .q-item-label[header] {
  font-weight: 600;
  color: #1976d2;
  padding-bottom: 8px;
}

.q-drawer {
  border-right: 1px solid #e0e0e0;
}

.q-chip {
  font-weight: 500;
  font-size: 0.75em;
}

.source-link {
  margin-top: 4px;
}

.source-url-link {
  color: #1976d2;
  text-decoration: none;
  font-size: 0.8em;
  display: inline-flex;
  align-items: center;
  transition: color 0.2s ease;
}

.source-url-link:hover {
  color: #1565c0;
  text-decoration: underline;
}

.vendor-logo-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 40px;
  height: 40px;
}

.vendor-logo {
  max-width: 32px;
  max-height: 32px;
  width: auto;
  height: auto;
  border-radius: 4px;
  border: 2px solid #e0e0e0;
  box-sizing: border-box;
}

.config-group {
  margin-bottom: 8px;
}

.config-group .q-expansion-item__container > .q-expansion-item__content {
  padding-left: 0;
}

.grouped-item {
  padding-left: 32px;
  border-left: 2px solid #e0e0e0;
  margin-left: 16px;
}

.grouped-item:last-child {
  border-left: 2px solid transparent;
}
</style>