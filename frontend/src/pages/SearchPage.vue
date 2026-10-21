<template>
  <q-page class="search-container">
    <div class="q-pa-md" style="max-width: none;">
      <!-- Search Form -->
      <q-card class="q-mb-lg">
        <q-card-section>
          <div class="text-h6">Network Configuration Search</div>
          <div class="text-subtitle2 text-grey-7">
            Search for IP addresses (comma, space, or line separated for multiple), object names, or FQDN records across LTM, Firewall, and DNS configurations
          </div>
        </q-card-section>

        <q-card-section>
          <div class="row q-gutter-md">
            <div class="col-md-4 col-sm-12">
              <q-input 
                v-if="!isMultipleIps" 
                v-model="searchQuery" 
                :loading="searching" 
                :rules="getValidationRules()" 
                :label="getDynamicInputLabel()" 
                outlined 
                :placeholder="getDynamicPlaceholder()" 
                style="height: 56px; cursor: text;"
                class="main-search-input"
                @keyup.enter="performSearch">
                <template #prepend>
                  <q-icon name="search" />
                </template>
                <template #append>
                  <q-chip
v-if="searchQuery" :color="searchType === 'ip' ? 'blue' : searchType === 'fqdn' ? 'purple' : 'green'" 
                    text-color="white" dense size="md">
                    {{ getSearchTypeLabel() }}
                  </q-chip>
                </template>
              </q-input>
              
              <q-input 
                v-if="isMultipleIps"
                v-model="searchQuery" 
                :loading="searching" 
                :rules="getValidationRules()" 
                type="textarea"
                :rows="4"
                :autogrow="false"
                :max-height="100"
                style="max-height: 100px;"
                :label="getDynamicInputLabel()" 
                outlined 
                :placeholder="'Enter multiple IP addresses (one per line or comma separated):\n192.168.1.1\n192.168.1.2, 192.168.1.3'">
                <template #prepend>
                  <q-icon name="search" />
                </template>
                <template #append>
                  <q-chip v-if="searchQuery" color="orange" text-color="white" dense size="md">
                    Multiple IPs ({{ getIpCount() }})
                  </q-chip>
                </template>
              </q-input>
            </div>

            <div class="col-md-4 col-sm-12">
              <div class="row q-gutter-sm">
                <div class="col">
                  <q-btn
                    :disable="!searchQuery || !isValidQuery"
                    :loading="searching"
                    color="primary"
                    icon="search"
                    label="Search"
                    style="height: 56px;"
                    class="full-width"
                    @click="performSearch" />
                </div>
                <div style="width: 60px;">
                  <q-btn-dropdown
                    icon="history"
                    color="blue-grey"
                    style="height: 56px;"
                    :loading="loadingHistory"
                    dropdown-icon="keyboard_arrow_down"
                    dense
                    @show="loadSearchHistory">
                    <template #label>
                      <q-tooltip>Search History</q-tooltip>
                    </template>
                    <q-list style="min-width: 300px; max-width: 400px; max-height: 400px;" class="q-pa-none">
                      <q-item-label header class="text-primary text-weight-bold">Recent Searches</q-item-label>
                      <q-separator />

                      <template v-if="loadingHistory">
                        <q-item>
                          <q-item-section>
                            <q-item-label class="text-grey-6 text-center q-py-md">Loading...</q-item-label>
                          </q-item-section>
                        </q-item>
                      </template>

                      <template v-else-if="searchHistory.length === 0">
                        <q-item>
                          <q-item-section>
                            <q-item-label class="text-grey-6 text-center q-py-md">No search history</q-item-label>
                          </q-item-section>
                        </q-item>
                      </template>

                      <template v-else>
                        <q-item
                          v-for="item in searchHistory"
                          :key="item.id"
                          clickable
                          @click="selectHistoryItem(item)"
                          class="q-py-sm">
                          <q-item-section>
                            <q-item-label>{{ item.search_query }}</q-item-label>
                            <q-item-label caption>
                              <q-chip
                                :color="item.search_type === 'ip' ? 'blue' : item.search_type === 'fqdn' ? 'purple' : 'green'"
                                text-color="white"
                                dense
                                size="sm"
                                class="q-mr-sm">
                                {{ item.search_type.toUpperCase() }}
                              </q-chip>
                              {{ item.search_date }} • {{ item.results_count }} results
                            </q-item-label>
                          </q-item-section>
                        </q-item>

                        <q-separator />
                        <q-item clickable @click="clearSearchHistory" class="text-negative">
                          <q-item-section side>
                            <q-icon name="clear_all" />
                          </q-item-section>
                          <q-item-section>Clear History</q-item-section>
                        </q-item>
                      </template>
                    </q-list>
                  </q-btn-dropdown>
                </div>
              </div>
            </div>
            
            <!-- IP Search Direction Filter -->
            <div v-if="searchType === 'ip'" class="col-md-4 col-sm-12">
              <q-select 
                v-model="ipSearchDirection" 
                :options="[
                  { label: 'Source & Destination', value: 'both', icon: 'swap_horiz' },
                  { label: 'Source Only', value: 'source', icon: 'input' },
                  { label: 'Destination Only', value: 'destination', icon: 'output' }
                ]" 
                label="Search In" 
                outlined 
                style="height: 56px;"
                emit-value
                map-options
                option-value="value"
                option-label="label"
                class="ip-direction-filter">
                <template #prepend>
                  <q-icon name="filter_alt" />
                </template>
                <template #option="scope">
                  <q-item v-bind="scope.itemProps">
                    <q-item-section avatar>
                      <q-icon :name="scope.opt.icon" />
                    </q-item-section>
                    <q-item-section>
                      <q-item-label>{{ scope.opt.label }}</q-item-label>
                    </q-item-section>
                  </q-item>
                </template>
                <template #selected>
                  <q-chip color="blue-grey" text-color="white" dense>
                    <q-icon 
                      :name="ipSearchDirection === 'both' ? 'swap_horiz' : ipSearchDirection === 'source' ? 'input' : 'output'" 
                      class="q-mr-xs" 
                    />
                    {{ ipSearchDirection === 'both' ? 'Both' : ipSearchDirection === 'source' ? 'Source' : 'Destination' }}
                  </q-chip>
                </template>
              </q-select>
            </div>
          </div>

          <!-- Infrastructure Filter -->
          <div class="row q-gutter-md q-mt-md">
            <div class="col-12">
              <q-card flat bordered class="q-pa-sm">
                <q-card-section class="q-pb-sm">
                  <div class="text-subtitle2 text-weight-medium">Search in Infrastructure:</div>
                  <div class="text-caption text-grey-7">Select infrastructure configurations to search in. Toggle off to exclude from search.</div>
                </q-card-section>
                <q-card-section class="q-pt-none">
                  <div class="row q-gutter-sm">
                    <div v-for="infra in visibleInfrastructures" :key="infra.key" class="col-auto">
                      <q-toggle
                        v-model="infraToggleStates[infra.key]"
                        :label="infra.label"
                        :icon="infra.icon"
                        :color="infra.color"
                        size="sm"
                        class="infra-toggle"
                      />
                    </div>
                  </div>
                  <div class="row q-gutter-sm q-mt-sm">
                    <q-btn
                      size="sm"
                      color="positive"
                      outline
                      icon="check_box"
                      label="Select All"
                      @click="selectAllInfrastructures"
                    />
                    <q-btn
                      size="sm"
                      color="negative"
                      outline
                      icon="check_box_outline_blank"
                      label="Deselect All"
                      @click="deselectAllInfrastructures"
                    />
                    <q-chip
                      v-if="selectedInfrastructuresCount > 0"
                      :color="selectedInfrastructuresCount === visibleInfrastructures.length ? 'positive' : 'primary'"
                      text-color="white"
                      size="sm"
                    >
                      {{ selectedInfrastructuresCount }} / {{ visibleInfrastructures.length }} selected
                    </q-chip>
                  </div>
                </q-card-section>
              </q-card>
            </div>
          </div>

          <!-- Environment Filter -->
          <div v-if="searchResults" class="row q-gutter-md q-mt-md">
            <div class="col-md-4 col-sm-12">
              <q-select
                v-model="selectedEnvironments"
                :options="availableEnvironments"
                label="Filter by Environment"
                multiple
                outlined 
                use-chips
                clearable
                options-dense
                emit-value
                map-options
                class="environment-filter"
              >
                <template #option="scope">
                  <q-item v-bind="scope.itemProps">
                    <q-item-section>
                      <q-chip :color="getEnvironmentColor(scope.opt.label)" text-color="white" dense size="md">
                        {{ scope.opt.label }}
                      </q-chip>
                    </q-item-section>
                  </q-item>
                </template>
                <template #selected-item="scope">
                  <q-chip 
                    :color="getEnvironmentColor(scope.opt.label)" 
                    text-color="white" 
                    dense 
                    removable 
                    @remove="scope.removeAtIndex(scope.index)"
                  >
                    {{ scope.opt.label }}
                  </q-chip>
                </template>
              </q-select>
            </div>
            <div class="col-md-6 col-sm-12 flex items-center">
              <q-btn
v-if="selectedEnvironments && selectedEnvironments.length > 0" 
                color="grey-6" 
                outline 
                icon="clear" 
                label="Clear Filter" 
                @click="clearEnvironmentFilter" 
              />
            </div>
          </div>
        </q-card-section>
      </q-card>

      <!-- Bulk Search Results Summary -->
      <div v-if="searchResults && searchResults.is_bulk" class="q-mb-lg">
        <q-card>
          <q-card-section>
            <div class="text-h6">Bulk Search Results Summary</div>
            <div class="row q-gutter-md q-mt-sm">
              <div class="col">
                <q-chip color="blue" text-color="white" dense size="md">
                  {{ searchResults.summary.searched_ips }} IPs Searched
                </q-chip>
              </div>
              <div class="col">
                <q-chip color="green" text-color="white" dense size="md">
                  {{ searchResults.summary.total_ltm_matches }} LTM Matches
                </q-chip>
              </div>
              <div class="col">
                <q-chip color="orange" text-color="white" dense size="md">
                  {{ searchResults.summary.total_firewall_matches }} Firewall Matches
                </q-chip>
              </div>
              <div class="col">
                <q-chip color="purple" text-color="white" dense size="md">
                  {{ searchResults.summary.total_fqdn_matches }} FQDN Matches
                </q-chip>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Bulk Search Results by IP -->
      <div v-if="searchResults && searchResults.is_bulk" class="bulk-results">
        <div v-for="(result, ip) in searchResults.bulk_results" :key="ip" class="q-mb-lg">
          <q-card>
            <q-card-section class="bg-blue-grey-1">
              <div class="text-h6">{{ formatIpWithClassification(ip, result.ip_classification) }}</div>
              <div class="text-subtitle2">
                {{ result.summary.total_matches }} total matches 
                ({{ result.summary.ltm_matches }} LTM, {{ result.summary.firewall_matches }} Firewall, {{ result.summary.fqdn_matches }} FQDN)
              </div>
            </q-card-section>
            
            <!-- Render regular results for each IP -->
            <q-card-section v-if="result.summary.total_matches > 0">
              <q-tabs v-model="activeTab" dense class="text-grey" active-color="primary" indicator-color="primary" align="left">
                <q-tab name="firewall" :label="`Firewall (${result.summary.firewall_matches})`" />
                <q-tab name="ltm" :label="`LTM (${result.summary.ltm_matches})`" />
                <q-tab
v-if="result.fqdn_results && result.fqdn_results.success && result.fqdn_results.count > 0" 
                  name="fqdn" :label="`FQDN (${result.summary.fqdn_matches})`" />
              </q-tabs>
              
              <q-tab-panels v-model="activeTab" animated>
                <!-- Firewall tab for this IP -->
                <q-tab-panel name="firewall" class="fw-result">
                  <!-- No firewall policies found -->
                  <div v-if="!result.firewall_results || !result.firewall_results.policies || result.firewall_results.policies.length === 0">
                    <q-card flat class="text-center q-pa-lg">
                      <q-icon name="security" size="56px" color="grey-5" />
                      <div class="text-h6 q-mt-sm text-grey-7">No firewall policies found</div>
                      <div class="text-body2 text-grey-6">The IP address was not found in any firewall policies</div>
                    </q-card>
                  </div>

                  <!-- Address Objects -->
                  <div v-if="result.firewall_results && result.firewall_results.address_objects && result.firewall_results.address_objects.length > 0" class="q-mb-lg">
                    <div class="text-h6 q-mb-md">Matching Address Objects</div>
                    <!-- Infrastructure Mapping Table -->
                    <div class="q-mb-lg">
                      <div class="text-subtitle1 q-mb-sm">Infrastructure Mapping</div>
                      <q-table
                        :columns="addressObjectsColumns"
                        :rows="filterAddressObjectsByEnvironment(result.firewall_results.address_objects)"
                        row-key="id"
                        flat
                        bordered
                        dense
                        :pagination="{ rowsPerPage: 10 }"
                        class="infrastructure-mapping-table">
                        <template v-slot:body-cell-name="props">
                          <q-td :props="props">
                            <q-chip
                              :color="props.row.object_type === 'group' ? 'blue-3' : getCidrGreenColor(props.row.cidr_notation || (props.row.ip_address && props.row.object_type === 'host' ? props.row.ip_address + '/32' : props.row.ip_address))"
                              text-color="black" dense>
                              {{ props.row.name }}
                              <q-tooltip v-if="props.row.object_type === 'group'">
                                Address Group with {{ props.row.member_count || 0 }} members
                              </q-tooltip>
                            </q-chip>
                          </q-td>
                        </template>
                        <template v-slot:body-cell-environment="props">
                          <q-td :props="props">
                            <q-chip
                              :color="getEnvironmentColor(props.row.environment)"
                              text-color="white" dense>
                              {{ props.row.environment }}
                            </q-chip>
                          </q-td>
                        </template>
                        <template v-slot:body-cell-config_type="props">
                          <q-td :props="props">
                            <q-chip
                              :color="props.row.config_type === 'fortigate' ? 'orange-6' : 'blue-6'"
                              text-color="white" dense>
                              {{ props.row.config_type === 'fortigate' ? 'FortiGate' : 'Palo Alto' }}
                            </q-chip>
                          </q-td>
                        </template>
                      </q-table>
                    </div>
                  </div>

                  <!-- Firewall Policies -->
                  <div v-if="result.firewall_results && result.firewall_results.policies && result.firewall_results.policies.length > 0" class="q-mb-lg">
                    <div class="text-h6 q-mb-md">Firewall Policies</div>
                    <div class="firewall-table-container">
                      <q-table
                        v-model:pagination="pagination"
                        :rows="filterPoliciesByEnvironment(result.firewall_results.policies)" 
                        :columns="firewallColumns" :expanded="expandedPolicies" bordered class="firewall-policy-table" flat
                        row-key="id" :sort-method="customSort"
                        binary-state-sort @update:expanded="expandedPolicies = $event">
                        <template #header="props">
                          <q-tr :props="props" class="bg-blue-grey-1">
                            <q-th v-for="col in props.cols" :key="col.name" :props="props" 
                              class="text-weight-bold sortable-header" 
                              :style="{ width: getColumnWidth(col.name), textAlign: col.align }"
                              :class="{ 'cursor-pointer': col.sortable !== false }"
                              @click="col.sortable !== false ? props.sort(col.field) : null">
                              <div class="row items-center no-wrap">
                                <span>{{ col.label }}</span>
                                <q-space />
                                <q-icon v-if="col.sortable !== false && props.sort === col.field" 
                                  :name="props.descending ? 'arrow_downward' : 'arrow_upward'" 
                                  size="20px" class="q-ml-xs" />
                              </div>
                            </q-th>
                          </q-tr>
                        </template>

                        <!-- Table content matches single IP display exactly -->
                        <template #body="props">
                          <q-tr :props="props">
                            <q-td key="expand" :props="props" :style="{ width: getColumnWidth('expand'), textAlign: 'center' }">
                              <q-btn
:icon="props.expand ? 'remove' : 'add'" color="primary" dense round size="md"
                                @click="props.expand = !props.expand" />
                            </q-td>

                            <q-td key="environment" :props="props" :style="{ width: getColumnWidth('environment'), textAlign: 'center' }">
                              <q-chip
:color="getEnvironmentColor(props.row.environment)" dense size="md"
                                text-color="white" class="environment-chip">
                                <q-icon v-if="props.row.config_type === 'paloalto' && props.row.environment !== 'Admin FW'" name="security" size="sm" class="q-mr-xs"/>
                                {{ props.row.environment }}
                              </q-chip>
                            </q-td>

                            <q-td key="source_zone" :props="props" class="zone-column" :style="{ width: getColumnWidth('source_zone'), textAlign: 'center' }">
                              <q-chip v-if="props.row.source_zone" :color="getZoneColor(props.row.source_zone)" text-color="white" dense size="md">
                                {{ props.row.source_zone }}
                              </q-chip>
                              <span v-else class="text-grey-6 text-caption">-</span>
                            </q-td>

                            <q-td key="destination_zone" :props="props" class="zone-column" :style="{ width: getColumnWidth('destination_zone'), textAlign: 'center' }">
                              <q-chip v-if="props.row.destination_zone" :color="getZoneColor(props.row.destination_zone)" text-color="white" dense size="md">
                                {{ props.row.destination_zone }}
                              </q-chip>
                              <span v-else class="text-grey-6 text-caption">-</span>
                            </q-td>

                            <q-td key="policy_id" :props="props" :style="{ width: getColumnWidth('policy_id'), textAlign: 'center' }">
                              {{ props.row.policy_id }}
                            </q-td>

                            <q-td key="name" :props="props" :style="{ width: getColumnWidth('name'), textAlign: 'left' }" class="policy-name-cell">
                              <div class="policy-name-text">{{ props.row.name || 'Unnamed Policy' }}</div>
                            </q-td>

                            <q-td key="source_addresses" :props="props" class="source-column" :style="{ width: getColumnWidth('source_addresses'), textAlign: 'left' }">
                              <div class="address-preview">
                                <div class="chips-container">
                                  <q-chip
v-for="(src, index) in JSON.parse(props.row.source_addresses || '[]')"
                                    :key="src + index"
                                    :color="props.row.match_details && props.row.match_details.source.includes(src) ? getMatchedAddressColor(src, props.row.address_mappings) : 'grey'"
                                    class="address-chip clickable-group" dense size="md" text-color="white" @click.stop="performClickableSearch(src)">
                                    {{ src }}
                                  </q-chip>
                                </div>
                              </div>
                            </q-td>

                            <q-td key="destination_addresses" :props="props" class="destination-column" :style="{ width: getColumnWidth('destination_addresses'), textAlign: 'left' }">
                              <div class="address-preview">
                                <div class="chips-container">
                                  <q-chip
                                    v-if="JSON.parse(props.row.destination_addresses || '[]').length === 0"
                                    color="orange-7" dense size="md" text-color="white" class="address-chip">
                                    any
                                  </q-chip>
                                  <q-chip
                                    v-for="(dst, index) in JSON.parse(props.row.destination_addresses || '[]')"
                                    :key="dst + index"
                                    :color="props.row.match_details && props.row.match_details.destination.includes(dst) ? getMatchedAddressColor(dst, props.row.address_mappings) : 'grey'"
                                    class="address-chip clickable-group" dense size="md" text-color="white" @click.stop="performClickableSearch(dst)">
                                    {{ dst }}
                                  </q-chip>
                                </div>
                              </div>
                            </q-td>

                            <q-td key="services" :props="props" class="services-column" :style="{ width: getColumnWidth('services'), textAlign: 'left' }">
                              <div class="address-preview">
                                <div class="chips-container">
                                  <q-chip
v-for="(svc, index) in JSON.parse(props.row.services || '[]')"
                                    :key="svc + index" class="service-chip" color="blue" dense size="md"
                                    text-color="white">
                                    {{ svc }}
                                  </q-chip>
                                </div>
                              </div>
                            </q-td>

                            <q-td key="match_details" :props="props" class="match-details-column" :style="{ width: getColumnWidth('match_details'), textAlign: 'left' }">
                              <div class="match-details-preview">
                                <div v-if="props.row.match_details">
                                  <div v-if="props.row.match_details.source && props.row.match_details.source.length > 0" class="q-mb-xs">
                                    <div class="text-caption text-weight-bold text-positive">Source:</div>
                                    <div class="chips-container">
                                      <q-chip
v-for="match in props.row.match_details.source" :key="match"
                                        color="positive" dense size="sm" text-color="white" class="q-mr-xs q-mb-xs">
                                        {{ match }}
                                      </q-chip>
                                    </div>
                                  </div>
                                  <div v-if="props.row.match_details.destination && props.row.match_details.destination.length > 0" class="q-mb-xs">
                                    <div class="text-caption text-weight-bold text-positive">Destination:</div>
                                    <div class="chips-container">
                                      <q-chip
v-for="match in props.row.match_details.destination" :key="match"
                                        color="positive" dense size="sm" text-color="white" class="q-mr-xs q-mb-xs">
                                        {{ match }}
                                      </q-chip>
                                    </div>
                                  </div>
                                  <div v-if="(!props.row.match_details.source || props.row.match_details.source.length === 0) && (!props.row.match_details.destination || props.row.match_details.destination.length === 0)" class="text-caption text-grey-6">
                                    No matches
                                  </div>
                                </div>
                                <div v-else class="text-caption text-grey-6">
                                  No details
                                </div>
                              </div>
                            </q-td>

                            <q-td key="action" :props="props" :style="{ width: getColumnWidth('action'), textAlign: 'center' }">
                              <q-chip
:color="props.row.action === 'accept' ? 'positive' : 'negative'" dense size="md"
                                text-color="white">
                                {{ props.row.action }}
                              </q-chip>
                            </q-td>
                          </q-tr>

                          <!-- Expanded Row with enhanced detail -->
                          <q-tr v-show="props.expand" :props="props" class="bg-blue-grey-1">
                            <q-td colspan="100%">
                              <div class="q-pa-md">
                                <!-- Policy Details Header -->
                                <div class="row q-mb-md">
                                  <div class="col-12">
                                    <div class="text-h6 text-primary q-mb-sm">
                                      Policy {{ props.row.policy_id }} - {{ props.row.name || 'Unnamed Policy' }}
                                    </div>
                                    <q-separator />
                                  </div>
                                </div>

                                <!-- Detailed Information Sections - 4 Column Layout -->
                                <div class="row q-gutter-md policy-details-row">
                                  <!-- Source Addresses Section -->
                                  <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                    <q-card flat bordered>
                                      <q-card-section class="bg-grey-2">
                                        <div class="text-subtitle1 text-weight-bold text-grey-8">
                                          <q-icon name="input" class="q-mr-sm" />
                                          Source Addresses
                                        </div>
                                      </q-card-section>
                                      <q-card-section>
                                        <div class="q-gutter-sm">
                                          <!-- Any/All addresses case -->
                                          <div v-if="JSON.parse(props.row.source_addresses || '[]').length === 0" class="address-card">
                                            <q-card flat bordered class="q-mb-sm">
                                              <q-card-section class="q-pa-sm">
                                                <q-chip color="orange-7" dense text-color="white" icon="info" class="q-mb-xs">
                                                  any
                                                </q-chip>
                                                <div class="address-ips">
                                                  <span class="ip-item">All source addresses allowed</span>
                                                </div>
                                              </q-card-section>
                                            </q-card>
                                          </div>
                                          
                                          <!-- Specific addresses -->
                                          <div v-for="(src, index) in JSON.parse(props.row.source_addresses || '[]')" :key="src + index" class="address-card">
                                            <q-card flat bordered class="q-mb-sm">
                                              <q-card-section class="q-pa-sm">
                                                <div class="address-header">
                                                  <q-chip
                                                    :color="props.row.match_details && props.row.match_details.source.includes(src) ? getMatchedAddressColor(src, props.row.address_mappings) : 'blue-grey-6'"
                                                    :icon="props.row.match_details && props.row.match_details.source.includes(src) ? 'verified' : 'info'"
                                                    dense text-color="white" class="q-mb-xs clickable-group" @click.stop="performClickableSearch(src)">
                                                    {{ src }}
                                                  </q-chip>
                                                </div>
                                                <!-- Check if this is a group with hierarchical member details -->
                                                <div v-if="props.row.address_mappings && props.row.address_mappings[src] && props.row.address_mappings[src].hierarchical_members" class="group-details">
                                                  <!-- Group expand/collapse button -->
                                                  <div class="row items-center q-mb-sm">
                                                    <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                      {{ props.row.address_mappings[src].member_count }} members
                                                    </q-chip>
                                                    <q-btn
                                                      :icon="expandedPolicyGroups[`${props.row.id}_${src}`] ? 'expand_less' : 'expand_more'"
                                                      flat dense round size="sm"
                                                      @click="togglePolicyGroupExpansion(`${props.row.id}_${src}`)" />
                                                  </div>

                                                  <!-- Expandable hierarchical member details -->
                                                  <div v-if="expandedPolicyGroups[`${props.row.id}_${src}`]" class="member-details">
                                                    <div v-for="(member, memberIndex) in safeParseHierarchicalMembers(props.row.address_mappings[src].hierarchical_members)" :key="memberIndex" class="member-item q-mb-xs">
                                                      <!-- Individual address member -->
                                                      <div v-if="member.type === 'address'" class="address-member">
                                                        <q-chip
                                                          :color="getMemberChipColor(member.type, member.name)"
                                                          text-color="white"
                                                          size="sm"
                                                          class="member-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                          <span v-if="member.ip" class="member-separator">→</span>
                                                          <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                        </q-chip>
                                                      </div>

                                                      <!-- Group member with nested expandable structure -->
                                                      <div v-else-if="member.type === 'group' && member.expandable" class="group-member">
                                                        <div class="group-header">
                                                          <q-chip
                                                            color="amber-8"
                                                            text-color="white"
                                                            size="sm"
                                                            class="member-chip q-mr-sm">
                                                            <q-icon name="folder" class="q-mr-xs" />
                                                            <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                            <span class="member-separator">→</span>
                                                            <span class="member-count">{{ member.member_count }} members</span>
                                                          </q-chip>
                                                          <q-btn
                                                            :icon="expandedPolicyGroups[`${props.row.id}_${src}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                                            flat dense round size="xs"
                                                            @click="togglePolicyGroupExpansion(`${props.row.id}_${src}_${member.name}`)" />
                                                        </div>

                                                        <!-- Nested members for this group -->
                                                        <div v-if="expandedPolicyGroups[`${props.row.id}_${src}_${member.name}`] && member.members" class="nested-members q-ml-md q-mt-xs">
                                                          <div v-for="(nested, nestedIndex) in member.members" :key="nestedIndex" class="nested-member q-mb-xs">
                                                            <q-chip
                                                              :color="getMemberChipColor(nested.type, nested.name)"
                                                              text-color="white"
                                                              size="xs"
                                                              class="nested-chip">
                                                              <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                              <span v-if="nested.ip" class="member-separator">→</span>
                                                              <span v-if="nested.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                            </q-chip>
                                                          </div>
                                                        </div>
                                                      </div>

                                                      <!-- Other member types -->
                                                      <div v-else class="other-member">
                                                        <q-chip
                                                          :color="getMemberChipColor(member.type, member.name)"
                                                          text-color="white"
                                                          size="sm"
                                                          class="member-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                          <span v-if="member.ip" class="member-separator">→</span>
                                                          <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                        </q-chip>
                                                      </div>
                                                    </div>
                                                  </div>
                                                </div>

                                                <!-- Fallback: Check if this is a group with old flat member details -->
                                                <div v-else-if="props.row.address_mappings && props.row.address_mappings[src] && props.row.address_mappings[src].member_details" class="group-details">
                                                  <!-- Group expand/collapse button -->
                                                  <div class="row items-center q-mb-sm">
                                                    <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                      {{ props.row.address_mappings[src].member_count }} members
                                                    </q-chip>
                                                    <q-btn
                                                      :icon="expandedPolicyGroups[`${props.row.id}_${src}`] ? 'expand_less' : 'expand_more'"
                                                      flat dense round size="sm"
                                                      @click="togglePolicyGroupExpansion(`${props.row.id}_${src}`)" />
                                                  </div>

                                                  <!-- Expandable member details (fallback) -->
                                                  <div v-if="expandedPolicyGroups[`${props.row.id}_${src}`]" class="member-details">
                                                    <div v-for="(member, memberIndex) in safeParseMemberDetails(props.row.address_mappings[src].member_details)" :key="memberIndex" class="member-item q-mb-xs">
                                                      <q-chip
                                                        :color="getMemberChipColor(member.type, member.name)"
                                                        text-color="white"
                                                        size="sm"
                                                        class="member-chip">
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                        <span v-if="member.ip" class="member-separator">→</span>
                                                        <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                      </q-chip>
                                                    </div>
                                                  </div>
                                                </div>
                                                <!-- Regular IP addresses (when not a group) -->
                                                <div v-else class="address-ips">
                                                  <div v-for="ipAddress in getAddressDisplay(src, props.row).ip.split(', ')" :key="ipAddress" class="ip-item q-mb-xs">
                                                    <span class="ip-bullet">•</span>
                                                    <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(ipAddress.trim()) }" @click.stop="performClickableSearch(ipAddress.trim())">{{ ipAddress.trim() }}</span>
                                                  </div>
                                                </div>
                                              </q-card-section>
                                            </q-card>
                                          </div>
                                        </div>
                                      </q-card-section>
                                    </q-card>
                                  </div>

                                  <!-- Destination Addresses Section -->
                                  <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                    <q-card flat bordered>
                                      <q-card-section class="bg-grey-2">
                                        <div class="text-subtitle1 text-weight-bold text-grey-8">
                                          <q-icon name="output" class="q-mr-sm" />
                                          Destination Addresses
                                        </div>
                                      </q-card-section>
                                      <q-card-section>
                                        <div class="q-gutter-sm">
                                          <!-- Any/All addresses case -->
                                          <div v-if="JSON.parse(props.row.destination_addresses || '[]').length === 0" class="address-card">
                                            <q-card flat bordered class="q-mb-sm">
                                              <q-card-section class="q-pa-sm">
                                                <q-chip color="orange-7" dense text-color="white" icon="info" class="q-mb-xs">
                                                  any
                                                </q-chip>
                                                <div class="address-ips">
                                                  <span class="ip-item">All destinations allowed</span>
                                                </div>
                                              </q-card-section>
                                            </q-card>
                                          </div>
                                          
                                          <!-- Specific addresses -->
                                          <div v-for="(dst, index) in JSON.parse(props.row.destination_addresses || '[]')" :key="dst + index" class="address-card">
                                            <q-card flat bordered class="q-mb-sm">
                                              <q-card-section class="q-pa-sm">
                                                <div class="address-header">
                                                  <q-chip
                                                    :color="props.row.address_mappings && props.row.address_mappings[dst] ? getMatchedAddressColor(dst, props.row.address_mappings) : 'blue-grey-6'"
                                                    :icon="props.row.match_details && props.row.match_details.destination.includes(dst) ? 'verified' : 'info'"
                                                    dense text-color="white" class="q-mb-xs clickable-group" @click.stop="performClickableSearch(dst)">
                                                    {{ dst }}
                                                  </q-chip>
                                                </div>
                                                <!-- Check if this is a group with hierarchical member details -->
                                                <div v-if="props.row.address_mappings && props.row.address_mappings[dst] && props.row.address_mappings[dst].hierarchical_members" class="group-details">
                                                  <!-- Group expand/collapse button -->
                                                  <div class="row items-center q-mb-sm">
                                                    <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                      {{ props.row.address_mappings[dst].member_count }} members
                                                    </q-chip>
                                                    <q-btn
                                                      :icon="expandedPolicyGroups[`${props.row.id}_${dst}`] ? 'expand_less' : 'expand_more'"
                                                      flat dense round size="sm"
                                                      @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}`)" />
                                                  </div>

                                                  <!-- Expandable hierarchical member details -->
                                                  <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}`]" class="member-details">
                                                    <div v-for="(member, memberIndex) in safeParseHierarchicalMembers(props.row.address_mappings[dst].hierarchical_members)" :key="memberIndex" class="member-item q-mb-xs">
                                                      <!-- Individual address member -->
                                                      <div v-if="member.type === 'address' || member.type === 'vip'" class="address-member">
                                                        <q-chip
                                                          :color="getMemberChipColor(member.type, member.name)"
                                                          text-color="white"
                                                          size="sm"
                                                          class="member-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                          <span v-if="member.ip" class="member-separator">→</span>
                                                          <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                        </q-chip>
                                                      </div>

                                                      <!-- Group member with nested expandable structure -->
                                                      <div v-else-if="member.type === 'group' && member.expandable" class="group-member">
                                                        <div class="group-header">
                                                          <q-chip
                                                            color="amber-8"
                                                            text-color="white"
                                                            size="sm"
                                                            class="member-chip q-mr-sm">
                                                            <q-icon name="folder" class="q-mr-xs" />
                                                            <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                            <span class="member-separator">→</span>
                                                            <span class="member-count">{{ member.member_count }} members</span>
                                                          </q-chip>
                                                          <q-btn
                                                            :icon="expandedPolicyGroups[`${props.row.id}_${dst}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                                            flat dense round size="xs"
                                                            @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}_${member.name}`)" />
                                                        </div>

                                                        <!-- Nested members for this group -->
                                                        <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}_${member.name}`] && member.members" class="nested-members q-ml-md q-mt-xs">
                                                          <div v-for="(nested, nestedIndex) in member.members" :key="nestedIndex" class="nested-member q-mb-xs">
                                                            <q-chip
                                                              :color="getMemberChipColor(nested.type, nested.name)"
                                                              text-color="white"
                                                              size="xs"
                                                              class="nested-chip">
                                                              <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                              <span v-if="nested.ip" class="member-separator">→</span>
                                                              <span v-if="nested.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                            </q-chip>
                                                          </div>
                                                        </div>
                                                      </div>

                                                      <!-- Other member types -->
                                                      <div v-else class="other-member">
                                                        <q-chip
                                                          :color="getMemberChipColor(member.type, member.name)"
                                                          text-color="white"
                                                          size="sm"
                                                          class="member-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                          <span v-if="member.ip" class="member-separator">→</span>
                                                          <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                        </q-chip>
                                                      </div>
                                                    </div>
                                                  </div>
                                                </div>

                                                <!-- Fallback: Check if this is a group with old flat member details -->
                                                <div v-else-if="props.row.address_mappings && props.row.address_mappings[dst] && props.row.address_mappings[dst].member_details" class="group-details">
                                                  <!-- Group expand/collapse button -->
                                                  <div class="row items-center q-mb-sm">
                                                    <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                      {{ props.row.address_mappings[dst].member_count }} members
                                                    </q-chip>
                                                    <q-btn
                                                      :icon="expandedPolicyGroups[`${props.row.id}_${dst}`] ? 'expand_less' : 'expand_more'"
                                                      flat dense round size="sm"
                                                      @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}`)" />
                                                  </div>

                                                  <!-- Expandable member details -->
                                                  <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}`]" class="member-details">
                                                    <div v-for="(member, memberIndex) in safeParseMemberDetails(props.row.address_mappings[dst].member_details)" :key="memberIndex" class="member-item q-mb-xs">
                                                      <q-chip
                                                        :color="getMemberChipColor(member.type, member.name)"
                                                        text-color="white"
                                                        size="sm"
                                                        class="member-chip">
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                        <span class="member-separator"> → </span>
                                                        <span class="member-ip" :class="{ 'clickable-ip': member.type === 'address' }" @click.stop="member.type === 'address' ? performClickableSearch(member.ip) : null">{{ member.ip }}</span>
                                                      </q-chip>
                                                      <!-- Show nested members for groups -->
                                                      <div v-if="member.type === 'group' && member.nested_members" class="nested-members q-ml-md q-mt-xs">
                                                        <div v-for="(nested, nestedIndex) in member.nested_members" :key="nestedIndex" class="q-mb-xs">
                                                          <q-chip
                                                            :color="getMemberChipColor(nested.type, nested.name)"
                                                            text-color="white"
                                                            size="xs"
                                                            class="nested-member-chip">
                                                            <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                            <span class="member-separator"> → </span>
                                                            <span class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                          </q-chip>
                                                        </div>
                                                      </div>
                                                    </div>
                                                  </div>
                                                </div>
                                                <!-- Regular IP display for non-groups -->
                                                <div v-else class="address-ips">
                                                  <div v-for="ip in getAddressDisplay(dst, props.row).ip.split(', ')" :key="ip" class="ip-item q-mb-xs">
                                                    <span class="ip-bullet">•</span>
                                                    <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(ip.trim()) }" @click.stop="performClickableSearch(ip.trim())">{{ ip.trim() }}</span>
                                                  </div>
                                                </div>
                                              </q-card-section>
                                            </q-card>
                                          </div>
                                        </div>
                                      </q-card-section>
                                    </q-card>
                                  </div>

                                  <!-- Services Section -->
                                  <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                    <q-card flat bordered>
                                      <q-card-section class="bg-grey-2">
                                        <div class="text-subtitle1 text-weight-bold text-grey-8">
                                          <q-icon name="settings" class="q-mr-sm" />
                                          Services
                                        </div>
                                      </q-card-section>
                                      <q-card-section>
                                        <div class="q-gutter-sm">
                                          <div v-for="(svc, index) in JSON.parse(props.row.services || '[]')" :key="svc + index" class="service-card">
                                            <q-card flat bordered class="q-mb-sm">
                                              <q-card-section class="q-pa-sm">
                                                <q-chip color="blue" dense text-color="white" icon="settings" class="q-mb-xs">
                                                  {{ svc }}
                                                </q-chip>
                                              </q-card-section>
                                            </q-card>
                                          </div>
                                        </div>
                                      </q-card-section>
                                    </q-card>
                                  </div>

                                  <!-- Match Details Section -->
                                  <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                    <q-card flat bordered class="bg-positive-1">
                                      <q-card-section class="bg-grey-2">
                                        <div class="text-subtitle1 text-weight-bold text-grey-8">
                                          <q-icon name="verified" class="q-mr-sm" />
                                          Match Details
                                        </div>
                                      </q-card-section>
                                      <q-card-section>
                                        <div v-if="props.row.match_details">
                                          <div v-if="props.row.match_details.source.length > 0" class="q-mb-sm">
                                            <div class="text-body2">
                                              <strong class="text-positive">Source Matches:</strong>
                                              <div class="q-mt-xs">
                                                <q-chip
v-for="match in props.row.match_details.source" :key="match"
                                                  color="positive" dense size="md" text-color="white" class="q-mr-xs q-mb-xs">
                                                  {{ match }}
                                                </q-chip>
                                              </div>
                                            </div>
                                          </div>
                                          <div v-if="props.row.match_details.destination.length > 0" class="q-mb-sm">
                                            <div class="text-body2">
                                              <strong class="text-positive">Destination Matches:</strong>
                                              <div class="q-mt-xs">
                                                <q-chip
v-for="match in props.row.match_details.destination" :key="match"
                                                  color="positive" dense size="md" text-color="white" class="q-mr-xs q-mb-xs">
                                                  {{ match }}
                                                </q-chip>
                                              </div>
                                            </div>
                                          </div>
                                          <div v-if="(!props.row.match_details.source || props.row.match_details.source.length === 0) && (!props.row.match_details.destination || props.row.match_details.destination.length === 0)" class="text-body2 text-grey-6">
                                            No direct matches found
                                          </div>
                                        </div>
                                        <div v-else class="text-body2 text-grey-6">
                                          No match details available
                                        </div>
                                      </q-card-section>
                                    </q-card>
                                  </div>

                                  <!-- Policy Info Section -->
                                  <div v-if="!searchResults.is_bulk" class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                    <q-card flat bordered>
                                      <q-card-section class="bg-grey-2">
                                        <div class="text-subtitle1 text-weight-bold text-grey-8">
                                          <q-icon name="info" class="q-mr-sm" />
                                          Policy Information
                                        </div>
                                      </q-card-section>
                                      <q-card-section>
                                        <div class="q-gutter-sm">
                                          <div class="policy-info-item">
                                            <span class="info-label">Environment:</span>
                                            <q-chip :color="getEnvironmentColor(props.row.environment)" dense size="md" text-color="white">
                                              <q-icon v-if="props.row.config_type === 'paloalto' && props.row.environment !== 'Admin FW'" name="security" size="sm" class="q-mr-xs"/>
                                              {{ props.row.environment }}
                                            </q-chip>
                                          </div>
                                          <div class="policy-info-item q-mt-sm">
                                            <span class="info-label">Action:</span>
                                            <q-chip :color="props.row.action === 'accept' ? 'positive' : 'negative'" dense size="md" text-color="white">
                                              {{ props.row.action }}
                                            </q-chip>
                                          </div>
                                          <div v-if="props.row.source_zone || props.row.destination_zone" class="policy-info-item q-mt-sm">
                                            <span class="info-label">Zones:</span>
                                            <div class="zone-info q-mt-xs">
                                              <q-chip v-if="props.row.source_zone" :color="getZoneColor(props.row.source_zone)" dense size="md" text-color="white" class="q-mr-xs">
                                                From: {{ props.row.source_zone }}
                                              </q-chip>
                                              <q-chip v-if="props.row.destination_zone" :color="getZoneColor(props.row.destination_zone)" dense size="md" text-color="white">
                                                To: {{ props.row.destination_zone }}
                                              </q-chip>
                                            </div>
                                          </div>
                                        </div>
                                      </q-card-section>
                                    </q-card>
                                  </div>
                                </div>
                              </div>
                            </q-td>
                          </q-tr>
                        </template>
                      </q-table>
                    </div>
                  </div>
                </q-tab-panel>
                
                <!-- LTM tab for this IP -->
                <q-tab-panel name="ltm" class="ltm-result">
                  <!-- Inline LTM results display -->
                  <div v-if="!result.ltm_results || (!result.ltm_results.virtual_servers?.length && !result.ltm_results.pools_and_nodes?.length)">
                    <q-card flat class="text-center q-pa-lg">
                      <q-icon name="info" size="56px" color="grey-5" />
                      <div class="text-h6 q-mt-sm text-grey-7">No LTM matches found</div>
                      <div class="text-body2 text-grey-6">The IP address was not found in any virtual servers or pool nodes</div>
                    </q-card>
                  </div>
                  <!-- Show full LTM results with tree structure -->
                  <div v-else>
                    <div v-if="result.ltm_results.virtual_servers && result.ltm_results.virtual_servers.length > 0" class="ltm-tree-container">
                      <!-- Group Virtual Servers by VS for display -->
                      <div v-for="vs in result.ltm_results.virtual_servers" :key="vs.virtual_server.id" class="ltm-vs-group">
                        <!-- Virtual Server -->
                        <div class="ltm-tree-item ltm-vs-item">
                          <div class="ltm-item-indicator">
                            <div class="ltm-status-dot" :class="getStatusClass(vs.virtual_server.status, vs.virtual_server.enabled)"></div>
                          </div>
                          <div class="ltm-item-content">
                            <div class="ltm-vs-header">
                              <div class="ltm-item-name ltm-clickable" @click.stop="performClickableSearch(vs.virtual_server.name)">{{ cleanName(vs.virtual_server.name) }}</div>
                              <q-chip v-if="vs.virtual_server.environment" :color="getEnvironmentColor(vs.virtual_server.environment)" dense size="md" text-color="white" class="ltm-environment-chip">
                                {{ vs.virtual_server.environment }}
                              </q-chip>
                            </div>
                            <div v-if="vs.virtual_server.destination_ip" class="ltm-item-details">
                              <span class="ltm-clickable" @click.stop="performClickableSearch(cleanIp(vs.virtual_server.destination_ip))">{{ cleanIp(vs.virtual_server.destination_ip) }}</span>:{{ vs.virtual_server.destination_port }}
                            </div>
                          </div>
                        </div>

                        <!-- Pool -->
                        <div v-if="vs.virtual_server.pool_name" class="ltm-tree-item ltm-pool-item">
                          <div class="ltm-item-indicator">
                            <div class="ltm-status-dot enabled"></div>
                          </div>
                          <div class="ltm-item-content">
                            <div class="ltm-item-name ltm-clickable" @click.stop="performClickableSearch(vs.virtual_server.pool_name)">{{ cleanName(vs.virtual_server.pool_name) }}</div>
                          </div>
                        </div>

                        <!-- Pool Nodes/Members -->
                        <div v-for="node in vs.pool_nodes" :key="node.id || `${node.ip_address}-${node.port}`" class="ltm-tree-item ltm-node-item">
                          <div class="ltm-item-indicator">
                            <div class="ltm-status-dot" :class="getNodeStatusClass(node.status)"></div>
                          </div>
                          <div class="ltm-item-content">
                            <div class="ltm-item-name">
                              <span class="ltm-clickable" @click.stop="performClickableSearch(node.ip_address)">{{ cleanIp(node.ip_address) }}</span>:{{ node.port }}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </q-tab-panel>
                
                <!-- FQDN tab for this IP -->
                <q-tab-panel v-if="result.fqdn_results && result.fqdn_results.success && result.fqdn_results.count > 0" name="fqdn">
                  <q-card flat>
                    <q-card-section class="q-pa-none">
                      <q-table
                        :rows="result.fqdn_results.records"
                        :columns="fqdnColumns"
                        :row-key="(row) => `${row.fqdn}-${row.ip}-${row.type}`"
                        dense
                        flat
                        :rows-per-page-options="[25, 50, 100, 200, 500]"
                        :pagination="{ rowsPerPage: 100 }"
                        class="fqdn-table">
                        
                        <template #body-cell-fqdn="props">
                          <q-td :props="props" class="text-weight-bold">
                            <span class="fqdn-clickable" @click.stop="performClickableSearch(props.row.fqdn)">{{ props.row.fqdn }}</span>
                          </q-td>
                        </template>
                        
                        <template #body-cell-ip="props">
                          <q-td :props="props">
                            <span class="ip-clickable" @click.stop="performClickableSearch(props.row.ip)">{{ props.row.ip }}</span>
                          </q-td>
                        </template>
                        
                        <template #body-cell-type="props">
                          <q-td :props="props">
                            <q-chip :color="props.row.type === 'A' ? 'green' : 'orange'" dense size="md" text-color="white">
                              {{ props.row.type }}
                            </q-chip>
                          </q-td>
                        </template>
                      </q-table>
                    </q-card-section>
                  </q-card>
                </q-tab-panel>
              </q-tab-panels>
            </q-card-section>
            
            <q-card-section v-else class="text-center text-grey-6">
              No matches found for {{ ip }}
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Regular Search Results -->
      <div v-if="searchResults && !searchResults.is_bulk" class="result-tabs">
        <q-card>
          <!-- Single IP Classification Header -->
          <q-card-section v-if="searchResults.search_type === 'ip' && searchResults.ip_classification" class="bg-blue-grey-1">
            <div class="text-h6">{{ formatIpWithClassification(searchResults.ip_address, searchResults.ip_classification) }}</div>
            <div class="text-subtitle2">
              {{ searchResults.summary.total_matches }} total matches 
              ({{ searchResults.summary.ltm_matches }} LTM, {{ searchResults.summary.firewall_matches }} Firewall, {{ searchResults.summary.fqdn_matches }} FQDN)
            </div>
          </q-card-section>
          
          <q-separator v-if="searchResults.search_type === 'ip' && searchResults.ip_classification" />
          
          <q-tabs
v-model="activeTab" dense class="text-grey" active-color="primary" indicator-color="primary"
            align="left">
            <q-tab v-if="searchResults.search_type !== 'fqdn'" name="firewall" :label="`Firewall Results (${searchResults.summary.firewall_matches || 0})`" />
            <q-tab v-if="searchResults.search_type !== 'fqdn'" name="ltm" :label="`LTM Results (${searchResults.summary.ltm_matches || 0})`" />
            <q-tab v-if="searchResults.search_type !== 'fqdn'" name="fqdn" :label="`FQDN Results (${(searchResults.summary.fqdn_matches || 0) + (searchResults.summary.object_fqdn_matches || 0) + (searchResults.summary.vs_mapping_fqdn_matches || 0) + getMappedFqdnCount()})`" />
            <q-tab v-if="searchResults.search_type === 'fqdn'" name="fqdn" :label="`FQDN Results (${(searchResults.summary.fqdn_matches || 0) + (searchResults.summary.object_fqdn_matches || 0) + (searchResults.summary.vs_mapping_fqdn_matches || 0) + getMappedFqdnCount()})`" />
          </q-tabs>

          <q-separator />

          <q-tab-panels v-model="activeTab" animated>
            <!-- LTM Results Tab -->
            <q-tab-panel name="ltm" class="ltm-result">
              <div
                v-if="!searchResults.ltm_results || (!searchResults.ltm_results.virtual_servers?.length && !searchResults.ltm_results.pools_and_nodes?.length)">
                <q-card flat class="text-center q-pa-lg">
                  <q-icon name="info" size="56px" color="grey-5" />
                  <div class="text-h6 q-mt-sm text-grey-7">No LTM matches found</div>
                  <div class="text-body2 text-grey-6">The IP address was not found in any virtual servers or pool nodes
                  </div>
                </q-card>
              </div>

              <!-- LTM Results Display - Tree Structure -->
              <div
                v-if="searchResults.ltm_results && searchResults.ltm_results.virtual_servers?.length > 0"
                class="ltm-tree-container">
                
                <!-- Group Virtual Servers by VS for display -->
                <div v-for="vs in filteredLtmResults" :key="vs.virtual_server.id" class="ltm-vs-group">
                  <!-- Virtual Server -->
                  <div class="ltm-tree-item ltm-vs-item">
                    <div class="ltm-item-indicator">
                      <div class="ltm-status-dot" :class="getStatusClass(vs.virtual_server.status, vs.virtual_server.enabled)"></div>
                    </div>
                    <div class="ltm-item-content">
                      <div class="ltm-vs-header">
                        <div class="ltm-item-name ltm-clickable" @click.stop="performClickableSearch(vs.virtual_server.name)">{{ cleanName(vs.virtual_server.name) }}</div>
                        <q-chip v-if="vs.virtual_server.environment" :color="getEnvironmentColor(vs.virtual_server.environment)" dense size="md" text-color="white" class="ltm-environment-chip">
                          {{ vs.virtual_server.environment }}
                        </q-chip>
                      </div>
                      <div v-if="vs.virtual_server.destination_ip" class="ltm-item-details">
                        <span class="ltm-clickable" @click.stop="performClickableSearch(cleanIp(vs.virtual_server.destination_ip))">{{ cleanIp(vs.virtual_server.destination_ip) }}</span>:{{ vs.virtual_server.destination_port }}
                      </div>
                    </div>
                  </div>

                  <!-- Pool -->
                  <div v-if="vs.virtual_server.pool_name" class="ltm-tree-item ltm-pool-item">
                    <div class="ltm-item-indicator">
                      <div class="ltm-status-dot enabled"></div>
                    </div>
                    <div class="ltm-item-content">
                      <div class="ltm-item-name ltm-clickable" @click.stop="performClickableSearch(vs.virtual_server.pool_name)">{{ cleanName(vs.virtual_server.pool_name) }}</div>
                    </div>
                  </div>

                  <!-- Pool Nodes/Members -->
                  <div v-for="node in vs.pool_nodes" :key="node.id || `${node.ip_address}-${node.port}`" class="ltm-tree-item ltm-node-item">
                    <div class="ltm-item-indicator">
                      <div class="ltm-status-dot" :class="getNodeStatusClass(node.status)"></div>
                    </div>
                    <div class="ltm-item-content">
                      <div class="ltm-item-name">
                        <span class="ltm-clickable" @click.stop="performClickableSearch(node.ip_address)">{{ cleanIp(node.ip_address) }}</span>:{{ node.port }}
                      </div>
                    </div>
                  </div>
                </div>

              </div>
            </q-tab-panel>

            <!-- Firewall Results Tab -->
            <q-tab-panel name="firewall" class="fw-result">
              <div
                v-if="!searchResults.firewall_results || !searchResults.firewall_results.policies || searchResults.firewall_results.policies.length === 0">
                <q-card flat class="text-center q-pa-lg">
                  <q-icon name="security" size="56px" color="grey-5" />
                  <div class="text-h6 q-mt-sm text-grey-7">No firewall policies found</div>
                  <div class="text-body2 text-grey-6">The IP address was not found in any firewall policies</div>
                </q-card>
              </div>

              <!-- Address Objects -->
              <div
                v-if="searchResults.firewall_results && searchResults.firewall_results.address_objects && searchResults.firewall_results.address_objects.length > 0"
                class="q-mb-lg">
                <div class="text-h6 q-mb-md">Matching Address Objects</div>
                <!-- Infrastructure Mapping Table -->
                <div class="q-mb-lg">
                  <div class="text-subtitle1 q-mb-sm">Infrastructure Mapping</div>
                  <q-table
                    :columns="addressObjectsColumns"
                    :rows="filteredAddressObjects"
                    row-key="id"
                    flat
                    bordered
                    dense
                    :pagination="{ rowsPerPage: 10 }"
                    class="infrastructure-mapping-table">
                    <template v-slot:body-cell-name="props">
                      <q-td :props="props">
                        <q-chip
                          :color="props.row.object_type === 'group' ? 'blue-3' : getCidrGreenColor(props.row.cidr_notation || (props.row.ip_address && props.row.object_type === 'host' ? props.row.ip_address + '/32' : props.row.ip_address))"
                          text-color="black" dense>
                          {{ props.row.name }}
                          <q-tooltip v-if="props.row.object_type === 'group'">
                            Address Group with {{ props.row.member_count || 0 }} members
                          </q-tooltip>
                        </q-chip>
                      </q-td>
                    </template>
                    <template v-slot:body-cell-environment="props">
                      <q-td :props="props">
                        <q-chip
                          :color="getEnvironmentColor(props.row.environment)"
                          text-color="white" dense>
                          {{ props.row.environment }}
                        </q-chip>
                      </q-td>
                    </template>
                    <template v-slot:body-cell-config_type="props">
                      <q-td :props="props">
                        <q-chip
                          :color="props.row.config_type === 'fortigate' ? 'orange-6' : 'blue-6'"
                          text-color="white" dense>
                          {{ props.row.config_type === 'fortigate' ? 'FortiGate' : 'Palo Alto' }}
                        </q-chip>
                      </q-td>
                    </template>
                  </q-table>
                </div>
              </div>

              <!-- Address Groups -->
              <div
                v-if="searchResults.firewall_results && searchResults.firewall_results.address_groups && searchResults.firewall_results.address_groups.length > 0"
                class="q-mb-lg">
                <div class="text-h6 q-mb-md">
                  Matching Address Groups
                  <q-chip dense color="primary" text-color="white" class="q-ml-sm">
                    {{ filteredAddressGroups.length }} total
                  </q-chip>
                </div>

                <!-- Infrastructure Mapping Table -->
                <div class="q-mb-lg">
                  <div class="text-subtitle1 q-mb-sm">Infrastructure Mapping</div>
                  <q-table
                    :columns="infrastructureMappingColumns"
                    :rows="filteredAddressGroups"
                    row-key="id"
                    flat
                    bordered
                    dense
                    :pagination="{ rowsPerPage: 25 }"
                    :rows-per-page-options="[10, 25, 50, 100]"
                    class="infrastructure-mapping-table">
                    <template v-slot:body-cell-expand="props">
                      <q-td :props="props">
                        <q-btn
                          :icon="expandedGroups[props.row.id] ? 'expand_less' : 'expand_more'"
                          v-if="props.row.member_details || JSON.parse(props.row.members || '[]').length > 0"
                          flat dense round size="sm"
                          @click="toggleGroupExpansion(props.row.id)" />
                      </q-td>
                    </template>
                    <template v-slot:body-cell-name="props">
                      <q-td :props="props">
                        <q-chip
                          color="indigo-7"
                          text-color="white"
                          class="clickable-group"
                          @click.stop="performClickableSearch(props.value)">
                          {{ props.value }}
                        </q-chip>
                      </q-td>
                    </template>
                    <template v-slot:body-cell-member_count="props">
                      <q-td :props="props">
                        <q-badge color="blue-grey-7" :label="props.value || JSON.parse(props.row.members || '[]').length" />
                      </q-td>
                    </template>
                    <template v-slot:body-cell-environment="props">
                      <q-td :props="props">
                        <q-badge
                          :color="getEnvironmentColor(props.value)"
                          :label="props.value || 'Unknown'"
                          class="text-weight-medium" />
                      </q-td>
                    </template>
                    <template v-slot:body="props">
                      <q-tr :props="props">
                        <q-td v-for="col in props.cols" :key="col.name" :props="props">
                          <template v-if="col.name === 'expand'">
                            <q-btn
                              :icon="expandedGroups[props.row.id] ? 'expand_less' : 'expand_more'"
                              v-if="props.row.member_details || JSON.parse(props.row.members || '[]').length > 0"
                              flat dense round size="sm"
                              @click="toggleGroupExpansion(props.row.id)" />
                          </template>
                          <template v-else-if="col.name === 'name'">
                            <q-chip
                              color="indigo-7"
                              text-color="white"
                              class="clickable-group"
                              @click.stop="performClickableSearch(col.value)">
                              {{ col.value }}
                            </q-chip>
                          </template>
                          <template v-else-if="col.name === 'member_count'">
                            <q-badge color="blue-grey-7" :label="col.value || JSON.parse(props.row.members || '[]').length" />
                          </template>
                          <template v-else-if="col.name === 'environment'">
                            <q-badge
                              :color="getEnvironmentColor(col.value)"
                              :label="col.value || 'Unknown'"
                              class="text-weight-medium" />
                          </template>
                          <template v-else>
                            {{ col.value }}
                          </template>
                        </q-td>
                      </q-tr>
                      <!-- Expandable row for member details -->
                      <q-tr v-if="expandedGroups[props.row.id]" :props="props">
                        <q-td colspan="100%" class="q-pa-md bg-blue-grey-1">
                          <div v-if="props.row.member_details" class="member-details">
                            <!-- Member Controls -->
                            <div class="member-controls q-mb-sm">
                              <div class="row items-center q-gutter-sm">
                                <div class="text-subtitle2 text-blue-grey-7">Member Details:</div>
                                <q-input
                                  v-model="groupSearchFilters[props.row.id]"
                                  dense outlined
                                  placeholder="Filter members..."
                                  class="col-auto"
                                  style="min-width: 200px;"
                                  clearable
                                  debounce="300">
                                  <template v-slot:prepend>
                                    <q-icon name="search" />
                                  </template>
                                </q-input>
                                <q-btn
                                  v-if="getFilteredMembers(props.row.member_details, props.row.id).length > 50"
                                  :label="showAllMembers[props.row.id] ? `Show Less (${getFilteredMembers(props.row.member_details, props.row.id).length})` : `Show All (${getFilteredMembers(props.row.member_details, props.row.id).length})`"
                                  :color="showAllMembers[props.row.id] ? 'orange-7' : 'green-7'"
                                  size="sm"
                                  outline
                                  @click="toggleShowAllMembers(props.row.id)" />
                                <div v-if="groupSearchFilters[props.row.id]" class="text-caption text-blue-grey-6">
                                  {{ getDisplayedMembers(props.row.member_details, props.row.id).length }} of {{ getFilteredMembers(props.row.member_details, props.row.id).length }} members
                                </div>
                              </div>
                            </div>
                            <div v-for="(member, index) in getDisplayedMembers(props.row.member_details, props.row.id)" :key="index" class="member-item q-mb-xs">
                              <div class="member-row">
                                <q-chip
                                  :color="getMemberChipColor(member.type, member.name)"
                                  text-color="white"
                                  size="sm"
                                  class="member-chip">
                                  <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                  <span class="member-separator"> → </span>
                                  <span class="member-ip" :class="{ 'clickable-ip': member.type === 'address' }" @click.stop="member.type === 'address' ? performClickableSearch(member.ip) : null">{{ member.ip }}</span>
                                </q-chip>
                                <!-- Expand button for groups with nested members -->
                                <q-btn
                                  v-if="member.type === 'group' && member.nested_members"
                                  :icon="expandedNestedGroups[`${props.row.id}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                  flat dense round size="xs"
                                  class="q-ml-xs"
                                  @click="toggleNestedGroupExpansion(`${props.row.id}_${member.name}`)" />
                              </div>
                              <!-- Show nested members for groups (when expanded) -->
                              <div v-if="member.type === 'group' && member.nested_members && expandedNestedGroups[`${props.row.id}_${member.name}`]" class="nested-members q-ml-md q-mt-xs">
                                <div v-for="(nested, nestedIndex) in member.nested_members" :key="nestedIndex" class="q-mb-xs">
                                  <q-chip
                                    :color="getMemberChipColor(nested.type, nested.name)"
                                    text-color="white"
                                    size="xs"
                                    outline>
                                    <span class="nested-member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                    <span class="member-separator"> → </span>
                                    <span class="nested-member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                  </q-chip>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div v-else class="text-body2 text-grey-6">
                            No detailed member information available for this group.
                          </div>
                        </q-td>
                      </q-tr>
                    </template>
                  </q-table>
                </div>

              </div>

              <!-- Firewall Policies Table -->
              <div
                v-if="searchResults.firewall_results && searchResults.firewall_results.policies && searchResults.firewall_results.policies.length > 0">
                <div class="text-h6 q-mb-md">Firewall Policies</div>
                <div class="firewall-table-container">
                  <q-table
v-model:pagination="pagination" :rows="uniquePolicies"
                    :columns="firewallColumns" :expanded="expandedPolicies" bordered class="firewall-policy-table" flat
                    row-key="id" :sort-method="customSort"
                    binary-state-sort @update:expanded="expandedPolicies = $event">
                    <template #header="props">
                      <q-tr :props="props" class="bg-blue-grey-1">
                        <q-th v-for="col in props.cols" :key="col.name" :props="props" 
                          class="text-weight-bold sortable-header" 
                          :style="{ width: getColumnWidth(col.name), textAlign: col.align }"
                          :class="{ 'cursor-pointer': col.sortable !== false }"
                          @click="col.sortable !== false ? props.sort(col.field) : null">
                          <div class="row items-center no-wrap">
                            <span>{{ col.label }}</span>
                            <q-space />
                            <q-icon v-if="col.sortable !== false && props.sort === col.field" 
                              :name="props.descending ? 'arrow_downward' : 'arrow_upward'" 
                              size="20px" class="q-ml-xs" />
                          </div>
                        </q-th>
                      </q-tr>
                    </template>

                    <template #body="props">
                      <q-tr :props="props">
                        <q-td key="expand" :props="props" :style="{ width: getColumnWidth('expand'), textAlign: 'center' }">
                          <q-btn
:icon="props.expand ? 'remove' : 'add'" color="primary" dense round size="md"
                            @click="props.expand = !props.expand" />
                        </q-td>

                        <q-td key="environment" :props="props" :style="{ width: getColumnWidth('environment'), textAlign: 'center' }">
                          <q-chip
:color="getEnvironmentColor(props.row.environment)" dense size="md"
                            text-color="white" class="environment-chip">
                            <q-icon v-if="props.row.config_type === 'paloalto' && props.row.environment !== 'Admin FW'" name="security" size="sm" class="q-mr-xs"/>
                            {{ props.row.environment }}
                          </q-chip>
                        </q-td>

                        <q-td key="source_zone" :props="props" class="zone-column" :style="{ width: getColumnWidth('source_zone'), textAlign: 'center' }">
                          <q-chip v-if="props.row.source_zone" :color="getZoneColor(props.row.source_zone)" text-color="white" dense size="md">
                            {{ props.row.source_zone }}
                          </q-chip>
                          <span v-else class="text-grey-6 text-caption">-</span>
                        </q-td>

                        <q-td key="destination_zone" :props="props" class="zone-column" :style="{ width: getColumnWidth('destination_zone'), textAlign: 'center' }">
                          <q-chip v-if="props.row.destination_zone" :color="getZoneColor(props.row.destination_zone)" text-color="white" dense size="md">
                            {{ props.row.destination_zone }}
                          </q-chip>
                          <span v-else class="text-grey-6 text-caption">-</span>
                        </q-td>

                        <q-td key="policy_id" :props="props" :style="{ width: getColumnWidth('policy_id'), textAlign: 'center' }">
                          {{ props.row.policy_id }}
                        </q-td>

                        <q-td key="name" :props="props" :style="{ width: getColumnWidth('name'), textAlign: 'left' }" class="policy-name-cell">
                          <div class="policy-name-text">{{ props.row.name || 'Unnamed Policy' }}</div>
                        </q-td>

                        <q-td key="source_addresses" :props="props" class="source-column" :style="{ width: getColumnWidth('source_addresses'), textAlign: 'left' }">
                          <div class="address-preview">
                            <div class="chips-container">
                              <q-chip
v-for="(src, index) in JSON.parse(props.row.source_addresses || '[]')"
                                :key="src + index"
                                :color="props.row.match_details && props.row.match_details.source.includes(src) ? getMatchedAddressColor(src, props.row.address_mappings) : 'grey'"
                                class="address-chip clickable-group" dense size="md" text-color="white" @click.stop="performClickableSearch(src)">
                                {{ src }}
                              </q-chip>
                            </div>
                          </div>
                        </q-td>

                        <q-td key="destination_addresses" :props="props" class="destination-column" :style="{ width: getColumnWidth('destination_addresses'), textAlign: 'left' }">
                          <div class="address-preview">
                            <div class="chips-container">
                              <q-chip
                                v-if="JSON.parse(props.row.destination_addresses || '[]').length === 0"
                                color="orange-7" dense size="md" text-color="white" class="address-chip">
                                any
                              </q-chip>
                              <q-chip
                                v-for="(dst, index) in JSON.parse(props.row.destination_addresses || '[]')"
                                :key="dst + index"
                                :color="props.row.match_details && props.row.match_details.destination.includes(dst) ? getMatchedAddressColor(dst, props.row.address_mappings) : 'grey'"
                                class="address-chip clickable-group" dense size="md" text-color="white" @click.stop="performClickableSearch(dst)">
                                {{ dst }}
                              </q-chip>
                            </div>
                          </div>
                        </q-td>

                        <q-td key="services" :props="props" class="services-column" :style="{ width: getColumnWidth('services'), textAlign: 'left' }">
                          <div class="address-preview">
                            <div class="chips-container">
                              <q-chip
v-for="(svc, index) in JSON.parse(props.row.services || '[]')"
                                :key="svc + index" class="service-chip" color="blue" dense size="md"
                                text-color="white">
                                {{ svc }}
                              </q-chip>
                            </div>
                          </div>
                        </q-td>

                        <q-td key="match_details" :props="props" class="match-details-column" :style="{ width: getColumnWidth('match_details'), textAlign: 'left' }">
                          <div class="match-details-preview">
                            <div v-if="props.row.match_details">
                              <div v-if="props.row.match_details.source && props.row.match_details.source.length > 0" class="q-mb-xs">
                                <div class="text-caption text-weight-bold text-positive">Source:</div>
                                <div class="chips-container">
                                  <q-chip
v-for="match in props.row.match_details.source" :key="match"
                                    color="positive" dense size="sm" text-color="white" class="q-mr-xs q-mb-xs">
                                    {{ match }}
                                  </q-chip>
                                </div>
                              </div>
                              <div v-if="props.row.match_details.destination && props.row.match_details.destination.length > 0" class="q-mb-xs">
                                <div class="text-caption text-weight-bold text-positive">Destination:</div>
                                <div class="chips-container">
                                  <q-chip
v-for="match in props.row.match_details.destination" :key="match"
                                    color="positive" dense size="sm" text-color="white" class="q-mr-xs q-mb-xs">
                                    {{ match }}
                                  </q-chip>
                                </div>
                              </div>
                              <div v-if="(!props.row.match_details.source || props.row.match_details.source.length === 0) && (!props.row.match_details.destination || props.row.match_details.destination.length === 0)" class="text-caption text-grey-6">
                                No matches
                              </div>
                            </div>
                            <div v-else class="text-caption text-grey-6">
                              No details
                            </div>
                          </div>
                        </q-td>

                        <q-td key="action" :props="props" :style="{ width: getColumnWidth('action'), textAlign: 'center' }">
                          <q-chip
:color="props.row.action === 'accept' ? 'positive' : 'negative'" dense size="md"
                            text-color="white">
                            {{ props.row.action }}
                          </q-chip>
                        </q-td>
                      </q-tr>

                      <!-- Expanded Row with enhanced detail -->
                      <q-tr v-show="props.expand" :props="props" class="bg-blue-grey-1">
                        <q-td colspan="100%">
                          <div class="q-pa-md">
                            <!-- Policy Details Header -->
                            <div class="row q-mb-md">
                              <div class="col-12">
                                <div class="text-h6 text-primary q-mb-sm">
                                  Policy {{ props.row.policy_id }} - {{ props.row.name || 'Unnamed Policy' }}
                                </div>
                                <q-separator />
                              </div>
                            </div>

                            <!-- Detailed Information Sections - 4 Column Layout -->
                            <div class="row q-gutter-md policy-details-row">
                              <!-- Source Addresses Section -->
                              <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                <q-card flat bordered>
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="input" class="q-mr-sm" />
                                      Source Addresses
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div class="q-gutter-sm">
                                      <!-- Any/All addresses case -->
                                      <div v-if="JSON.parse(props.row.source_addresses || '[]').length === 0" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <q-chip color="orange-7" dense text-color="white" icon="info" class="q-mb-xs">
                                              any
                                            </q-chip>
                                            <div class="address-ips">
                                              <span class="ip-item">All source addresses allowed</span>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                      
                                      <!-- Specific addresses -->
                                      <div v-for="(src, index) in JSON.parse(props.row.source_addresses || '[]')" :key="src + index" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <div class="address-header">
                                              <q-chip
                                                :color="props.row.match_details && props.row.match_details.source.includes(src) ? getMatchedAddressColor(src, props.row.address_mappings) : 'blue-grey-6'"
                                                :icon="props.row.match_details && props.row.match_details.source.includes(src) ? 'verified' : 'info'"
                                                dense text-color="white" class="q-mb-xs clickable-group" @click.stop="performClickableSearch(src)">
                                                {{ src }}
                                              </q-chip>
                                            </div>
                                            <!-- Check if this is a group with hierarchical member details -->
                                            <div v-if="props.row.address_mappings && props.row.address_mappings[src] && props.row.address_mappings[src].hierarchical_members" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[src].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${src}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${src}`)" />
                                              </div>

                                              <!-- Expandable hierarchical member details -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${src}`]" class="member-details">
                                                <div v-for="(member, memberIndex) in safeParseHierarchicalMembers(props.row.address_mappings[src].hierarchical_members)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <!-- Individual address member -->
                                                  <div v-if="member.type === 'address'" class="address-member">
                                                    <q-chip
                                                      :color="getMemberChipColor(member.type, member.name)"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.ip" class="member-separator">→</span>
                                                      <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                    </q-chip>
                                                  </div>

                                                  <!-- Group member with nested expandable structure -->
                                                  <div v-else-if="member.type === 'group' && member.expandable" class="group-member">
                                                    <div class="group-header">
                                                      <q-chip
                                                        color="amber-8"
                                                        text-color="white"
                                                        size="sm"
                                                        class="member-chip q-mr-sm">
                                                        <q-icon name="folder" class="q-mr-xs" />
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                        <span class="member-separator">→</span>
                                                        <span class="member-count">{{ member.member_count }} members</span>
                                                      </q-chip>
                                                      <q-btn
                                                        :icon="expandedPolicyGroups[`${props.row.id}_${src}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                                        flat dense round size="xs"
                                                        @click="togglePolicyGroupExpansion(`${props.row.id}_${src}_${member.name}`)" />
                                                    </div>

                                                    <!-- Nested members for this group -->
                                                    <div v-if="expandedPolicyGroups[`${props.row.id}_${src}_${member.name}`] && member.members" class="nested-members q-ml-md q-mt-xs">
                                                      <div v-for="(nested, nestedIndex) in member.members" :key="nestedIndex" class="nested-member q-mb-xs">
                                                        <q-chip
                                                          :color="getMemberChipColor(nested.type, nested.name)"
                                                          text-color="white"
                                                          size="xs"
                                                          class="nested-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                          <span v-if="nested.ip" class="member-separator">→</span>
                                                          <span v-if="nested.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                        </q-chip>
                                                      </div>
                                                    </div>
                                                  </div>

                                                  <!-- Non-expandable group member -->
                                                  <div v-else-if="member.type === 'group'" class="group-member">
                                                    <q-chip
                                                      color="amber-8"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <q-icon name="folder" class="q-mr-xs" />
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.member_count" class="member-separator">→</span>
                                                      <span v-if="member.member_count" class="member-count">{{ member.member_count }} members</span>
                                                    </q-chip>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>

                                            <!-- Fallback: Check if this is a group with flat member details -->
                                            <div v-else-if="props.row.address_mappings && props.row.address_mappings[src] && props.row.address_mappings[src].member_details" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[src].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${src}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${src}`)" />
                                              </div>

                                              <!-- Expandable member details (fallback) -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${src}`]" class="member-details">
                                                <!-- Member Controls -->
                                                <div class="member-controls q-mb-sm">
                                                  <div class="row items-center q-gutter-sm">
                                                    <div class="text-subtitle2 text-blue-grey-7">Member Details:</div>
                                                    <q-input
                                                      v-model="groupSearchFilters[`${props.row.id}_${src}`]"
                                                      dense outlined
                                                      placeholder="Filter members..."
                                                      class="col-auto"
                                                      style="min-width: 200px;"
                                                      clearable
                                                      debounce="300">
                                                      <template v-slot:prepend>
                                                        <q-icon name="search" />
                                                      </template>
                                                    </q-input>
                                                    <q-btn
                                                      v-if="getPolicyFilteredMembers(props.row.address_mappings[src].member_details, `${props.row.id}_${src}`).length > 50"
                                                      :label="showAllMembers[`${props.row.id}_${src}`] ? `Show Less (${getPolicyFilteredMembers(props.row.address_mappings[src].member_details, `${props.row.id}_${src}`).length})` : `Show All (${getPolicyFilteredMembers(props.row.address_mappings[src].member_details, `${props.row.id}_${src}`).length})`"
                                                      :color="showAllMembers[`${props.row.id}_${src}`] ? 'orange-7' : 'green-7'"
                                                      size="sm"
                                                      outline
                                                      @click="toggleShowAllMembers(`${props.row.id}_${src}`)" />
                                                    <div v-if="groupSearchFilters[`${props.row.id}_${src}`]" class="text-caption text-blue-grey-6">
                                                      {{ getPolicyDisplayedMembers(props.row.address_mappings[src].member_details, `${props.row.id}_${src}`).length }} of {{ getPolicyFilteredMembers(props.row.address_mappings[src].member_details, `${props.row.id}_${src}`).length }} members
                                                    </div>
                                                  </div>
                                                </div>
                                                <div v-for="(member, memberIndex) in getPolicyDisplayedMembers(props.row.address_mappings[src].member_details, `${props.row.id}_${src}`)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <q-chip
                                                    :color="getMemberChipColor(member.type, member.name)"
                                                    text-color="white"
                                                    size="sm"
                                                    class="member-chip">
                                                    <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                    <span v-if="member.ip" class="member-separator">→</span>
                                                    <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                  </q-chip>
                                                </div>
                                              </div>
                                            </div>

                                            <!-- Regular IP addresses (when not a group) -->
                                            <div v-else class="address-ips">
                                              <div v-for="ip in getAddressDisplay(src, props.row).ip.split(', ')" :key="ip" class="ip-item q-mb-xs">
                                                <span class="ip-bullet">•</span>
                                                <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(ip.trim()) }" @click.stop="performClickableSearch(ip.trim())">{{ ip.trim() }}</span>
                                              </div>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                    </div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Destination Addresses Section -->
                              <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                <q-card flat bordered>
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="output" class="q-mr-sm" />
                                      Destination Addresses
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div class="q-gutter-sm">
                                      <!-- Any/All addresses case -->
                                      <div v-if="JSON.parse(props.row.destination_addresses || '[]').length === 0" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <q-chip color="orange-7" dense text-color="white" icon="info" class="q-mb-xs">
                                              any
                                            </q-chip>
                                            <div class="address-ips">
                                              <span class="ip-item">All destinations allowed</span>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>

                                      <!-- Specific addresses -->
                                      <div v-for="(dst, index) in JSON.parse(props.row.destination_addresses || '[]')" :key="dst + index" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <div class="address-header">
                                              <q-chip
                                                :color="props.row.address_mappings && props.row.address_mappings[dst] ? getMatchedAddressColor(dst, props.row.address_mappings) : 'blue-grey-6'"
                                                :icon="props.row.match_details && props.row.match_details.destination.includes(dst) ? 'verified' : 'info'"
                                                dense text-color="white" class="q-mb-xs clickable-group" @click.stop="performClickableSearch(dst)">
                                                {{ dst }}
                                              </q-chip>
                                            </div>
                                            <!-- Check if this is a group with hierarchical member details -->
                                            <div v-if="props.row.address_mappings && props.row.address_mappings[dst] && props.row.address_mappings[dst].hierarchical_members" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[dst].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${dst}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}`)" />
                                              </div>

                                              <!-- Expandable hierarchical member details -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}`]" class="member-details">
                                                <div v-for="(member, memberIndex) in safeParseHierarchicalMembers(props.row.address_mappings[dst].hierarchical_members)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <!-- Individual address member -->
                                                  <div v-if="member.type === 'address' || member.type === 'vip'" class="address-member">
                                                    <q-chip
                                                      :color="getMemberChipColor(member.type, member.name)"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.ip" class="member-separator">→</span>
                                                      <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                    </q-chip>
                                                  </div>

                                                  <!-- Group member with nested expandable structure -->
                                                  <div v-else-if="member.type === 'group' && member.expandable" class="group-member">
                                                    <div class="group-header">
                                                      <q-chip
                                                        color="amber-8"
                                                        text-color="white"
                                                        size="sm"
                                                        class="member-chip q-mr-sm">
                                                        <q-icon name="folder" class="q-mr-xs" />
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                        <span class="member-separator">→</span>
                                                        <span class="member-count">{{ member.member_count }} members</span>
                                                      </q-chip>
                                                      <q-btn
                                                        :icon="expandedPolicyGroups[`${props.row.id}_${dst}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                                        flat dense round size="xs"
                                                        @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}_${member.name}`)" />
                                                    </div>

                                                    <!-- Nested members for this group -->
                                                    <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}_${member.name}`] && member.members" class="nested-members q-ml-md q-mt-xs">
                                                      <div v-for="(nested, nestedIndex) in member.members" :key="nestedIndex" class="nested-member q-mb-xs">
                                                        <q-chip
                                                          :color="getMemberChipColor(nested.type, nested.name)"
                                                          text-color="white"
                                                          size="xs"
                                                          class="nested-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                          <span v-if="nested.ip" class="member-separator">→</span>
                                                          <span v-if="nested.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                        </q-chip>
                                                      </div>
                                                    </div>
                                                  </div>

                                                  <!-- Non-expandable group member -->
                                                  <div v-else-if="member.type === 'group'" class="group-member">
                                                    <q-chip
                                                      color="amber-8"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <q-icon name="folder" class="q-mr-xs" />
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.member_count" class="member-separator">→</span>
                                                      <span v-if="member.member_count" class="member-count">{{ member.member_count }} members</span>
                                                    </q-chip>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>

                                            <!-- Fallback: Check if this is a group with flat member details -->
                                            <div v-else-if="props.row.address_mappings && props.row.address_mappings[dst] && props.row.address_mappings[dst].member_details" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[dst].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${dst}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}`)" />
                                              </div>

                                              <!-- Expandable member details (fallback) -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}`]" class="member-details">
                                                <!-- Member Controls -->
                                                <div class="member-controls q-mb-sm">
                                                  <div class="row items-center q-gutter-sm">
                                                    <div class="text-subtitle2 text-blue-grey-7">Member Details:</div>
                                                    <q-input
                                                      v-model="groupSearchFilters[`${props.row.id}_${dst}`]"
                                                      dense outlined
                                                      placeholder="Filter members..."
                                                      class="col-auto"
                                                      style="min-width: 200px;"
                                                      clearable
                                                      debounce="300">
                                                      <template v-slot:prepend>
                                                        <q-icon name="search" />
                                                      </template>
                                                    </q-input>
                                                    <q-btn
                                                      v-if="getPolicyFilteredMembers(props.row.address_mappings[dst].member_details, `${props.row.id}_${dst}`).length > 50"
                                                      :label="showAllMembers[`${props.row.id}_${dst}`] ? `Show Less (${getPolicyFilteredMembers(props.row.address_mappings[dst].member_details, `${props.row.id}_${dst}`).length})` : `Show All (${getPolicyFilteredMembers(props.row.address_mappings[dst].member_details, `${props.row.id}_${dst}`).length})`"
                                                      :color="showAllMembers[`${props.row.id}_${dst}`] ? 'orange-7' : 'green-7'"
                                                      size="sm"
                                                      outline
                                                      @click="toggleShowAllMembers(`${props.row.id}_${dst}`)" />
                                                    <div v-if="groupSearchFilters[`${props.row.id}_${dst}`]" class="text-caption text-blue-grey-6">
                                                      {{ getPolicyDisplayedMembers(props.row.address_mappings[dst].member_details, `${props.row.id}_${dst}`).length }} of {{ getPolicyFilteredMembers(props.row.address_mappings[dst].member_details, `${props.row.id}_${dst}`).length }} members
                                                    </div>
                                                  </div>
                                                </div>
                                                <div v-for="(member, memberIndex) in getPolicyDisplayedMembers(props.row.address_mappings[dst].member_details, `${props.row.id}_${dst}`)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <q-chip
                                                    :color="getMemberChipColor(member.type, member.name)"
                                                    text-color="white"
                                                    size="sm"
                                                    class="member-chip">
                                                    <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                    <span class="member-separator"> → </span>
                                                    <span class="member-ip" :class="{ 'clickable-ip': member.type === 'address' }" @click.stop="member.type === 'address' ? performClickableSearch(member.ip) : null">{{ member.ip }}</span>
                                                  </q-chip>
                                                  <!-- Show nested members for groups -->
                                                  <div v-if="member.type === 'group' && member.nested_members" class="nested-members q-ml-md q-mt-xs">
                                                    <div v-for="(nested, nestedIndex) in member.nested_members" :key="nestedIndex" class="q-mb-xs">
                                                      <q-chip
                                                        :color="getMemberChipColor(nested.type, nested.name)"
                                                        text-color="white"
                                                        size="xs"
                                                        class="nested-member-chip">
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                        <span class="member-separator"> → </span>
                                                        <span class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                      </q-chip>
                                                    </div>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>

                                            <!-- Regular IP display for non-groups -->
                                            <div v-else class="address-ips">
                                              <div v-for="ipAddress in getAddressDisplay(dst, props.row).ip.split(', ')" :key="ipAddress" class="ip-item q-mb-xs">
                                                <span class="ip-bullet">•</span>
                                                <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(ipAddress.trim()) }" @click.stop="performClickableSearch(ipAddress.trim())">{{ ipAddress.trim() }}</span>
                                              </div>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                    </div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Services Section -->
                              <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                <q-card flat bordered>
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="settings_ethernet" class="q-mr-sm" />
                                      Services
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div class="q-gutter-xs expanded-chips-container">
                                      <q-chip
v-for="(svc, index) in JSON.parse(props.row.services || '[]')"
                                        :key="svc + index" color="blue" class="q-mb-xs expanded-chip" dense text-color="white">
                                        {{ svc }}
                                      </q-chip>
                                    </div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Match Details Section -->
                              <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                <q-card flat bordered class="bg-positive-1">
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="verified" class="q-mr-sm" />
                                      Match Details
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div v-if="props.row.match_details">
                                      <div v-if="props.row.match_details.source.length > 0" class="q-mb-sm">
                                        <div class="text-body2">
                                          <strong class="text-positive">Source Matches:</strong>
                                          <div class="q-mt-xs">
                                            <q-chip
v-for="match in props.row.match_details.source" :key="match"
                                              color="positive" dense size="md" text-color="white" class="q-mr-xs q-mb-xs">
                                              {{ match }}
                                            </q-chip>
                                          </div>
                                        </div>
                                      </div>
                                      <div v-if="props.row.match_details.destination.length > 0" class="q-mb-sm">
                                        <div class="text-body2">
                                          <strong class="text-positive">Destination Matches:</strong>
                                          <div class="q-mt-xs">
                                            <q-chip
v-for="match in props.row.match_details.destination" :key="match"
                                              color="positive" dense size="md" text-color="white" class="q-mr-xs q-mb-xs">
                                              {{ match }}
                                            </q-chip>
                                          </div>
                                        </div>
                                      </div>
                                      <div v-if="(!props.row.match_details.source || props.row.match_details.source.length === 0) && (!props.row.match_details.destination || props.row.match_details.destination.length === 0)" class="text-body2 text-grey-6">
                                        No direct matches found
                                      </div>
                                    </div>
                                    <div v-else class="text-body2 text-grey-6">
                                      No match details available
                                    </div>
                                </q-card-section>
                                </q-card>
                              </div>
                            </div>
                          </div>
                        </q-td>
                      </q-tr>
                    </template>
                  </q-table>
                </div>
              </div>

              <!-- NAT Policies Table -->
              <div
                v-if="searchResults.firewall_results && searchResults.firewall_results.nat_policies && searchResults.firewall_results.nat_policies.length > 0"
                class="q-mt-lg">
                <div class="text-h6 q-mb-md">NAT Policies</div>
                <div class="firewall-table-container">
                  <q-table
v-model:pagination="pagination" :rows="filteredNatPolicies"
                    :columns="natPolicyColumns" :expanded="expandedNatPolicies" bordered class="firewall-policy-table" flat
                    row-key="id" :sort-method="customSort"
                    binary-state-sort @update:expanded="expandedNatPolicies = $event">
                    <template #header="props">
                      <q-tr :props="props" class="bg-orange-1">
                        <q-th v-for="col in props.cols" :key="col.name" :props="props" 
                          class="text-weight-bold sortable-header" 
                          :style="{ width: getNatColumnWidth(col.name), textAlign: col.align }"
                          :class="{ 'cursor-pointer': col.sortable !== false }"
                          @click="col.sortable !== false ? props.sort(col.field) : null">
                          <div class="row items-center no-wrap">
                            <span>{{ col.label }}</span>
                            <q-space />
                            <q-icon v-if="col.sortable !== false && props.sort === col.field" 
                              :name="props.descending ? 'arrow_downward' : 'arrow_upward'" 
                              size="20px" class="q-ml-xs" />
                          </div>
                        </q-th>
                      </q-tr>
                    </template>

                    <template #body="props">
                      <q-tr :props="props" :class="{ 'disabled-nat-policy': props.row.status === 'disable' }">
                        <q-td key="expand" :props="props" :style="{ width: getNatColumnWidth('expand'), textAlign: 'center' }">
                          <q-btn
:icon="props.expand ? 'remove' : 'add'" color="orange-8" dense round size="md"
                            @click="props.expand = !props.expand" />
                        </q-td>

                        <q-td key="environment" :props="props" :style="{ width: getNatColumnWidth('environment'), textAlign: 'center' }">
                          <q-chip
:color="getEnvironmentColor(props.row.environment)" dense size="md"
                            text-color="white">
                            <q-icon v-if="props.row.config_type === 'paloalto' && props.row.environment !== 'Admin FW'" name="security" size="sm" class="q-mr-xs"/>
                            {{ props.row.environment }}
                          </q-chip>
                        </q-td>

                        <q-td key="policy_id" :props="props" :style="{ width: getNatColumnWidth('policy_id'), textAlign: 'center' }">
                          {{ props.row.policy_id }}
                        </q-td>

                        <q-td key="source_zone" :props="props" class="zone-column" :style="{ width: getNatColumnWidth('source_zone'), textAlign: 'center' }">
                          <q-chip v-if="props.row.source_zone" :color="getZoneColor(props.row.source_zone)" text-color="white" dense size="md">
                            {{ props.row.source_zone }}
                          </q-chip>
                          <span v-else class="text-grey-6 text-caption">-</span>
                        </q-td>

                        <q-td key="destination_zone" :props="props" class="zone-column" :style="{ width: getNatColumnWidth('destination_zone'), textAlign: 'center' }">
                          <q-chip v-if="props.row.destination_zone" :color="getZoneColor(props.row.destination_zone)" text-color="white" dense size="md">
                            {{ props.row.destination_zone }}
                          </q-chip>
                          <span v-else class="text-grey-6 text-caption">-</span>
                        </q-td>

                        <q-td key="source_addresses" :props="props" class="source-column" :style="{ width: getNatColumnWidth('source_addresses'), textAlign: 'left' }">
                          <div class="address-preview">
                            <div class="chips-container">
                              <q-chip
v-if="JSON.parse(props.row.source_addresses || '[]').length === 0"
                                color="orange-7" dense size="md" text-color="white" class="address-chip">
                                any
                              </q-chip>
                              <q-chip
v-for="(src, index) in JSON.parse(props.row.source_addresses || '[]')"
                                :key="src + index"
                                :color="props.row.match_details && props.row.match_details.source.includes(src) ? getMatchedAddressColor(src, props.row.address_mappings) : 'grey'"
                                class="address-chip clickable-group" dense size="md" text-color="white" @click.stop="performClickableSearch(src)">
                                {{ src }}
                              </q-chip>
                            </div>
                          </div>
                        </q-td>

                        <q-td key="destination_addresses" :props="props" class="destination-column" :style="{ width: getNatColumnWidth('destination_addresses'), textAlign: 'left' }">
                          <div class="address-preview">
                            <div class="chips-container">
                              <q-chip
                                v-if="JSON.parse(props.row.destination_addresses || '[]').length === 0"
                                color="orange-7" dense size="md" text-color="white" class="address-chip">
                                any
                              </q-chip>
                              <q-chip
                                v-for="(dst, index) in JSON.parse(props.row.destination_addresses || '[]')"
                                :key="dst + index"
                                :color="props.row.match_details && props.row.match_details.destination.includes(dst) ? getMatchedAddressColor(dst, props.row.address_mappings) : 'grey'"
                                class="address-chip clickable-group" dense size="md" text-color="white" @click.stop="performClickableSearch(dst)">
                                {{ dst }}
                              </q-chip>
                            </div>
                          </div>
                        </q-td>

                        <q-td key="source_translation" :props="props" class="translation-column" :style="{ width: getNatColumnWidth('source_translation'), textAlign: 'left' }">
                          <div class="address-preview">
                            <div class="chips-container">
                              <q-chip v-if="props.row.source_translation" color="amber-8" dense size="md" text-color="white" class="address-chip">
                                {{ getTranslationDisplay(props.row.source_translation) }}
                              </q-chip>
                              <span v-else class="text-grey-6 text-caption">-</span>
                            </div>
                          </div>
                        </q-td>

                        <q-td key="status" :props="props" class="status-column" :style="{ width: getNatColumnWidth('status'), textAlign: 'center' }">
                          <q-chip 
                            :color="props.row.status === 'enable' ? 'positive' : 'negative'" 
                            text-color="white" 
                            dense 
                            size="sm">
                            {{ props.row.status === 'enable' ? 'Enabled' : 'Disabled' }}
                          </q-chip>
                        </q-td>
                      </q-tr>

                      <!-- Expanded Row with NAT Policy Details -->
                      <q-tr v-show="props.expand" :props="props" class="bg-orange-1">
                        <q-td colspan="100%">
                          <div class="q-pa-md">
                            <!-- NAT Policy Details Header -->
                            <div class="row q-mb-md">
                              <div class="col-12">
                                <div class="text-h6 text-orange-8 q-mb-sm">
                                  NAT Policy {{ props.row.policy_id }} - {{ props.row.name || 'Unnamed NAT Policy' }}
                                </div>
                                <q-separator />
                              </div>
                            </div>

                            <!-- NAT Policy Details Sections -->
                            <div class="row q-gutter-md policy-details-row">
                              <!-- Source Section -->
                              <div class="col-12 col-md-6 col-lg-2 policy-detail-column">
                                <q-card flat bordered>
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="input" class="q-mr-sm" />
                                      Source
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div class="q-gutter-sm">
                                      <!-- Any/All addresses case -->
                                      <div v-if="JSON.parse(props.row.source_addresses || '[]').length === 0" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <q-chip color="orange-7" dense text-color="white" icon="info" class="q-mb-xs">
                                              any
                                            </q-chip>
                                            <div class="address-ips">
                                              <span class="ip-item">All source addresses allowed</span>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                      
                                      <!-- Specific addresses -->
                                      <div v-for="(src, index) in JSON.parse(props.row.source_addresses || '[]')" :key="src + index" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <div class="address-header">
                                              <q-chip
                                                :color="props.row.match_details && props.row.match_details.source.includes(src) ? getMatchedAddressColor(src, props.row.address_mappings) : 'blue-grey-6'"
                                                :icon="props.row.match_details && props.row.match_details.source.includes(src) ? 'verified' : 'info'"
                                                dense text-color="white" class="q-mb-xs clickable-group" @click.stop="performClickableSearch(src)">
                                                {{ src }}
                                              </q-chip>
                                            </div>
                                            <!-- Check if this is a group with hierarchical member details -->
                                            <div v-if="props.row.address_mappings && props.row.address_mappings[src] && props.row.address_mappings[src].hierarchical_members" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[src].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${src}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${src}`)" />
                                              </div>

                                              <!-- Expandable hierarchical member details -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${src}`]" class="member-details">
                                                <div v-for="(member, memberIndex) in safeParseHierarchicalMembers(props.row.address_mappings[src].hierarchical_members)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <!-- Individual address member -->
                                                  <div v-if="member.type === 'address'" class="address-member">
                                                    <q-chip
                                                      :color="getMemberChipColor(member.type, member.name)"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.ip" class="member-separator">→</span>
                                                      <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                    </q-chip>
                                                  </div>

                                                  <!-- Group member with nested expandable structure -->
                                                  <div v-else-if="member.type === 'group' && member.expandable" class="group-member">
                                                    <div class="group-header">
                                                      <q-chip
                                                        color="amber-8"
                                                        text-color="white"
                                                        size="sm"
                                                        class="member-chip q-mr-sm">
                                                        <q-icon name="folder" class="q-mr-xs" />
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                        <span class="member-separator">→</span>
                                                        <span class="member-count">{{ member.member_count }} members</span>
                                                      </q-chip>
                                                      <q-btn
                                                        :icon="expandedPolicyGroups[`${props.row.id}_${src}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                                        flat dense round size="xs"
                                                        @click="togglePolicyGroupExpansion(`${props.row.id}_${src}_${member.name}`)" />
                                                    </div>

                                                    <!-- Nested members for this group -->
                                                    <div v-if="expandedPolicyGroups[`${props.row.id}_${src}_${member.name}`] && member.members" class="nested-members q-ml-md q-mt-xs">
                                                      <div v-for="(nested, nestedIndex) in member.members" :key="nestedIndex" class="nested-member q-mb-xs">
                                                        <q-chip
                                                          :color="getMemberChipColor(nested.type, nested.name)"
                                                          text-color="white"
                                                          size="xs"
                                                          class="nested-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                          <span v-if="nested.ip" class="member-separator">→</span>
                                                          <span v-if="nested.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                        </q-chip>
                                                      </div>
                                                    </div>
                                                  </div>

                                                  <!-- Non-expandable group member -->
                                                  <div v-else-if="member.type === 'group'" class="group-member">
                                                    <q-chip
                                                      color="amber-8"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <q-icon name="folder" class="q-mr-xs" />
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.member_count" class="member-separator">→</span>
                                                      <span v-if="member.member_count" class="member-count">{{ member.member_count }} members</span>
                                                    </q-chip>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>

                                            <!-- Fallback: Check if this is a group with flat member details -->
                                            <div v-else-if="props.row.address_mappings && props.row.address_mappings[src] && props.row.address_mappings[src].member_details" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[src].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${src}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${src}`)" />
                                              </div>

                                              <!-- Expandable member details (fallback) -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${src}`]" class="member-details">
                                                <div v-for="(member, memberIndex) in safeParseMemberDetails(props.row.address_mappings[src].member_details)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <q-chip
                                                    :color="getMemberChipColor(member.type, member.name)"
                                                    text-color="white"
                                                    size="sm"
                                                    class="member-chip">
                                                    <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                    <span class="member-separator"> → </span>
                                                    <span class="member-ip" :class="{ 'clickable-ip': member.type === 'address' }" @click.stop="member.type === 'address' ? performClickableSearch(member.ip) : null">{{ member.ip }}</span>
                                                  </q-chip>
                                                  <!-- Show nested members for groups -->
                                                  <div v-if="member.type === 'group' && member.nested_members" class="nested-members q-ml-md q-mt-xs">
                                                    <div v-for="(nested, nestedIndex) in member.nested_members" :key="nestedIndex" class="q-mb-xs">
                                                      <q-chip
                                                        :color="getMemberChipColor(nested.type, nested.name)"
                                                        text-color="white"
                                                        size="xs"
                                                        class="nested-member-chip">
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                        <span class="member-separator"> → </span>
                                                        <span class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                      </q-chip>
                                                    </div>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>
                                            <!-- Regular IP display for non-groups -->
                                            <div v-else class="address-ips">
                                              <div v-for="ip in getAddressDisplay(src, props.row).ip.split(', ')" :key="ip" class="ip-item q-mb-xs">
                                                <span class="ip-bullet">•</span>
                                                <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(ip.trim()) }" @click.stop="performClickableSearch(ip.trim())">{{ ip.trim() }}</span>
                                              </div>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                    </div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Destination Section -->
                              <div class="col-12 col-md-6 col-lg-2 policy-detail-column">
                                <q-card flat bordered>
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="output" class="q-mr-sm" />
                                      Destination
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div class="q-gutter-sm">
                                      <!-- Any/All addresses case -->
                                      <div v-if="JSON.parse(props.row.destination_addresses || '[]').length === 0" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <q-chip color="orange-7" dense text-color="white" icon="info" class="q-mb-xs">
                                              any
                                            </q-chip>
                                            <div class="address-ips">
                                              <span class="ip-item">All destinations allowed</span>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                      
                                      <!-- Specific addresses -->
                                      <div v-for="(dst, index) in JSON.parse(props.row.destination_addresses || '[]')" :key="dst + index" class="address-card">
                                        <q-card flat bordered class="q-mb-sm">
                                          <q-card-section class="q-pa-sm">
                                            <div class="address-header">
                                              <q-chip
                                                :color="props.row.address_mappings && props.row.address_mappings[dst] ? getMatchedAddressColor(dst, props.row.address_mappings) : 'blue-grey-6'"
                                                :icon="props.row.match_details && props.row.match_details.destination.includes(dst) ? 'verified' : 'info'"
                                                dense text-color="white" class="q-mb-xs clickable-group" @click.stop="performClickableSearch(dst)">
                                                {{ dst }}
                                              </q-chip>
                                            </div>
                                            <!-- Check if this is a group with hierarchical member details -->
                                            <div v-if="props.row.address_mappings && props.row.address_mappings[dst] && props.row.address_mappings[dst].hierarchical_members" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[dst].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${dst}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}`)" />
                                              </div>

                                              <!-- Expandable hierarchical member details -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}`]" class="member-details">
                                                <div v-for="(member, memberIndex) in safeParseHierarchicalMembers(props.row.address_mappings[dst].hierarchical_members)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <!-- Individual address member -->
                                                  <div v-if="member.type === 'address' || member.type === 'vip'" class="address-member">
                                                    <q-chip
                                                      :color="getMemberChipColor(member.type, member.name)"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.ip" class="member-separator">→</span>
                                                      <span v-if="member.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(member.ip)">{{ member.ip }}</span>
                                                    </q-chip>
                                                  </div>

                                                  <!-- Group member with nested expandable structure -->
                                                  <div v-else-if="member.type === 'group' && member.expandable" class="group-member">
                                                    <div class="group-header">
                                                      <q-chip
                                                        color="amber-8"
                                                        text-color="white"
                                                        size="sm"
                                                        class="member-chip q-mr-sm">
                                                        <q-icon name="folder" class="q-mr-xs" />
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                        <span class="member-separator">→</span>
                                                        <span class="member-count">{{ member.member_count }} members</span>
                                                      </q-chip>
                                                      <q-btn
                                                        :icon="expandedPolicyGroups[`${props.row.id}_${dst}_${member.name}`] ? 'expand_less' : 'expand_more'"
                                                        flat dense round size="xs"
                                                        @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}_${member.name}`)" />
                                                    </div>

                                                    <!-- Nested members for this group -->
                                                    <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}_${member.name}`] && member.members" class="nested-members q-ml-md q-mt-xs">
                                                      <div v-for="(nested, nestedIndex) in member.members" :key="nestedIndex" class="nested-member q-mb-xs">
                                                        <q-chip
                                                          :color="getMemberChipColor(nested.type, nested.name)"
                                                          text-color="white"
                                                          size="xs"
                                                          class="nested-chip">
                                                          <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                          <span v-if="nested.ip" class="member-separator">→</span>
                                                          <span v-if="nested.ip" class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                        </q-chip>
                                                      </div>
                                                    </div>
                                                  </div>

                                                  <!-- Non-expandable group member -->
                                                  <div v-else-if="member.type === 'group'" class="group-member">
                                                    <q-chip
                                                      color="amber-8"
                                                      text-color="white"
                                                      size="sm"
                                                      class="member-chip">
                                                      <q-icon name="folder" class="q-mr-xs" />
                                                      <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                      <span v-if="member.member_count" class="member-separator">→</span>
                                                      <span v-if="member.member_count" class="member-count">{{ member.member_count }} members</span>
                                                    </q-chip>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>

                                            <!-- Fallback: Check if this is a group with flat member details -->
                                            <div v-else-if="props.row.address_mappings && props.row.address_mappings[dst] && props.row.address_mappings[dst].member_details" class="group-details">
                                              <!-- Group expand/collapse button -->
                                              <div class="row items-center q-mb-sm">
                                                <q-chip color="blue-grey-7" text-color="white" size="sm" class="q-mr-sm">
                                                  {{ props.row.address_mappings[dst].member_count }} members
                                                </q-chip>
                                                <q-btn
                                                  :icon="expandedPolicyGroups[`${props.row.id}_${dst}`] ? 'expand_less' : 'expand_more'"
                                                  flat dense round size="sm"
                                                  @click="togglePolicyGroupExpansion(`${props.row.id}_${dst}`)" />
                                              </div>

                                              <!-- Expandable member details (fallback) -->
                                              <div v-if="expandedPolicyGroups[`${props.row.id}_${dst}`]" class="member-details">
                                                <div v-for="(member, memberIndex) in safeParseMemberDetails(props.row.address_mappings[dst].member_details)" :key="memberIndex" class="member-item q-mb-xs">
                                                  <q-chip
                                                    :color="getMemberChipColor(member.type, member.name)"
                                                    text-color="white"
                                                    size="sm"
                                                    class="member-chip">
                                                    <span class="member-name clickable-group" @click.stop="performClickableSearch(member.name)">{{ member.name }}</span>
                                                    <span class="member-separator"> → </span>
                                                    <span class="member-ip" :class="{ 'clickable-ip': member.type === 'address' }" @click.stop="member.type === 'address' ? performClickableSearch(member.ip) : null">{{ member.ip }}</span>
                                                  </q-chip>
                                                  <!-- Show nested members for groups -->
                                                  <div v-if="member.type === 'group' && member.nested_members" class="nested-members q-ml-md q-mt-xs">
                                                    <div v-for="(nested, nestedIndex) in member.nested_members" :key="nestedIndex" class="q-mb-xs">
                                                      <q-chip
                                                        :color="getMemberChipColor(nested.type, nested.name)"
                                                        text-color="white"
                                                        size="xs"
                                                        class="nested-member-chip">
                                                        <span class="member-name clickable-group" @click.stop="performClickableSearch(nested.name)">{{ nested.name }}</span>
                                                        <span class="member-separator"> → </span>
                                                        <span class="member-ip clickable-ip" @click.stop="performClickableSearch(nested.ip)">{{ nested.ip }}</span>
                                                      </q-chip>
                                                    </div>
                                                  </div>
                                                </div>
                                              </div>
                                            </div>
                                            <!-- Regular IP display for non-groups -->
                                            <div v-else class="address-ips">
                                              <div v-for="ipAddress in getAddressDisplay(dst, props.row).ip.split(', ')" :key="ipAddress" class="ip-item q-mb-xs">
                                                <span class="ip-bullet">•</span>
                                                <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(ipAddress.trim()) }" @click.stop="performClickableSearch(ipAddress.trim())">{{ ipAddress.trim() }}</span>
                                              </div>
                                            </div>
                                          </q-card-section>
                                        </q-card>
                                      </div>
                                    </div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Source Translation Section -->
                              <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                <q-card flat bordered class="bg-amber-1">
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="transform" class="q-mr-sm" />
                                      Source Translation
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div v-if="props.row.source_translation">
                                      <q-chip color="grey-6" class="q-mb-xs expanded-chip" dense text-color="white">
                                        {{ getTranslationDisplay(props.row.source_translation) }}
                                      </q-chip>
                                    </div>
                                    <div v-else class="text-body2 text-grey-6">No source translation</div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Destination Translation Section -->
                              <div class="col-12 col-md-6 col-lg-2 policy-detail-column">
                                <q-card flat bordered>
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="swap_horiz" class="q-mr-sm" />
                                      Dest Translation
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div v-if="props.row.destination_translation" class="address-ips">
                                      <div class="ip-item q-mb-xs">
                                        <span class="ip-bullet">•</span>
                                        <span class="ip-address clickable-ip" :class="{ 'ip-highlight-match': isIpMatchingSearch(getTranslationDisplay(props.row.destination_translation)) }" @click.stop="performClickableSearch(getTranslationDisplay(props.row.destination_translation))">{{ getTranslationDisplay(props.row.destination_translation) }}</span>
                                      </div>
                                    </div>
                                    <div v-else class="text-body2 text-grey-6">No dest translation</div>
                                  </q-card-section>
                                </q-card>
                              </div>

                              <!-- Match Details Section -->
                              <div class="col-12 col-md-6 col-lg-3 policy-detail-column">
                                <q-card flat bordered class="bg-positive-1">
                                  <q-card-section class="bg-grey-2">
                                    <div class="text-subtitle1 text-weight-bold text-grey-8">
                                      <q-icon name="verified" class="q-mr-sm" />
                                      Match Details
                                    </div>
                                  </q-card-section>
                                  <q-card-section>
                                    <div v-if="props.row.match_details">
                                      <div v-if="props.row.match_details.source && props.row.match_details.source.length > 0" class="q-mb-sm">
                                        <div class="text-body2">
                                          <strong class="text-positive">Source:</strong>
                                          <div class="q-mt-xs">
                                            <q-chip
v-for="match in props.row.match_details.source" :key="match"
                                              color="positive" dense size="md" text-color="white" class="q-mr-xs q-mb-xs">
                                              {{ match }}
                                            </q-chip>
                                          </div>
                                        </div>
                                      </div>
                                      <div v-if="props.row.match_details.source_translation && props.row.match_details.source_translation.length > 0" class="q-mb-sm">
                                        <div class="text-body2">
                                          <strong class="text-amber-8">Translation:</strong>
                                          <div class="q-mt-xs">
                                            <q-chip
v-for="match in props.row.match_details.source_translation" :key="match"
                                              color="amber-8" dense size="md" text-color="white" class="q-mr-xs q-mb-xs">
                                              {{ match }}
                                            </q-chip>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                    <div v-else class="text-body2 text-grey-6">No match details</div>
                                  </q-card-section>
                                </q-card>
                              </div>
                            </div>
                          </div>
                        </q-td>
                      </q-tr>
                    </template>
                  </q-table>
                </div>
              </div>

              <!-- Pagination Controls for Firewall Results -->
              <div
v-if="paginationInfo && (paginationInfo.has_more_policies || paginationInfo.has_more_nat_policies)" 
                   class="text-center q-mt-lg">
                <q-card flat class="bg-blue-grey-1 q-pa-md">
                  <div class="text-body2 text-grey-7 q-mb-md">
                    <div v-if="paginationInfo.total_policies > 0">
                      Showing {{ paginationInfo.current_page * paginationInfo.page_size - paginationInfo.page_size + 1 }}-{{ 
                        Math.min(paginationInfo.current_page * paginationInfo.page_size, paginationInfo.total_policies) 
                      }} of {{ paginationInfo.total_policies }} firewall policies
                    </div>
                    <div v-if="paginationInfo.total_nat_policies > 0" class="q-mt-xs">
                      {{ paginationInfo.total_nat_policies }} NAT policies total
                    </div>
                  </div>
                  
                  <q-btn 
                    v-if="paginationInfo.has_more_policies || paginationInfo.has_more_nat_policies"
                    :loading="loadingMore" 
                    color="primary" 
                    icon="expand_more" 
                    label="Load More Results" 
                    class="q-px-lg" 
                    @click="loadMore" />
                    
                  <div
v-if="!paginationInfo.has_more_policies && !paginationInfo.has_more_nat_policies" 
                       class="text-caption text-grey-6">
                    All results loaded
                  </div>
                </q-card>
              </div>
            </q-tab-panel>

            <!-- FQDN Results Tab -->
            <q-tab-panel name="fqdn" class="fqdn-result">
              <!-- Copy Buttons for FQDN Results -->
              <div v-if="hasAnyFqdnResults()" class="q-mb-md">
                <div class="row q-gutter-sm">
                  <q-btn
                    color="primary"
                    icon="content_copy"
                    label="Copy FQDNs"
                    size="sm"
                    @click="copyAllFqdns()"
                    :disable="!hasAnyFqdnResults()" />
                  <q-btn
                    color="secondary"
                    icon="content_copy"
                    label="Copy IPs"
                    size="sm"
                    @click="copyAllIps()"
                    :disable="!hasAnyFqdnResults()" />
                  <q-btn
                    color="accent"
                    icon="content_copy"
                    label="Copy FQDN & IP"
                    size="sm"
                    @click="copyFqdnTable()"
                    :disable="!hasAnyFqdnResults()" />
                </div>
              </div>
              <!-- Object Resolution FQDN Results -->
              <div v-if="searchResults.object_resolution && searchResults.object_resolution.success && searchResults.object_resolution.fqdn_results.count > 0" class="q-mb-lg">
                <q-card flat>
                  <q-card-section class="q-pa-md">
                    <div class="text-h6 text-primary">Object Resolution FQDN Results</div>
                    <div class="text-subtitle2 text-grey-7">
                      FQDN records for IPs resolved from object name: {{ searchResults.ip_address }}
                    </div>
                    <div class="text-caption text-grey-6 q-mt-xs">
                      Resolved IPs: {{ searchResults.object_resolution.resolved_ips.join(', ') }}
                    </div>
                  </q-card-section>
                  <q-card-section class="q-pa-none">
                    <q-table
                      :rows="searchResults.object_resolution.fqdn_results.records"
                      :columns="fqdnColumns"
                      :row-key="(row) => `obj-${row.fqdn}-${row.ip}-${row.type}`"
                      dense
                      flat
                      :rows-per-page-options="[25, 50, 100, 200, 500]"
                      :pagination="{ rowsPerPage: 100 }"
                      class="fqdn-table">

                      <template #body-cell-fqdn="props">
                        <q-td :props="props" class="text-weight-bold">
                          <span class="fqdn-clickable" @click.stop="performClickableSearch(props.row.fqdn)">{{ props.row.fqdn }}</span>
                        </q-td>
                      </template>

                      <template #body-cell-ip="props">
                        <q-td :props="props">
                          <span class="ip-clickable" @click.stop="performClickableSearch(props.row.ip)">{{ props.row.ip }}</span>
                        </q-td>
                      </template>

                      <template #body-cell-type="props">
                        <q-td :props="props">
                          <q-chip :color="props.row.type === 'A' ? 'green' : 'orange'" dense size="md" text-color="white">
                            {{ props.row.type }}
                          </q-chip>
                        </q-td>
                      </template>

                      <template #body-cell-domain="props">
                        <q-td :props="props">
                          <span class="domain-clickable" @click.stop="performClickableSearch(props.row.domain)">{{ props.row.domain }}</span>
                        </q-td>
                      </template>

                    </q-table>
                  </q-card-section>
                </q-card>
              </div>

              <!-- VS Mapping FQDN Results -->
              <div v-if="searchResults.vs_mapping && searchResults.vs_mapping.success && searchResults.vs_mapping.vs_fqdn_results.count > 0" class="q-mb-lg">
                <q-card flat>
                  <q-card-section class="q-pa-md">
                    <div class="text-h6 text-primary">Virtual Server FQDN Results</div>
                    <div class="text-subtitle2 text-grey-7">
                      FQDN records for Virtual Servers that use {{ searchResults.ip_address }} as a pool member
                    </div>
                    <div class="text-caption text-grey-6 q-mt-xs">
                      Found {{ searchResults.vs_mapping.count }} Virtual Servers with this node IP
                    </div>
                  </q-card-section>

                  <!-- Virtual Servers Summary -->
                  <q-card-section class="q-pa-md q-pt-none">
                    <q-expansion-item
                      icon="dns"
                      label="Virtual Servers Using This Node"
                      :caption="`${searchResults.vs_mapping.count} Virtual Servers found`"
                      dense
                      dense-toggle
                      expand-separator
                      class="q-mb-md">
                      <div class="row q-gutter-sm q-mt-sm">
                        <div v-for="vs in searchResults.vs_mapping.virtual_servers" :key="vs.vs_name" class="col-12 col-md-6">
                          <q-card flat bordered class="q-pa-sm">
                            <div class="text-weight-bold">{{ vs.vs_name }}</div>
                            <div class="text-caption text-grey-7">VS IP: <span class="ip-clickable" @click.stop="performClickableSearch(vs.vs_ip.replace('/Common/', ''))">{{ vs.vs_ip }}</span></div>
                            <div class="text-caption text-grey-7">Pool: {{ vs.pool_name }}</div>
                          </q-card>
                        </div>
                      </div>
                    </q-expansion-item>
                  </q-card-section>

                  <q-card-section class="q-pa-none">
                    <q-table
                      :rows="searchResults.vs_mapping.vs_fqdn_results.records"
                      :columns="fqdnColumns"
                      :row-key="(row) => `vs-${row.fqdn}-${row.ip}-${row.type}`"
                      dense
                      flat
                      :rows-per-page-options="[25, 50, 100, 200, 500]"
                      :pagination="{ rowsPerPage: 100 }"
                      class="fqdn-table">
                      <template #body-cell-fqdn="props">
                        <q-td :props="props" class="text-weight-bold">
                          <span class="fqdn-clickable" @click.stop="performClickableSearch(props.row.fqdn)">{{ props.row.fqdn }}</span>
                        </q-td>
                      </template>
                      <template #body-cell-ip="props">
                        <q-td :props="props">
                          <span class="ip-clickable" @click.stop="performClickableSearch(props.row.ip)">{{ props.row.ip }}</span>
                        </q-td>
                      </template>
                      <template #body-cell-type="props">
                        <q-td :props="props">
                          <q-chip :color="props.row.type === 'A' ? 'green' : 'orange'" dense size="md" text-color="white">
                            {{ props.row.type }}
                          </q-chip>
                        </q-td>
                      </template>
                      <template #body-cell-domain="props">
                        <q-td :props="props">
                          <span class="domain-clickable" @click.stop="performClickableSearch(props.row.domain)">{{ props.row.domain }}</span>
                        </q-td>
                      </template>
                    </q-table>
                  </q-card-section>
                </q-card>
              </div>

              <!-- NAT-Mapped FQDN Results -->
              <div v-if="searchResults.mapped_fqdn_results && searchResults.mapped_fqdn_results.success && searchResults.mapped_fqdn_results.count > 0" class="q-mb-lg">
                <q-card flat>
                  <q-card-section class="q-pa-md">
                    <div class="text-h6 text-primary">NAT-Mapped FQDN Results</div>
                    <div class="text-subtitle2 text-grey-7">
                      FQDN records for IPs mapped through NAT translation from {{ searchResults.ip_address }}
                    </div>
                    <div class="text-caption text-grey-6 q-mt-xs">
                      Found {{ searchResults.mapped_fqdn_results.count }} NAT translation{{ searchResults.mapped_fqdn_results.count !== 1 ? 's' : '' }}
                    </div>
                  </q-card-section>

                  <q-card-section class="q-pa-none">
                    <q-table
                      :rows="getEnhancedNatFqdnRecords()"
                      :columns="fqdnColumns"
                      :row-key="(row) => `nat-${row.nat_translation}-${row.fqdn}-${row.ip}-${row.type}`"
                      dense
                      flat
                      :rows-per-page-options="[25, 50, 100, 200, 500]"
                      :pagination="{ rowsPerPage: 25 }"
                      class="fqdn-table">
                      <template v-slot:body-cell-ip="props">
                        <q-td :props="props">
                          <q-chip
                            :label="props.value"
                            size="sm"
                            color="blue-grey-3"
                            text-color="dark"
                            dense
                            class="q-ma-none"
                          />
                        </q-td>
                      </template>
                      <template v-slot:body-cell-type="props">
                        <q-td :props="props">
                          <q-badge
                            :label="props.value"
                            :color="props.value === 'A' ? 'green' : props.value === 'CNAME' ? 'blue' : 'purple'"
                            class="q-pa-xs"
                          />
                        </q-td>
                      </template>
                      <template v-slot:body-cell-owner="props">
                        <q-td :props="props">
                          <q-chip
                            :label="props.value || 'N/A'"
                            size="sm"
                            :color="getOwnerColor(props.value)"
                            text-color="white"
                            dense
                            class="q-ma-none"
                          />
                        </q-td>
                      </template>

                      <template v-slot:body-cell-fqdn="props">
                        <q-td :props="props" class="text-weight-bold">
                          <span class="fqdn-clickable" @click.stop="performClickableSearch(props.row.fqdn)">{{ props.row.fqdn }}</span>
                        </q-td>
                      </template>

                      <template v-slot:body-cell-nat_translation="props">
                        <q-td :props="props">
                          <q-chip
                            v-if="props.row.nat_translation"
                            :label="props.row.nat_translation"
                            size="sm"
                            color="blue"
                            text-color="white"
                            dense
                            icon="swap_horiz"
                            class="q-ma-none"
                          />
                          <span v-else>-</span>
                        </q-td>
                      </template>
                    </q-table>
                  </q-card-section>
                </q-card>
              </div>

              <!-- Regular FQDN Results -->

              <div v-if="searchResults.fqdn_results && searchResults.fqdn_results.records && searchResults.fqdn_results.records.length > 0">
                <q-card flat>
                  <q-card-section v-if="searchResults.object_resolution && searchResults.object_resolution.success && searchResults.object_resolution.fqdn_results.count > 0" class="q-pa-md">
                    <div class="text-h6 text-primary">Direct FQDN Results</div>
                    <div class="text-subtitle2 text-grey-7">
                      FQDN records matching the search term directly
                    </div>
                  </q-card-section>
                  <q-card-section class="q-pa-none">
                    <q-table
                      :rows="searchResults.fqdn_results.records"
                      :columns="fqdnColumns"
                      :row-key="(row) => `${row.fqdn}-${row.ip}-${row.type}`"
                      dense
                      flat
                      :rows-per-page-options="[25, 50, 100, 200, 500]"
                      :pagination="{ rowsPerPage: 100 }"
                      class="fqdn-table">
                      
                      <template #body-cell-fqdn="props">
                        <q-td :props="props" class="text-weight-bold">
                          <span class="fqdn-clickable" @click.stop="performClickableSearch(props.row.fqdn)">{{ props.row.fqdn }}</span>
                        </q-td>
                      </template>
                      
                      <template #body-cell-ip="props">
                        <q-td :props="props">
                          <span class="ip-clickable" @click.stop="performClickableSearch(props.row.ip)">{{ props.row.ip }}</span>
                        </q-td>
                      </template>
                      
                      <template #body-cell-type="props">
                        <q-td :props="props">
                          <q-chip :color="props.row.type === 'A' ? 'green' : 'orange'" dense size="md" text-color="white">
                            {{ props.row.type }}
                          </q-chip>
                        </q-td>
                      </template>
                      
                      <template #body-cell-domain="props">
                        <q-td :props="props">
                          <span class="fqdn-clickable" @click.stop="performClickableSearch(props.row.domain)">{{ props.row.domain }}</span>
                        </q-td>
                      </template>
                      
                      <template #body-cell-owner="props">
                        <q-td :props="props">
                          <q-chip color="grey-6" dense size="md" text-color="white">
                            {{ props.row.owner }}
                          </q-chip>
                        </q-td>
                      </template>
                    </q-table>
                  </q-card-section>
                </q-card>
              </div>
            </q-tab-panel>
          </q-tab-panels>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script>
import { defineComponent, ref, computed, watch, onMounted } from 'vue'
import { api } from 'boot/axios'
import { Notify } from 'quasar'

export default defineComponent({
  name: 'SearchPage',

  setup() {
    const searchType = ref('fqdn')
    const searchQuery = ref('sb-results.demo-corp.example')
    const searching = ref(false)
    const searchResults = ref(null)
    const activeTab = ref('firewall')
    const expandedPolicies = ref([])
    const expandedNatPolicies = ref([])
    const expandedChips = ref({})
    const expandedGroups = ref({})
    const expandedPolicyGroups = ref({})
    const expandedNestedGroups = ref({})
    const pagination = ref({
      rowsPerPage: 20
    })
    const selectedEnvironments = ref([])
    const availableEnvironments = ref([])
    const isMultipleIps = ref(false)
    const bulkResults = ref(null)
    const ipSearchDirection = ref('both')  // 'both', 'source', 'destination'

    // Infrastructure filtering state
    const availableInfrastructures = ref([])
    const infraToggleStates = ref({})
    
    // Pagination state
    const currentPage = ref(1)
    const pageSize = ref(1000)
    const loadingMore = ref(false)
    const paginationInfo = ref(null)
    
    // Multi-IP detection and parsing
    const parseIpAddresses = (query) => {
      if (!query) return []
      // Split by commas, spaces, and newlines, then clean up each IP
      return query
        .split(/[,\s\n\r]+/)
        .map(ip => {
          let cleanIp = ip.trim()
          // Auto-remove _32 suffix if present
          if (cleanIp.endsWith('_32')) {
            cleanIp = cleanIp.slice(0, -3)
          }
          return cleanIp
        })
        .filter(ip => ip.length > 0)
    }
    
    
    const getIpCount = () => {
      return parseIpAddresses(searchQuery.value).length
    }
    
    const getSearchTypeLabel = () => {
      if (isMultipleIps.value) {
        return `Multiple IPs (${getIpCount()})`
      }
      return searchType.value === 'ip' ? 'IP' : searchType.value === 'fqdn' ? 'FQDN' : 'Object'
    }
    
    // Helper function to detect if input is a partial IP
    const isPartialIp = (query) => {
      // Check for partial IP patterns like 172.30, 10.1.2, etc.
      const partialIpPattern = /^(?:\d{1,3}\.){1,3}\d{1,3}?$/
      return partialIpPattern.test(query) && !query.match(/^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/)
    }

    // Helper function to detect if input is a complete IP
    const isCompleteIp = (query) => {
      const ipPattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
      return ipPattern.test(query)
    }

    // Auto-detect search type based on input
    const autoDetectSearchType = (query) => {
      if (!query || query.trim() === '') {
        // Reset to default when empty
        searchType.value = 'ip'
        isMultipleIps.value = false
        return
      }
      
      // First check for multiple IPs
      const ips = parseIpAddresses(query)
      if (ips.length > 1) {
        isMultipleIps.value = true
        searchType.value = 'ip'
        return
      }
      
      isMultipleIps.value = false
      const trimmedQuery = query.trim()
      
      // Check if it's a complete IP address
      if (isCompleteIp(trimmedQuery)) {
        searchType.value = 'ip'
      } 
      // Check if it's a partial IP (e.g., 172.30, 10.1.2)
      else if (isPartialIp(trimmedQuery)) {
        searchType.value = 'ip'
      } 
      // Check if it looks like a domain/FQDN (excluding partial IPs)
      else if (trimmedQuery.includes('.') && (trimmedQuery.endsWith('.com') || trimmedQuery.endsWith('.net') || trimmedQuery.endsWith('.org') || trimmedQuery.match(/\.[a-zA-Z]{2,}$/))) {
        searchType.value = 'fqdn'
      } else if (trimmedQuery.length >= 3) {
        searchType.value = 'object'
      }
      // For strings less than 3 chars, keep current search type
    }

    // Function to update URL with search parameter
    const updateUrlWithSearch = (searchTerm) => {
      const currentUrl = new URL(window.location.href)
      if (searchTerm && searchTerm.trim()) {
        currentUrl.searchParams.set('search', searchTerm.trim())
      } else {
        currentUrl.searchParams.delete('search')
      }
      // Update URL without causing a page reload
      window.history.replaceState({}, '', currentUrl.toString())
    }

    // Watch for changes in searchQuery to auto-detect search type and update URL
    watch(searchQuery, (newValue) => {
      autoDetectSearchType(newValue)
      updateUrlWithSearch(newValue)
    })

    // Watch for policy expansion and auto-expand all address groups by default
    watch(expandedPolicies, (newExpandedPolicies, oldExpandedPolicies) => {
      // Find newly expanded policy IDs
      const newlyExpandedIds = newExpandedPolicies.filter(id => !oldExpandedPolicies.includes(id))


      // For each newly expanded policy ID, look up the policy object and auto-expand its address groups
      newlyExpandedIds.forEach(policyId => {
        // Find the policy object from uniquePolicies computed property
        const policy = uniquePolicies.value.find(p => p.id === policyId)


        if (policy && policy.address_mappings) {

          // Expand source address groups
          const sourceAddresses = JSON.parse(policy.source_addresses || '[]')

          sourceAddresses.forEach(src => {
            const mapping = policy.address_mappings[src]

            if (mapping && mapping.hierarchical_members) {
              const groupKey = `${policy.id}_${src}`
              expandedPolicyGroups.value[groupKey] = true
            }
          })

          // Expand destination address groups
          const destAddresses = JSON.parse(policy.destination_addresses || '[]')

          destAddresses.forEach(dst => {
            const mapping = policy.address_mappings[dst]

            if (mapping && mapping.hierarchical_members) {
              const groupKey = `${policy.id}_${dst}`
              expandedPolicyGroups.value[groupKey] = true
            }
          })
        }
      })
    }, { deep: true })

    const searchTypes = [
      { label: 'IP Address', value: 'ip' },
      { label: 'Object Name', value: 'object' },
      { label: 'FQDN/Domain', value: 'fqdn' }
    ]
    
    // Remove unused filter variables - using sortable headers instead

    const firewallColumns = [
      { name: 'expand', label: '', align: 'center', field: 'expand', sortable: false },
      { name: 'environment', label: 'Env', align: 'center', field: 'environment', sortable: true },
      { name: 'source_zone', label: 'From', align: 'center', field: 'source_zone', sortable: true },
      { name: 'destination_zone', label: 'To', align: 'center', field: 'destination_zone', sortable: true },
      { name: 'policy_id', label: 'ID', align: 'center', field: 'policy_id', sortable: true, sort: (a, b) => parseInt(a) - parseInt(b) },
      { name: 'name', label: 'Name', align: 'left', field: 'name', sortable: true },
      { name: 'source_addresses', label: 'Source', align: 'left', field: 'source_addresses', sortable: false },
      { name: 'destination_addresses', label: 'Destination', align: 'left', field: 'destination_addresses', sortable: false },
      { name: 'services', label: 'Services', align: 'left', field: 'services', sortable: false },
      { name: 'match_details', label: 'Match Details', align: 'left', field: 'match_details', sortable: false },
      { name: 'action', label: 'Action', align: 'center', field: 'action', sortable: true }
    ]

    const natPolicyColumns = [
      { name: 'expand', label: 'Expand', align: 'center', field: 'expand', sortable: false },
      { name: 'environment', label: 'Env', align: 'center', field: 'environment', sortable: true },
      { name: 'policy_id', label: 'Policy ID', align: 'center', field: 'policy_id', sortable: true, sort: (a, b) => parseInt(a) - parseInt(b) },
      { name: 'source_zone', label: 'From', align: 'center', field: 'source_zone', sortable: true },
      { name: 'destination_zone', label: 'To', align: 'center', field: 'destination_zone', sortable: true },
      { name: 'source_addresses', label: 'Source', align: 'left', field: 'source_addresses', sortable: false },
      { name: 'destination_addresses', label: 'Destination', align: 'left', field: 'destination_addresses', sortable: false },
      { name: 'source_translation', label: 'Translation', align: 'left', field: 'source_translation', sortable: false },
      { name: 'status', label: 'Status', align: 'center', field: 'status', sortable: true }
    ]

    const fqdnColumns = [
      { 
        name: 'fqdn', 
        label: 'FQDN', 
        align: 'left', 
        field: 'fqdn', 
        sortable: true 
      },
      { 
        name: 'ip', 
        label: 'IP Address', 
        align: 'left', 
        field: 'ip', 
        sortable: true 
      },
      { 
        name: 'type', 
        label: 'Type', 
        align: 'center', 
        field: 'type', 
        sortable: true 
      },
      { 
        name: 'domain', 
        label: 'Domain', 
        align: 'left', 
        field: 'domain', 
        sortable: true 
      },
      { 
        name: 'owner', 
        label: 'Owner', 
        align: 'center', 
        field: 'owner', 
        sortable: true 
      },
      { 
        name: 'ttl', 
        label: 'TTL', 
        align: 'center', 
        field: 'ttl', 
        sortable: true 
      },
      {
        name: 'geo_info',
        label: 'Geo Info',
        align: 'center',
        field: 'geo_info',
        sortable: true
      },
      {
        name: 'nat_translation',
        label: 'NAT Translation',
        align: 'center',
        field: 'nat_translation',
        sortable: false
      }
    ]
    
    
    // Remove duplicate policies and apply environment filters
    const uniquePolicies = computed(() => {
      if (!searchResults.value?.firewall_results?.policies) return []

      const policies = searchResults.value.firewall_results.policies
      const seen = new Set()

      return policies.filter(policy => {
        // Create a unique key based on policy_id and environment to identify duplicates
        const uniqueKey = `${policy.policy_id}-${policy.environment}`
        if (seen.has(uniqueKey)) {
          return false // Skip duplicate
        }
        seen.add(uniqueKey)

        // Apply environment filter if any environments are selected
        if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
          return selectedEnvironments.value.includes(policy.environment)
        }

        return true
      })
    })

    // Filtered NAT policies based on environment filter
    const filteredNatPolicies = computed(() => {
      if (!searchResults.value?.firewall_results?.nat_policies) return []

      const natPolicies = searchResults.value.firewall_results.nat_policies

      // Apply environment filter if any environments are selected
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return natPolicies.filter(policy => selectedEnvironments.value.includes(policy.environment))
      } else {
        return natPolicies
      }
    })

    // Filtered LTM results based on environment filter
    const filteredLtmResults = computed(() => {
      if (!searchResults.value?.ltm_results?.virtual_servers) return []

      const virtualServers = searchResults.value.ltm_results.virtual_servers

      // Apply environment filter if any environments are selected
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return virtualServers.filter(vs => selectedEnvironments.value.includes(vs.virtual_server.environment))
      } else {
        return virtualServers
      }
    })

    // Filtered address objects based on environment filter
    const filteredAddressObjects = computed(() => {
      if (!searchResults.value?.firewall_results?.address_objects) return []

      const addressObjects = searchResults.value.firewall_results.address_objects

      // Apply environment filter if any environments are selected
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return addressObjects.filter(obj => selectedEnvironments.value.includes(obj.environment))
      } else {
        return addressObjects
      }
    })

    // Filtered address groups based on environment filter
    const filteredAddressGroups = computed(() => {
      if (!searchResults.value?.firewall_results?.address_groups) return []

      const addressGroups = searchResults.value.firewall_results.address_groups

      // Apply environment filter if any environments are selected
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return addressGroups.filter(group => selectedEnvironments.value.includes(group.environment))
      } else {
        return addressGroups
      }
    })

    // Removed filteredPolicies - using sortable uniquePolicies directly

    const isValidQuery = computed(() => {
      if (searchType.value === 'ip') {
        // Check for multiple IPs
        if (isMultipleIps.value) {
          const ips = parseIpAddresses(searchQuery.value)
          return ips.length > 0 && ips.every(ip => isCompleteIp(ip) || isPartialIp(ip))
        } else {
          // Single IP validation - accept both complete and partial IPs
          const trimmed = searchQuery.value.trim()
          return isCompleteIp(trimmed) || isPartialIp(trimmed)
        }
      } else if (searchType.value === 'fqdn') {
        return searchQuery.value && searchQuery.value.trim().length >= 3
      } else {
        return searchQuery.value && searchQuery.value.trim().length >= 3
      }
    })

    const getValidationRules = () => {
      if (searchType.value === 'ip') {
        if (isMultipleIps.value) {
          // Multiple IP validation
          return [(val) => {
            if (!val || val.trim() === '') return true // Allow empty values
            const ips = parseIpAddresses(val)
            if (ips.length === 0) return 'Please enter at least one IP address'
            
            const invalidIps = ips.filter(ip => !isCompleteIp(ip) && !isPartialIp(ip))
            
            if (invalidIps.length > 0) {
              return `Invalid IP address(es): ${invalidIps.join(', ')}`
            }
            
            return true
          }]
        } else {
          // Single IP validation - accept both complete and partial IPs
          return [(val) => {
            if (!val || val.trim() === '') return true // Allow empty values
            const trimmed = val.trim()
            return (isCompleteIp(trimmed) || isPartialIp(trimmed)) || 'Please enter a valid IPv4 address or partial IP (e.g., 192.168.1.100 or 172.30)'
          }]
        }
      } else if (searchType.value === 'fqdn') {
        return [(val) => {
          if (!val || val.trim() === '') return true // Allow empty values
          return (val && val.trim().length >= 3) || 'FQDN must be at least 3 characters'
        }]
      } else {
        return [(val) => {
          if (!val || val.trim() === '') return true // Allow empty values
          return (val && val.trim().length >= 3) || 'Object name must be at least 3 characters'
        }]
      }
    }

    const getInputLabel = () => {
      if (searchType.value === 'ip') return 'IP Address'
      if (searchType.value === 'fqdn') return 'FQDN/Domain'
      return 'Object Name'
    }

    const getPlaceholder = () => {
      if (searchType.value === 'ip') {
        return 'Enter full or partial IP address (e.g., 192.168.1.100 or 172.30)'
      } else if (searchType.value === 'fqdn') {
        return 'Enter FQDN or domain (e.g., www.example.com, example.com)'
      } else {
        return 'Enter object name (min 3 chars, e.g., CSP, Office365)'
      }
    }

    const getDynamicInputLabel = () => {
      if (!searchQuery.value) {
        return 'Search IP Address, Object Name, or FQDN'
      }
      if (searchType.value === 'ip') return 'IP Address'
      if (searchType.value === 'fqdn') return 'FQDN/Domain'
      return 'Object Name'
    }

    const getDynamicPlaceholder = () => {
      if (!searchQuery.value) {
        return 'Enter IP address, object name, or FQDN (e.g., 192.168.1.100, 172.30, CSP, www.example.com)'
      }
      if (searchType.value === 'ip') {
        return 'Enter full or partial IP address (e.g., 192.168.1.100 or 172.30)'
      } else if (searchType.value === 'fqdn') {
        return 'Enter FQDN or domain (e.g., www.example.com, example.com)'
      } else {
        return 'Enter object name (min 3 chars, e.g., CSP, Office365)'
      }
    }


    const toggleChip = (policyId, addressName) => {
      const key = `${policyId}_${addressName}`
      // If it's undefined (first time), it means it was expanded by default, so set to false
      // If it's already defined, toggle it
      expandedChips.value[key] = expandedChips.value[key] !== undefined ? !expandedChips.value[key] : false
    }

    const isChipExpanded = (policyId, addressName) => {
      const key = `${policyId}_${addressName}`
      return expandedChips.value[key] !== undefined ? expandedChips.value[key] : true
    }


    const getAddressDisplay = (addressName, policy) => {
      // Check if it's already an IP address
      const ipPattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
      if (ipPattern.test(addressName)) {
        return { name: addressName, ip: addressName, type: 'ip' }
      }

      // Look up in address mappings
      if (policy.address_mappings && policy.address_mappings[addressName]) {
        const mapping = policy.address_mappings[addressName]
        
        // Handle address groups - they now show group name with member count
        if (mapping.object_type === 'group' && mapping.ip_address) {
          return {
            name: addressName,
            ip: mapping.ip_address, // Contains "GroupName (X members)" format
            type: 'group'
          }
        }
        
        // Handle regular address objects - prefer cidr_notation over ip_address
        let displayIp = mapping.cidr_notation || mapping.ip_address || 'Unknown'
        
        // If we have cidr_notation, use it directly as it already contains the prefix
        // If we only have ip_address but it's a host address, add /32
        if (!mapping.cidr_notation && mapping.ip_address && mapping.object_type === 'host') {
          displayIp = `${mapping.ip_address}/32`
        }
        
        return {
          name: addressName,
          ip: displayIp,
          type: mapping.object_type || 'object'
        }
      }

      return { name: addressName, ip: 'Unknown', type: 'unknown' }
    }
    
    // Function to check if an IP matches the current search query
    const isIpMatchingSearch = (ip) => {
      if (!searchQuery.value || searchType.value !== 'ip') {
        return false
      }
      
      // Clean up the IP (remove CIDR notation if present)
      const cleanIp = ip.split('/')[0].trim()
      const searchIp = searchQuery.value.trim()
      
      // Check for exact IP match
      if (cleanIp === searchIp) {
        return true
      }
      
      // Check for partial IP match (e.g., search "172.30" should match "172.30.1.100")
      if (isPartialIp(searchIp)) {
        if (cleanIp.startsWith(searchIp + '.')) {
          return true
        }
      }
      
      // Check if search IP falls within this subnet
      if (ip.includes('/')) {
        try {
          const [subnetIp, prefixLength] = ip.split('/')
          const prefix = parseInt(prefixLength)
          
          // For partial IP searches, also check if the subnet IP matches the partial pattern
          if (isPartialIp(searchIp)) {
            const cleanSubnetIp = subnetIp.trim()
            if (cleanSubnetIp.startsWith(searchIp + '.')) {
              return true
            }
          }
          
          // Convert IPs to binary for subnet matching (only for complete IP searches)
          if (isCompleteIp(searchIp)) {
            const ipToBinary = (ipAddr) => {
              return ipAddr.split('.').map(octet => {
                return parseInt(octet).toString(2).padStart(8, '0')
              }).join('')
            }
            
            const searchBinary = ipToBinary(searchIp)
            const subnetBinary = ipToBinary(subnetIp.trim())
            
            // Compare the first 'prefix' bits
            return searchBinary.substring(0, prefix) === subnetBinary.substring(0, prefix)
          }
        } catch (e) {
          console.warn('Error checking subnet match:', e)
          return false
        }
      }
      
      return false
    }

    // Status class functions for LTM nodes
    const getStatusClass = (status, enabled) => {
      if (status === 'disabled' || enabled === false) {
        return 'disabled'
      }
      return 'enabled'
    }

    const getNodeStatusClass = (status) => {
      // Simplified F5 LTM node status mapping - only show enabled (green) or disabled (black)
      
      if (!status) return 'enabled' // Default for null/undefined
      
      const normalizedStatus = status.toLowerCase().trim()
      
      // Disabled states (Black dot) - node is administratively disabled
      if (normalizedStatus === 'disabled' || normalizedStatus === 'disable' || 
          normalizedStatus === 'user-disabled' || normalizedStatus === 'monitor-disabled') {
        return 'disabled'
      }
      
      // All other states show as enabled (Green dot)
      return 'enabled'
    }

    // Environment color mapping function - consistent colors for each environment
    const getEnvironmentColor = (envName) => {
      if (!envName) return 'blue-grey-8'
      
      const cleanEnvName = envName.trim()
      const envColorMap = {
        'Production FW': 'red-10',
        'FQDN2.0 ADMIN FW': 'deep-purple-10', 
        'UAT FW': 'blue-10',
        'Bravo FW': 'orange-10',
        'Alpha FW': 'green-10',
        'Charlie FW': 'teal-10',
        'Delta FW': 'indigo-10',
        'LoadTest FW': 'brown-10',
        'Admin FW': 'pink-10'
      }
      
      return envColorMap[cleanEnvName] || 'grey-8'
    }

    // Zone color mapping function - sequential assignment for maximum differentiation
    const zoneColorMap = ref(new Map())
    const zoneColorCounter = ref(0)

    // Group member search and display control
    const groupSearchFilters = ref({})
    const showAllMembers = ref({})

    // Search history functionality
    const searchHistory = ref([])
    const showSearchHistory = ref(false)
    const loadingHistory = ref(false)

    // Infrastructure Mapping Table columns
    const infrastructureMappingColumns = [
      {
        name: 'expand',
        label: '',
        field: 'id',
        align: 'center',
        style: 'width: 50px'
      },
      {
        name: 'name',
        required: true,
        label: 'Address Group Name',
        align: 'left',
        field: 'name',
        sortable: true
      },
      {
        name: 'environment',
        required: true,
        label: 'Infrastructure/Environment',
        align: 'center',
        field: 'environment',
        sortable: true
      },
      {
        name: 'member_count',
        required: true,
        label: 'Members',
        align: 'center',
        field: row => row.member_count || JSON.parse(row.members || '[]').length,
        sortable: true
      }
    ]

    // Address Objects Table columns
    const addressObjectsColumns = [
      {
        name: 'name',
        required: true,
        label: 'Address Object Name',
        align: 'left',
        field: 'name',
        sortable: true
      },
      {
        name: 'ip_address',
        required: true,
        label: 'IP Address/CIDR',
        align: 'left',
        field: row => row.cidr_notation || (row.ip_address && row.object_type === 'host' ? row.ip_address + '/32' : row.ip_address) || 'N/A',
        sortable: true
      },
      {
        name: 'object_type',
        required: true,
        label: 'Type',
        align: 'center',
        field: 'object_type',
        sortable: true
      },
      {
        name: 'environment',
        required: true,
        label: 'Infrastructure/Environment',
        align: 'center',
        field: 'environment',
        sortable: true
      }
    ]

    const getZoneColor = (zoneName) => {
      if (!zoneName) return 'blue-grey-8'
      
      // Clean the zone name (trim whitespace)
      const cleanZoneName = zoneName.trim()
      
      // Check if we already have a color for this zone
      if (zoneColorMap.value.has(cleanZoneName)) {
        return zoneColorMap.value.get(cleanZoneName)
      }
      
      // Define color palette for zones - muted tones; env chips use the darkest (-10) shades
      // Muted, low-saturation tones so zones stay distinguishable without a rainbow
      const colors = [
        'blue-grey-7', 'teal-8', 'indigo-6', 'brown-7', 'cyan-9',
        'deep-purple-5', 'green-8', 'blue-grey-9', 'orange-9', 'light-blue-9',
        'pink-8', 'lime-10', 'purple-8'
      ]
      
      // Assign colors sequentially to ensure each zone gets a different color
      const assignedColor = colors[zoneColorCounter.value % colors.length]
      zoneColorCounter.value++
      
      // Store the mapping for future use
      zoneColorMap.value.set(cleanZoneName, assignedColor)

      return assignedColor
    }

    // CIDR-based green color function - darker green for more specific (/32), lighter for less specific (/8, /16, /24)
    const getCidrGreenColor = (ipWithCidr) => {
      if (!ipWithCidr) return 'green-5' // Default green if no CIDR info
      
      // Extract CIDR prefix from ip string (e.g., "192.168.1.1/24" -> 24)
      const cidrMatch = ipWithCidr.toString().match(/\/(\d+)/)
      const cidrPrefix = cidrMatch ? parseInt(cidrMatch[1]) : 32 // Default to /32 if no CIDR found
      
      // Map CIDR prefix to green shade:
      // /32 (host) = darkest green (green-9)
      // /31 = green-8  
      // /30 = green-7
      // /29-/25 = green-6
      // /24 (class C) = green-5
      // /23-/17 = green-4
      // /16 (class B) = green-3
      // /15-/9 = green-2
      // /8 (class A) and wider = lightest green (green-1)
      
      if (cidrPrefix >= 32) return 'green-9'      // /32 - most specific (darkest)
      if (cidrPrefix >= 31) return 'green-8'      // /31
      if (cidrPrefix >= 30) return 'green-7'      // /30
      if (cidrPrefix >= 25) return 'green-6'      // /29-/25
      if (cidrPrefix >= 24) return 'green-5'      // /24
      if (cidrPrefix >= 17) return 'green-4'      // /23-/17
      if (cidrPrefix >= 16) return 'green-3'      // /16
      if (cidrPrefix >= 9) return 'green-2'       // /15-/9
      return 'green-1'                            // /8 and wider (lightest)
    }

    // Get matched address color based on CIDR accuracy from address_mappings
    const getMatchedAddressColor = (addressName, addressMappings) => {
      if (!addressMappings || !addressName) return 'green-5'
      
      const mapping = addressMappings[addressName]
      if (!mapping) return 'green-5'
      
      // Use cidr_notation first, then ip_address with /32 fallback for hosts
      const cidrInfo = mapping.cidr_notation || 
                       (mapping.ip_address && mapping.object_type === 'host' ? mapping.ip_address + '/32' : mapping.ip_address)
      
      return getCidrGreenColor(cidrInfo)
    }

    // Get count of mapped FQDN results for NAT translations
    const getMappedFqdnCount = () => {
      if (!searchResults.value?.mapped_fqdn_results?.fqdn_mappings) return 0

      return searchResults.value.mapped_fqdn_results.fqdn_mappings.reduce((total, mapping) => {
        return total + (mapping.fqdn_records?.length || 0)
      }, 0)
    }

    const getEnhancedNatFqdnRecords = () => {
      if (!searchResults.value?.mapped_fqdn_results?.fqdn_mappings) return []

      const allRecords = []

      searchResults.value.mapped_fqdn_results.fqdn_mappings.forEach(mapping => {
        if (mapping.fqdn_records && mapping.fqdn_records.length > 0) {
          mapping.fqdn_records.forEach(record => {
            allRecords.push({
              ...record,
              nat_translation: `${searchResults.value.ip_address} → ${mapping.public_ip}`
            })
          })
        }
      })

      return allRecords
    }

    const customSort = (rows, sortBy, descending) => {
      const data = [...rows]
      
      if (sortBy) {
        data.sort((a, b) => {
          const aVal = a[sortBy]
          const bVal = b[sortBy]
          
          // Handle policy_id numeric sorting
          if (sortBy === 'policy_id') {
            const aNum = parseInt(aVal) || 0
            const bNum = parseInt(bVal) || 0
            return descending ? bNum - aNum : aNum - bNum
          }
          
          // Handle string sorting
          if (typeof aVal === 'string' && typeof bVal === 'string') {
            return descending 
              ? bVal.localeCompare(aVal)
              : aVal.localeCompare(bVal)
          }
          
          // Handle null/undefined values
          if (aVal === null || aVal === undefined) return descending ? 1 : -1
          if (bVal === null || bVal === undefined) return descending ? -1 : 1
          
          // Default comparison
          return descending ? bVal - aVal : aVal - bVal
        })
      }
      
      return data
    }

    const getColumnWidth = (columnName) => {
      const widths = {
        'expand': '50px',
        'environment': '90px', 
        'source_zone': '80px',
        'destination_zone': '80px',
        'policy_id': '70px',
        'name': '140px',
        'source_addresses': '180px',
        'destination_addresses': '180px', 
        'services': '110px',
        'match_details': '150px',
        'action': '80px'
      }
      return widths[columnName] || 'auto'
    }

    const getNatColumnWidth = (columnName) => {
      const widths = {
        'expand': '60px',
        'environment': '110px', 
        'policy_id': '80px',
        'source_zone': '90px',
        'destination_zone': '90px',
        'source_addresses': '200px',
        'destination_addresses': '200px', 
        'source_translation': '180px',
        'status': '80px'
      }
      return widths[columnName] || 'auto'
    }

    const getTranslationDisplay = (translation) => {
      if (!translation) return '-'
      try {
        const parsed = typeof translation === 'string' ? JSON.parse(translation) : translation
        if (typeof parsed === 'object') {
          if (parsed.translated_ip) return parsed.translated_ip
          if (parsed.translated_address) return parsed.translated_address
          if (parsed.interface) return `Interface: ${parsed.interface}`
          return 'Translation configured'
        }
        return String(parsed)
      } catch {
        return String(translation)
      }
    }

    const getTranslationDetails = (translation) => {
      if (!translation) return 'No translation configured'
      try {
        const parsed = typeof translation === 'string' ? JSON.parse(translation) : translation
        if (typeof parsed === 'object') {
          const details = []
          if (parsed.type) details.push(`Type: ${parsed.type}`)
          if (parsed.translated_ip) details.push(`IP: ${parsed.translated_ip}`)
          if (parsed.translated_address) details.push(`Address: ${parsed.translated_address}`)
          if (parsed.interface) details.push(`Interface: ${parsed.interface}`)
          if (parsed.bidirectional !== undefined) details.push(`Bidirectional: ${parsed.bidirectional}`)
          return details.length > 0 ? details.join(', ') : 'Translation configured'
        }
        return String(parsed)
      } catch {
        return String(translation)
      }
    }
    
    // Toggle functions for mobile card layouts
    const togglePolicyExpansion = (policyId) => {
      const index = expandedPolicies.value.indexOf(policyId)
      if (index > -1) {
        expandedPolicies.value.splice(index, 1)
      } else {
        expandedPolicies.value.push(policyId)
      }
    }
    
    const toggleNatPolicyExpansion = (policyId) => {
      const index = expandedNatPolicies.value.indexOf(policyId)
      if (index > -1) {
        expandedNatPolicies.value.splice(index, 1)
      } else {
        expandedNatPolicies.value.push(policyId)
      }
    }

    // Group expansion functions
    const toggleGroupExpansion = (groupId) => {
      expandedGroups.value[groupId] = !expandedGroups.value[groupId]
    }

    const togglePolicyGroupExpansion = (policyGroupKey) => {
      expandedPolicyGroups.value[policyGroupKey] = !expandedPolicyGroups.value[policyGroupKey]
    }
    const toggleNestedGroupExpansion = (nestedGroupKey) => {
      expandedNestedGroups.value[nestedGroupKey] = !expandedNestedGroups.value[nestedGroupKey]
    }

    // Safe JSON parser for member details
    const safeParseMemberDetails = (memberDetails) => {
      if (!memberDetails) return []
      if (typeof memberDetails === 'object' && Array.isArray(memberDetails)) {
        return memberDetails
      }
      if (typeof memberDetails === 'string') {
        try {
          const parsed = JSON.parse(memberDetails)
          if (Array.isArray(parsed)) {
            return parsed
          }
        } catch (e) {
          console.warn('Failed to parse member_details:', memberDetails)
        }
      }
      return []
    }

    // Safe parser for hierarchical member details
    const safeParseHierarchicalMembers = (hierarchicalMembers) => {
      if (!hierarchicalMembers) return []
      if (typeof hierarchicalMembers === 'object' && Array.isArray(hierarchicalMembers)) {
        return hierarchicalMembers
      }
      if (typeof hierarchicalMembers === 'string') {
        try {
          const parsed = JSON.parse(hierarchicalMembers)
          if (Array.isArray(parsed)) {
            return parsed
          }
        } catch (e) {
          console.warn('Failed to parse hierarchical_members:', hierarchicalMembers)
        }
      }
      return []
    }

    const getMemberChipColor = (memberType, memberName = '') => {
      // Check if this member matches the current search query
      const isSearchMatch = searchQuery.value && memberName.toLowerCase().includes(searchQuery.value.toLowerCase())

      switch (memberType) {
        case 'address':
          return isSearchMatch ? 'green-6' : 'grey-6'
        case 'vip': {
          // Check if VIP member name matches any address object in search results
          const addressObjects = searchResults.value?.firewall_results?.address_objects || []
          const isInAddressObjects = addressObjects.some(obj => obj.name === memberName)

          // If VIP member is in address objects, use same color as address objects (green if match, grey if not)
          if (isInAddressObjects) {
            return isSearchMatch ? 'green-6' : 'grey-6'
          }

          // Otherwise use a muted teal color for VIPs not in address list
          return isSearchMatch ? 'teal-4' : 'teal-3'
        }
        case 'group':
          return isSearchMatch ? 'blue-6' : 'blue-grey-6'
        case 'missing':
          return 'orange-6'
        case 'circular':
          return 'red-6'
        default:
          return 'grey-6'
      }
    }

    // Filter members based on search term
    const getFilteredMembers = (memberDetails, groupId) => {
      if (!memberDetails) return []

      const members = safeParseMemberDetails(memberDetails)
      const searchTerm = groupSearchFilters.value[groupId]

      if (!searchTerm || !searchTerm.trim()) {
        return members
      }

      const searchLower = searchTerm.toLowerCase().trim()
      return members.filter(member =>
        member && member.name && member.name.toLowerCase().includes(searchLower)
      )
    }

    // Get displayed members based on filter and show all setting
    const getDisplayedMembers = (memberDetails, groupId) => {
      const filteredMembers = getFilteredMembers(memberDetails, groupId)
      const showAll = showAllMembers.value[groupId]

      if (showAll || filteredMembers.length <= 50) {
        return filteredMembers
      }

      return filteredMembers.slice(0, 50)
    }

    // Toggle show all members for a specific group
    const toggleShowAllMembers = (groupId) => {
      showAllMembers.value[groupId] = !showAllMembers.value[groupId]
    }

    // Policy-specific filtering functions
    const getPolicyFilteredMembers = (memberDetails, policyGroupKey) => {
      if (!memberDetails) return []
      const members = safeParseMemberDetails(memberDetails)
      const searchTerm = groupSearchFilters.value[policyGroupKey]
      if (!searchTerm || !searchTerm.trim()) {
        return members
      }
      const searchLower = searchTerm.toLowerCase().trim()
      return members.filter(member =>
        member && member.name && member.name.toLowerCase().includes(searchLower)
      )
    }

    // Get displayed members for policy groups based on filter and show all setting
    const getPolicyDisplayedMembers = (memberDetails, policyGroupKey) => {
      const filteredMembers = getPolicyFilteredMembers(memberDetails, policyGroupKey)
      const showAll = showAllMembers.value[policyGroupKey]
      if (showAll || filteredMembers.length <= 50) {
        return filteredMembers
      }
      return filteredMembers.slice(0, 50)
    }

    // Function to update available environments based on search results
    const updateAvailableEnvironments = () => {
      if (!searchResults.value) return
      
      const environments = new Set()
      
      // Collect from firewall policies
      if (searchResults.value.firewall_results?.policies) {
        searchResults.value.firewall_results.policies.forEach(policy => {
          if (policy.environment) environments.add(policy.environment)
        })
      }
      
      // Collect from NAT policies
      if (searchResults.value.firewall_results?.nat_policies) {
        searchResults.value.firewall_results.nat_policies.forEach(policy => {
          if (policy.environment) environments.add(policy.environment)
        })
      }
      
      // Collect from LTM virtual servers
      if (searchResults.value.ltm_results?.virtual_servers) {
        searchResults.value.ltm_results.virtual_servers.forEach(vs => {
          if (vs.virtual_server.environment) environments.add(vs.virtual_server.environment)
        })
      }
      
      // Convert to options format for q-select
      availableEnvironments.value = Array.from(environments)
        .sort()
        .map(env => ({ label: env, value: env }))
    }

    // Function to clear environment filter
    const clearEnvironmentFilter = () => {
      selectedEnvironments.value = []
    }

    // Helper functions to filter results by environment
    const filterAddressObjectsByEnvironment = (addressObjects) => {
      if (!addressObjects) return []
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return addressObjects.filter(obj => selectedEnvironments.value.includes(obj.environment))
      }
      return addressObjects
    }

    const filterPoliciesByEnvironment = (policies) => {
      if (!policies) return []
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return policies.filter(policy => selectedEnvironments.value.includes(policy.environment))
      }
      return policies
    }

    const filterAddressGroupsByEnvironment = (addressGroups) => {
      if (!addressGroups) return []
      if (selectedEnvironments.value && selectedEnvironments.value.length > 0) {
        return addressGroups.filter(group => selectedEnvironments.value.includes(group.environment))
      }
      return addressGroups
    }

    // Infrastructure filtering computed properties and functions
    const visibleInfrastructures = computed(() => availableInfrastructures.value.filter(i => i.visible !== false))

    const selectedInfrastructuresCount = computed(() => {
      return visibleInfrastructures.value.filter(i => infraToggleStates.value[i.key]).length
    })

    const getInfrastructureFromFilename = (filename) => {
      const mapping = {
        'DELTA-LTM': { key: 'DELTA', label: 'Delta', visible: false, icon: 'business', color: 'blue' },
        'DELTA-FW01_': { key: 'DELTA', label: 'Delta', visible: false, icon: 'business', color: 'blue' },
        'DELTA-ADMIN-FW01': { key: 'DELTA', label: 'Delta', visible: false, icon: 'business', color: 'blue' },
        'CHARLIE-LTM': { key: 'CHARLIE', label: 'Charlie', icon: 'cloud', color: 'teal' },
        'CHARLIE-FW01': { key: 'CHARLIE', label: 'Charlie', icon: 'cloud', color: 'teal' },
        'BRAVO-LTM': { key: 'BRAVO', label: 'Bravo', icon: 'wb_sunny', color: 'orange' },
        'BRAVO-FW01': { key: 'BRAVO', label: 'Bravo', icon: 'wb_sunny', color: 'orange' },
        'ALPHA-FW01': { key: 'ALPHA', label: 'Alpha', icon: 'diamond', color: 'green' },
        'ALPHA-LTM01': { key: 'ALPHA', label: 'Alpha', icon: 'diamond', color: 'green' },
        'ADMIN-LTM': { key: 'ADMIN', label: 'Admin', visible: false, icon: 'settings', color: 'purple' },
        'ADMIN-FW01': { key: 'ADMIN', label: 'Admin', visible: false, icon: 'settings', color: 'purple' },
        'UAT-FW01': { key: 'UAT', label: 'UAT', visible: false, icon: 'construction', color: 'amber' },
        'UAT-SLB01': { key: 'UAT', label: 'UAT', visible: false, icon: 'construction', color: 'amber' },
        'LoadTest-FW01': { key: 'LOADTEST', label: 'LOADTEST', visible: false, icon: 'speed', color: 'deep-purple' },
        'LoadTest-LTM01': { key: 'LOADTEST', label: 'LOADTEST', visible: false, icon: 'speed', color: 'deep-purple' }
      }

      for (const [pattern, infra] of Object.entries(mapping)) {
        if (filename.includes(pattern)) {
          return infra
        }
      }
      return null
    }

    const loadAvailableInfrastructures = async () => {
      try {
        const response = await api.get('/config/status')
        if (response.data && response.data.success) {
          const infrastructures = new Map()

          response.data.files.forEach(file => {
            const infra = getInfrastructureFromFilename(file.filename)
            if (infra) {
              infrastructures.set(infra.key, infra)
            }
          })

          // Order according to Parsed Configuration Files display order
          const displayOrder = ['ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'UAT', 'ADMIN', 'LOADTEST']
          availableInfrastructures.value = Array.from(infrastructures.values())
            .sort((a, b) => {
              const aIndex = displayOrder.indexOf(a.key)
              const bIndex = displayOrder.indexOf(b.key)
              return aIndex - bIndex
            })

          // Initialize toggle states - all enabled by default
          const initialStates = {}
          availableInfrastructures.value.forEach(infra => {
            initialStates[infra.key] = true
          })
          infraToggleStates.value = initialStates
        }
      } catch (error) {
        console.error('Failed to load infrastructure options:', error)
      }
    }

    const selectAllInfrastructures = () => {
      visibleInfrastructures.value.forEach(infra => {
        infraToggleStates.value[infra.key] = true
      })
    }

    const deselectAllInfrastructures = () => {
      visibleInfrastructures.value.forEach(infra => {
        infraToggleStates.value[infra.key] = false
      })
    }

    const getSelectedInfrastructureKeys = () => {
      // Hidden infrastructures are searched only while at least one visible toggle is on
      const hiddenKeys = availableInfrastructures.value.filter(i => i.visible === false).map(i => i.key)
      return Object.keys(infraToggleStates.value).filter(key =>
        infraToggleStates.value[key] && (!hiddenKeys.includes(key) || selectedInfrastructuresCount.value > 0))
    }

    const performSearch = async () => {
      if (!searchQuery.value || !isValidQuery.value) {
        const message = searchType.value === 'ip' 
          ? 'Please enter a valid IP address'
          : 'Please enter a valid object name (at least 3 characters)'
        
        Notify.create({
          type: 'warning',
          message: message,
          timeout: 3000
        })
        return
      }

      searching.value = true
      searchResults.value = null  // Clear previous results
      selectedEnvironments.value = []  // Clear environment filter
      currentPage.value = 1  // Reset pagination
      paginationInfo.value = null
      
      // Clear computed property caches to improve performance

      try {
        let searchValue = searchQuery.value.trim()

        // Auto-remove _32 suffix if present (commonly used CIDR notation for single IPs)
        if (searchValue.endsWith('_32')) {
          searchValue = searchValue.slice(0, -3)
        }

        let response
        
        // Get selected infrastructure keys for filtering
        const selectedInfraKeys = getSelectedInfrastructureKeys()

        // Check if we have multiple IPs
        if (isMultipleIps.value) {
          const ipAddresses = parseIpAddresses(searchValue)

          response = await api.post('/search/bulk_ip', {
            ip_addresses: ipAddresses,
            search_direction: ipSearchDirection.value,
            infrastructure_filter: selectedInfraKeys
          })
          
          if (response.data && response.data.success) {
            bulkResults.value = response.data.bulk_results
            searchResults.value = {
              success: true,
              is_bulk: true,
              bulk_results: response.data.bulk_results,
              summary: response.data.summary
            }
          }
        } else {
          
          if (searchType.value === 'ip') {
            response = await api.post('/search/ip', {
              ip_address: searchValue,
              search_direction: ipSearchDirection.value,
              page: currentPage.value,
              page_size: pageSize.value,
              infrastructure_filter: selectedInfraKeys
            })
          } else if (searchType.value === 'fqdn') {
            response = await api.post('/search/fqdn', {
              search_term: searchValue,
              infrastructure_filter: selectedInfraKeys
            })
          } else {
            response = await api.post('/search/object', {
              object_name: searchValue,
              infrastructure_filter: selectedInfraKeys
            })
          }
        }


        if (response.data && response.data.success) {
          // Only process regular results for non-bulk searches
          if (!isMultipleIps.value) {
            searchResults.value = response.data

            // Store pagination info
            if (response.data.firewall_results && response.data.firewall_results.pagination) {
              paginationInfo.value = response.data.firewall_results.pagination
            }
            
            // Update available environments for filter
            updateAvailableEnvironments()

          // Switch to tab with results
          if (response.data.search_type === 'fqdn') {
            activeTab.value = 'fqdn'
          } else if (response.data.summary && response.data.summary.firewall_matches > 0) {
            activeTab.value = 'firewall'
          } else if (response.data.summary && response.data.summary.ltm_matches > 0) {
            activeTab.value = 'ltm'
          }

          const totalMatches = response.data.summary ? response.data.summary.total_matches : 0
          if (totalMatches === 0) {
            const searchTarget = searchType.value === 'ip' ? 'IP address' : searchType.value === 'fqdn' ? 'FQDN' : 'object name'
            Notify.create({
              type: 'info',
              message: `No matches found for the given ${searchTarget}`,
              timeout: 3000
            })
          } else {
            const extraInfo = searchType.value === 'object' && response.data.summary.address_objects && response.data.summary.address_groups
              ? `, Objects: ${response.data.summary.address_objects}, Groups: ${response.data.summary.address_groups}`
              : ''
            
            let message = `Found ${totalMatches} matches (LTM: ${response.data.summary.ltm_matches}, Firewall: ${response.data.summary.firewall_matches}${extraInfo})`
            
            // Add truncation notice for very large result sets only
            if (totalMatches >= 5000 && searchType.value === 'object') {
              message += ' - Large result set may take longer to display'
            }
            
            Notify.create({
              type: 'positive',
              message: message,
              timeout: 4000
            })
          }
          }
        } else {
          throw new Error('Invalid response format from server')
        }
      } catch (error) {
        console.error('Search Error:', error)
        searchResults.value = null
        Notify.create({
          type: 'negative',
          message: 'Search failed: ' + (error.response?.data?.message || error.message),
          timeout: 5000
        })
      } finally {
        searching.value = false
      }
    }

    // Load more results for pagination
    const loadMore = async () => {
      if (loadingMore.value || !paginationInfo.value) return
      
      loadingMore.value = true
      currentPage.value += 1
      
      try {
        const searchValue = searchQuery.value.trim()
        const selectedInfraKeys = getSelectedInfrastructureKeys()
        const response = await api.post('/search/ip', {
          ip_address: searchValue,
          search_direction: ipSearchDirection.value,
          page: currentPage.value,
          page_size: pageSize.value,
          infrastructure_filter: selectedInfraKeys
        })
        
        if (response.data && response.data.success) {
          // Append new results to existing results
          if (response.data.firewall_results) {
            if (response.data.firewall_results.policies) {
              searchResults.value.firewall_results.policies.push(...response.data.firewall_results.policies)
            }
            if (response.data.firewall_results.nat_policies) {
              searchResults.value.firewall_results.nat_policies.push(...response.data.firewall_results.nat_policies)
            }
            
            // Update pagination info
            if (response.data.firewall_results.pagination) {
              paginationInfo.value = response.data.firewall_results.pagination
            }
          }
          
          // Update available environments for filter
          updateAvailableEnvironments()
          
          Notify.create({
            type: 'positive',
            message: `Loaded more results (Page ${currentPage.value})`,
            timeout: 2000
          })
        }
      } catch (error) {
        console.error('Load More Error:', error)
        currentPage.value -= 1  // Revert page increment on error
        Notify.create({
          type: 'negative',
          message: 'Failed to load more results: ' + (error.response?.data?.message || error.message),
          timeout: 5000
        })
      } finally {
        loadingMore.value = false
      }
    }

    // Helper function to clean display names by removing /Common/ prefix
    const cleanName = (name) => {
      if (!name) return name
      return name.replace('/Common/', '')
    }

    // Helper function to clean IP addresses by removing /Common/ prefix  
    const cleanIp = (ip) => {
      if (!ip) return ip
      return ip.replace('/Common/', '')
    }

    // Format IP address with classification (Virtual Server IP or Node IP)
    const formatIpWithClassification = (ip, ipClassification) => {
      if (!ipClassification) {
        return ip
      }
      
      if (ipClassification.type === 'virtual_server') {
        return `${ip} (Virtual Server IP)`
      } else if (ipClassification.type === 'node') {
        return `${ip} (Node IP)`
      } else {
        return ip
      }
    }

    const formatDate = (dateString) => {
      if (!dateString) return 'N/A'
      try {
        const date = new Date(dateString)
        return date.toLocaleDateString('en-US', { 
          year: 'numeric', 
          month: 'short', 
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        })
      } catch (e) {
        return dateString
      }
    }

    // Function to perform a clickable search when user clicks on IP/hostname/VS name
    const performClickableSearch = async (searchTerm) => {
      if (!searchTerm || searchTerm.trim() === '') {
        return
      }
      
      // Clean the search term (remove /Common/ prefix, trailing dots, subnet masks, _32 suffix, and whitespace)
      let cleanedTerm = searchTerm.replace('/Common/', '').trim().replace(/\.$/, '').replace(/\/\d+$/, '')

      // Auto-remove _32 suffix if present
      if (cleanedTerm.endsWith('_32')) {
        cleanedTerm = cleanedTerm.slice(0, -3)
      }
      
      // Open the search in a new tab by constructing the URL with search parameters
      const currentUrl = new URL(window.location.href)
      const newUrl = new URL(currentUrl.origin + currentUrl.pathname)
      
      // Add search query as URL parameter
      newUrl.searchParams.set('search', cleanedTerm)
      
      // Open in new tab
      window.open(newUrl.toString(), '_blank')
      
      // Show notification about the new search
      Notify.create({
        type: 'info',
        message: `Opening search for: ${cleanedTerm} in new tab`,
        timeout: 2000
      })
    }

    // Handle URL parameters on page load
    onMounted(() => {
      // Load available infrastructures
      loadAvailableInfrastructures()

      const urlParams = new URLSearchParams(window.location.search)
      const searchParam = urlParams.get('search')
      
      if (searchParam && searchParam.trim()) {
        const cleanedTerm = searchParam.trim()
        
        // Auto-detect search type
        const isIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(cleanedTerm)
        const isFqdn = /^[a-zA-Z0-9][a-zA-Z0-9-._]*\.[a-zA-Z]{2,}$/.test(cleanedTerm)
        
        // Set search query and type
        searchQuery.value = cleanedTerm
        
        if (isIp) {
          searchType.value = 'ip'
        } else if (isFqdn) {
          searchType.value = 'fqdn'
        } else {
          searchType.value = 'object'
        }
        
        // Automatically perform the search
        performSearch()
      }
    })

    // Function to get color for FQDN owner column
    const getOwnerColor = (owner) => {
      if (!owner || owner === 'N/A') return 'grey-5'
      // Simple hash-based color assignment for consistent coloring
      const colors = ['primary', 'secondary', 'accent', 'positive', 'negative', 'warning', 'info']
      let hash = 0
      for (let i = 0; i < owner.length; i++) {
        hash = owner.charCodeAt(i) + ((hash << 5) - hash)
      }
      return colors[Math.abs(hash) % colors.length]
    }

    // Search history functions
    const loadSearchHistory = async () => {
      if (loadingHistory.value) return
      loadingHistory.value = true
      try {
        const response = await api.get('/search/history?limit=10')
        if (response.data.success) {
          searchHistory.value = response.data.history
        }
      } catch (error) {
        console.error('Failed to load search history:', error)
      } finally {
        loadingHistory.value = false
      }
    }

    const selectHistoryItem = (item) => {
      searchQuery.value = item.search_query
      // Auto-detect search type and perform search
      autoDetectSearchType(item.search_query)
      performSearch()
    }

    // FQDN copy functions
    const hasAnyFqdnResults = () => {
      return (
        (searchResults.value.fqdn_results && searchResults.value.fqdn_results.records && searchResults.value.fqdn_results.records.length > 0) ||
        (searchResults.value.object_resolution && searchResults.value.object_resolution.success && searchResults.value.object_resolution.fqdn_results && searchResults.value.object_resolution.fqdn_results.count > 0) ||
        (searchResults.value.vs_mapping && searchResults.value.vs_mapping.success && searchResults.value.vs_mapping.vs_fqdn_results && searchResults.value.vs_mapping.vs_fqdn_results.count > 0) ||
        (searchResults.value.mapped_fqdn_results && searchResults.value.mapped_fqdn_results.success && searchResults.value.mapped_fqdn_results.count > 0)
      )
    }

    const getAllFqdnRecords = () => {
      let allRecords = []

      // Regular FQDN results
      if (searchResults.value.fqdn_results && searchResults.value.fqdn_results.records) {
        allRecords = allRecords.concat(searchResults.value.fqdn_results.records)
      }

      // Object resolution FQDN results
      if (searchResults.value.object_resolution && searchResults.value.object_resolution.fqdn_results && searchResults.value.object_resolution.fqdn_results.records) {
        allRecords = allRecords.concat(searchResults.value.object_resolution.fqdn_results.records)
      }

      // VS mapping FQDN results
      if (searchResults.value.vs_mapping && searchResults.value.vs_mapping.vs_fqdn_results && searchResults.value.vs_mapping.vs_fqdn_results.records) {
        allRecords = allRecords.concat(searchResults.value.vs_mapping.vs_fqdn_results.records)
      }

      // NAT-mapped FQDN results (using the enhanced structure)
      if (searchResults.value.mapped_fqdn_results && searchResults.value.mapped_fqdn_results.fqdn_mappings) {
        searchResults.value.mapped_fqdn_results.fqdn_mappings.forEach(mapping => {
          if (mapping.fqdn_records && mapping.fqdn_records.length > 0) {
            mapping.fqdn_records.forEach(record => {
              allRecords.push({
                ...record,
                nat_translation: `${searchResults.value.ip_address} → ${mapping.public_ip}`
              })
            })
          }
        })
      }

      return allRecords
    }

    const copyToClipboardFallback = (text) => {
      // Create a temporary textarea element
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)

      // Select and copy the text
      textarea.focus()
      textarea.select()

      try {
        const successful = document.execCommand('copy')
        document.body.removeChild(textarea)
        return successful
      } catch (err) {
        document.body.removeChild(textarea)
        return false
      }
    }

    const copyAllFqdns = async () => {
      try {
        const records = getAllFqdnRecords()
        const fqdns = [...new Set(records.map(record => record.fqdn))].sort()
        const text = fqdns.join('\n')

        let success = false

        // Try modern clipboard API first
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(text)
            success = true
          } catch (err) {
            // Fall back to legacy method
            success = copyToClipboardFallback(text)
          }
        } else {
          // Use legacy method directly
          success = copyToClipboardFallback(text)
        }

        if (success) {
          Notify.create({
            message: `Copied ${fqdns.length} unique FQDNs to clipboard`,
            color: 'positive',
            timeout: 2000
          })
        } else {
          throw new Error('Copy failed')
        }
      } catch (error) {
        Notify.create({
          message: 'Failed to copy to clipboard',
          color: 'negative',
          timeout: 2000
        })
      }
    }

    const copyAllIps = async () => {
      try {
        const records = getAllFqdnRecords()
        const ips = [...new Set(records.map(record => record.ip))].sort()
        const text = ips.join('\n')

        let success = false

        // Try modern clipboard API first
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(text)
            success = true
          } catch (err) {
            // Fall back to legacy method
            success = copyToClipboardFallback(text)
          }
        } else {
          // Use legacy method directly
          success = copyToClipboardFallback(text)
        }

        if (success) {
          Notify.create({
            message: `Copied ${ips.length} unique IP addresses to clipboard`,
            color: 'positive',
            timeout: 2000
          })
        } else {
          throw new Error('Copy failed')
        }
      } catch (error) {
        Notify.create({
          message: 'Failed to copy to clipboard',
          color: 'negative',
          timeout: 2000
        })
      }
    }

    const copyFqdnTable = async () => {
      try {
        const records = getAllFqdnRecords()

        // Create simple FQDN and IP format (tab-separated)
        let content = ''
        records.forEach(record => {
          content += `${record.fqdn || ''}\t${record.ip || ''}\n`
        })

        let success = false

        // Try modern clipboard API first
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(content)
            success = true
          } catch (err) {
            // Fall back to legacy method
            success = copyToClipboardFallback(content)
          }
        } else {
          // Use legacy method directly
          success = copyToClipboardFallback(content)
        }

        if (success) {
          Notify.create({
            message: `Copied ${records.length} FQDN and IP pairs to clipboard`,
            color: 'positive',
            timeout: 2000
          })
        } else {
          throw new Error('Copy failed')
        }
      } catch (error) {
        Notify.create({
          message: 'Failed to copy to clipboard',
          color: 'negative',
          timeout: 2000
        })
      }
    }

    const clearSearchHistory = async () => {
      try {
        const response = await api.post('/search/history/clear')
        if (response.data.success) {
          searchHistory.value = []
          Notify.create({
            message: 'Search history cleared',
            color: 'positive',
            timeout: 2000
          })
        }
      } catch (error) {
        console.error('Failed to clear search history:', error)
        Notify.create({
          message: 'Failed to clear search history',
          color: 'negative',
          timeout: 2000
        })
      }
    }


    return {
      searchType,
      searchTypes,
      searchQuery,
      searching,
      searchResults,
      activeTab,
      expandedPolicies,
      expandedChips,
      pagination,
      selectedEnvironments,
      availableEnvironments,
      isMultipleIps,
      bulkResults,
      ipSearchDirection,
      // Infrastructure filtering
      availableInfrastructures,
      visibleInfrastructures,
      infraToggleStates,
      selectedInfrastructuresCount,
      selectAllInfrastructures,
      deselectAllInfrastructures,
      loadAvailableInfrastructures,
      getSelectedInfrastructureKeys,
      currentPage,
      pageSize,
      loadingMore,
      paginationInfo,
      loadMore,
      parseIpAddresses,
      getIpCount,
      getSearchTypeLabel,
      firewallColumns,
      natPolicyColumns,
      fqdnColumns,
      expandedNatPolicies,
      uniquePolicies,
      filteredNatPolicies,
      filteredLtmResults,
      filteredAddressObjects,
      filteredAddressGroups,
      isValidQuery,
      getValidationRules,
      getInputLabel,
      getPlaceholder,
      getDynamicInputLabel,
      getDynamicPlaceholder,
      autoDetectSearchType,
      updateAvailableEnvironments,
      clearEnvironmentFilter,
      filterAddressObjectsByEnvironment,
      filterPoliciesByEnvironment,
      filterAddressGroupsByEnvironment,
      performSearch,
      toggleChip,
      isChipExpanded,
      getAddressDisplay,
      isIpMatchingSearch,
      getStatusClass,
      getNodeStatusClass,
      getEnvironmentColor,
      getZoneColor,
      infrastructureMappingColumns,
      addressObjectsColumns,
      getCidrGreenColor,
      getMatchedAddressColor,
      zoneColorMap,
      zoneColorCounter,
      customSort,
      getColumnWidth,
      getNatColumnWidth,
      getTranslationDisplay,
      getTranslationDetails,
      cleanName,
      cleanIp,
      formatIpWithClassification,
      formatDate,
      performClickableSearch,
      togglePolicyExpansion,
      toggleNatPolicyExpansion,
      expandedGroups,
      toggleGroupExpansion,
      togglePolicyGroupExpansion,
      toggleNestedGroupExpansion,
      expandedPolicyGroups,
      expandedNestedGroups,
      safeParseMemberDetails,
      safeParseHierarchicalMembers,
      getMemberChipColor,
      groupSearchFilters,
      showAllMembers,
      getFilteredMembers,
      getDisplayedMembers,
      toggleShowAllMembers,
      getPolicyFilteredMembers,
      getPolicyDisplayedMembers,
      getMappedFqdnCount,
      getEnhancedNatFqdnRecords,
      updateUrlWithSearch,
      getOwnerColor,
      // Search history
      searchHistory,
      showSearchHistory,
      loadingHistory,
      loadSearchHistory,
      selectHistoryItem,
      clearSearchHistory,
      // FQDN copy functions
      hasAnyFqdnResults,
      copyToClipboardFallback,
      copyAllFqdns,
      copyAllIps,
      copyFqdnTable
    }
  }
})
</script>

<style scoped>
.search-container {
  width: 100%;
  max-width: none !important;
}

/* Address Group Member Display Styling */
.member-details {
  background: rgba(233, 243, 255, 0.3);
  border-radius: 8px;
  padding: 12px;
  border-left: 4px solid #1976d2;
}

.member-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.member-chip, .nested-chip {
  display: inline-flex;
  align-items: flex-start;
  gap: 4px;
  max-width: 100%;
  flex-wrap: wrap;
  min-height: 40px;
  height: auto !important;
  padding: 8px 12px !important;
}

.member-chip :deep(.q-chip__content), .nested-chip :deep(.q-chip__content) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  white-space: normal;
  line-height: 1.4;
}
.member-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.member-name {
  font-weight: 600;
  color: white !important;
}

.member-separator {
  color: white !important;
  font-weight: 500;
  flex-shrink: 0;
  margin-right: 4px;
}

.member-separator::after {
  content: '';
  flex-basis: 100%;
  height: 0;
}

.member-ip {
  font-family: 'Roboto Mono', monospace;
  color: white !important;
  word-break: break-word;
  flex: 1 1 auto;
  min-width: 0;
}

.nested-members {
  border-left: 2px solid rgba(25, 118, 210, 0.3);
  padding-left: 8px;
  margin-top: 4px;
}

.nested-member-name {
  font-weight: 500;
  font-size: 0.85em;
  color: #333333 !important;
}

.nested-member-ip {
  font-family: 'Roboto Mono', monospace;
  font-size: 0.85em;
  color: #333333 !important;
}

.fallback-members {
  background: rgba(224, 224, 224, 0.3);
  border-radius: 8px;
  padding: 12px;
  border-left: 4px solid #757575;
}

/* LTM Tree Layout Styling - Aligned Grid Layout */
.ltm-tree-container {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 16px;
  align-items: stretch;
}

.ltm-vs-group {
  background: #ffffff;
  border: 2px solid #e3f2fd;
  border-radius: 8px;
  padding: 16px;
  flex: 1 1 380px;
  min-width: 380px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.ltm-tree-item {
  display: flex;
  align-items: center;
  margin: 4px 0;
  padding: 8px 6px;
  border-radius: 6px;
  transition: background-color 0.2s ease;
  min-height: 40px;
}

.ltm-tree-item:hover {
  background-color: rgba(25, 118, 210, 0.06);
}

/* Virtual Server Item */
.ltm-vs-item {
  margin-bottom: 12px;
  padding: 12px 8px;
  border-bottom: 2px solid #e3f2fd;
  background-color: rgba(25, 118, 210, 0.02);
  min-height: 60px;
}

/* Pool Item - indented layout */
.ltm-pool-item {
  margin-left: 32px;
  margin-bottom: 8px;
  padding: 8px 6px;
  background-color: rgba(25, 118, 210, 0.01);
  min-height: 48px;
}

/* Node Item - indented layout */
.ltm-node-item {
  margin-left: 64px;
  margin-bottom: 6px;
  padding: 6px 6px;
  min-height: 44px;
}

/* Node Item with disabled status (black circle) - light grey background */
.ltm-node-item:has(.ltm-status-dot.disabled) {
  background-color: #f5f5f5 !important;
}

.ltm-item-indicator {
  display: flex;
  align-items: center;
  margin-right: 16px;
}

.ltm-status-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  background-color: #000000; /* Default to black - ensures consistency with disabled nodes */
}

/* Status Colors */
.ltm-status-dot.enabled {
  background-color: #00C853 !important; /* Vibrant green - enabled and online */
  opacity: 1 !important; /* Ensure full opacity for maximum vibrancy */
}

.ltm-status-dot.disabled {
  background-color: #000000 !important; /* Pure black - administratively disabled */
  opacity: 1 !important; /* Ensure full opacity for maximum blackness */
}

.ltm-item-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.ltm-item-name {
  font-size: 14px;
  font-weight: 600;
  color: #1976d2;
  line-height: 1.4;
  margin-bottom: 2px;
}

.ltm-item-details {
  font-size: 13px;
  color: #666;
  line-height: 1.3;
  font-weight: 500;
}

/* Different styling for VS, Pool, and Node names */
.ltm-vs-item .ltm-item-name {
  font-size: 16px;
  font-weight: 700;
  color: #0d47a1;
}

.ltm-vs-item .ltm-item-details {
  font-size: 14px;
  color: #424242;
  font-weight: 600;
}

/* LTM VS Header - for environment chip layout */
.ltm-vs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.ltm-environment-chip {
  font-size: 10px !important;
  padding: 4px 8px !important;
  min-height: 22px !important;
  flex-shrink: 0;
  font-weight: 500 !important;
}

.ltm-pool-item .ltm-item-name {
  font-size: 15px;
  font-weight: 600;
  color: #1976d2;
}

.ltm-node-item .ltm-item-name {
  font-size: 14px;
  font-weight: 500;
  color: #424242;
}

/* Responsive design for LTM tree */
@media (max-width: 1200px) {
  .ltm-tree-container {
    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
    gap: 20px;
  }
}

@media (max-width: 768px) {
  .ltm-tree-container {
    grid-template-columns: 1fr;
    gap: 20px;
  }
  
  .ltm-vs-group {
    min-height: 180px;
  }
  
  .ltm-pool-item {
    margin-left: 24px;
  }
  
  .ltm-node-item {
    margin-left: 48px;
  }
}

@media (max-width: 480px) {
  .ltm-vs-group {
    padding: 12px;
    min-height: 160px;
  }
  
  .ltm-pool-item {
    margin-left: 16px;
  }
  
  .ltm-node-item {
    margin-left: 32px;
  }
  
  .ltm-vs-item .ltm-item-name {
    font-size: 15px;
  }
  
  .ltm-pool-item .ltm-item-name {
    font-size: 14px;
  }
  
  .ltm-node-item .ltm-item-name {
    font-size: 13px;
  }
}

/* Responsive Table Layout Control */
.mobile-card-layout {
  display: block;
}

.desktop-table-layout {
  display: none;
}

/* Desktop Layout */
@media (min-width: 1200px) {
  .mobile-card-layout {
    display: none;
  }
  
  .desktop-table-layout {
    display: block;
  }
}

/* Mobile Card Layouts */
.policy-card, .nat-policy-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
  border: 1px solid #e0e0e0;
}

.policy-card:hover, .nat-policy-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transform: translateY(-1px);
}

.policy-card-header, .nat-card-header {
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.policy-id-section {
  display: flex;
  align-items: center;
  flex: 1;
}

.policy-id-text {
  font-size: 18px;
  font-weight: 600;
  color: #1976d2;
  margin: 0;
}

.policy-name {
  font-size: 14px;
  color: #666;
  font-weight: 500;
  margin-top: 4px;
  line-height: 1.4;
}

.policy-card-content, .nat-card-content {
  padding: 16px;
}

.policy-flow, .nat-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 16px;
}

.flow-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.flow-label {
  font-size: 12px;
  color: #666;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.flow-arrow {
  color: #1976d2;
  font-size: 24px;
}

.action-chip {
  font-size: 14px !important;
  font-weight: 600 !important;
  padding: 6px 16px !important;
  text-transform: uppercase;
}

.addresses-preview {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
}

.preview-section {
  margin-bottom: 12px;
}

.preview-label {
  font-size: 12px;
  color: #666;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.chips-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.preview-chip {
  font-size: 11px !important;
  padding: 4px 8px !important;
  border-radius: 6px !important;
  max-width: 150px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.policy-expanded-content, .nat-expanded-content {
  padding: 20px;
  background: #f8f9fa;
}

.detailed-addresses-section {
  padding: 12px !important;
  min-height: 60px;
}

.detail-chip {
  font-size: 11px !important;
  padding: 6px 10px !important;
  border-radius: 6px !important;
  margin: 2px 4px 4px 0 !important;
  max-width: 100%;
  word-wrap: break-word;
  white-space: normal;
  height: auto !important;
  min-height: 24px !important;
}

.chip-content-mobile {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}

.chip-name-mobile {
  font-weight: 600;
  font-size: 11px;
  line-height: 1.2;
}

.chip-ip-mobile {
  font-size: 10px;
  opacity: 0.9;
  line-height: 1.2;
}

.nat-translation {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fff3e0;
  border-radius: 8px;
}

.translation-label {
  font-size: 12px;
  color: #666;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Firewall Table Container and Layout */
.firewall-table-container {
  width: 100%;
  overflow-x: auto;
  margin-bottom: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.firewall-policy-table {
  width: 100% !important;
  min-width: 1200px;
}

.firewall-policy-table :deep(.q-table) {
  width: 100% !important;
}

.firewall-policy-table :deep(.q-table__container) {
  width: 100% !important;
  overflow-x: auto;
}

.firewall-policy-table :deep(table) {
  width: 100% !important;
  table-layout: auto !important;
  border-collapse: separate;
  border-spacing: 0;
}

/* Simplified Column Width Management */
.firewall-policy-table :deep(th),
.firewall-policy-table :deep(td) {
  vertical-align: middle !important;
  border: 1px solid #e0e0e0;
  padding: 8px 12px !important;
}

.firewall-policy-table :deep(tr) {
  min-height: 48px;
}

/* Center aligned columns */
.firewall-policy-table :deep(td[key="expand"]),
.firewall-policy-table :deep(td[key="environment"]),
.firewall-policy-table :deep(td[key="source_zone"]),
.firewall-policy-table :deep(td[key="destination_zone"]),
.firewall-policy-table :deep(td[key="policy_id"]),
.firewall-policy-table :deep(td[key="action"]) {
  text-align: center !important;
}


/* Chip styling for centered columns */
.firewall-policy-table :deep(.q-chip) {
  display: inline-flex !important;
  margin: 0 auto !important;
  vertical-align: middle !important;
}

/* Environment column chips */
.environment-chip {
  font-size: 10px !important;
  padding: 6px 8px !important;
  min-height: 32px !important;
  border-radius: 0px !important;
  max-width: 100px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500 !important;
}

/* Zone column chips */
.zone-column .q-chip {
  font-size: 10px !important;
  padding: 6px 8px !important;
  min-height: 32px !important;
  border-radius: 0px !important;
  max-width: 70px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500 !important;
}

/* Action column chip styling */
.firewall-policy-table :deep(td[key="action"] .q-chip) {
  font-size: 10px !important;
  padding: 4px 8px !important;
  min-height: 22px !important;
  text-transform: uppercase;
  font-weight: 600;
  border-radius: 0px !important;
}

/* Policy name cell styling */
.policy-name-cell {
  max-width: 140px !important;
}

.policy-name-text {
  font-size: 11px !important;
  font-weight: 500;
  line-height: 1.3;
  word-wrap: break-word;
  word-break: break-word;
  white-space: normal;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  text-overflow: ellipsis;
}

/* Address Preview Styling */
.address-preview {
  min-height: 32px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  width: 100%;
  padding: 2px 0;
}

.chips-container {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: flex-start;
  width: 100%;
}

.address-chip {
  font-size: 10px !important;
  max-width: 150px;
  min-width: 60px;
  white-space: normal;
  overflow: visible !important;
  text-overflow: clip !important;
  padding: 4px 8px !important;
  border-radius: 0px !important;
  height: auto !important;
  min-height: 22px !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.3 !important;
  font-weight: 500 !important;
}

.address-chip :deep(.q-chip__content) {
  overflow: visible !important;
  text-overflow: clip !important;
  white-space: normal !important;
  padding: 3px 0 !important;
  font-size: 10px !important;
  font-weight: 500 !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.3 !important;
}

.service-chip {
  font-size: 10px !important;
  max-width: 90px;
  min-width: 40px;
  white-space: normal;
  overflow: visible !important;
  text-overflow: clip !important;
  padding: 4px 8px !important;
  border-radius: 0px !important;
  height: auto !important;
  min-height: 22px !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.3 !important;
  font-weight: 500 !important;
}

.service-chip :deep(.q-chip__content) {
  overflow: visible !important;
  text-overflow: clip !important;
  white-space: normal !important;
  padding: 3px 0 !important;
  font-size: 10px !important;
  font-weight: 500 !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.3 !important;
}

.more-items {
  margin-top: 4px;
}

.more-items .q-btn {
  font-size: 10px !important;
  padding: 4px 8px !important;
  min-height: 24px !important;
}

/* Table Cell Alignment */
.firewall-policy-table :deep(td) {
  vertical-align: top !important;
  padding: 8px 6px !important;
  word-wrap: break-word;
  overflow: visible;
  line-height: 1.3;
}

.firewall-policy-table :deep(th) {
  padding: 8px 6px !important;
  font-weight: bold !important;
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 12px !important;
  background-color: #f5f5f5 !important;
  height: 48px !important;
  min-height: 48px !important;
}

/* General table header styling - center all headers horizontally and vertically */
.q-table :deep(th) {
  text-align: center !important;
  vertical-align: middle !important;
}

/* Sortable Header Styling */
.sortable-header {
  user-select: none;
  transition: background-color 0.2s ease;
  font-size: 14px !important;
  font-weight: 600 !important;
  text-align: center !important;
  vertical-align: middle !important;
  height: 48px !important;
  min-height: 48px !important;
  max-height: 48px !important;
  padding: 8px 6px !important;
  line-height: 1.2 !important;
  white-space: nowrap !important;
  overflow: hidden !important;
}

.sortable-header.cursor-pointer:hover {
  background-color: rgba(25, 118, 210, 0.08) !important;
}

.sortable-header .row {
  width: 100%;
  justify-content: center !important;
  align-items: center !important;
  height: 32px !important;
  min-height: 32px !important;
  max-height: 32px !important;
  line-height: 1.2 !important;
}

/* Force center alignment for all firewall and NAT policy table headers */
.firewall-policy-table .sortable-header,
.nat-policy-table .sortable-header {
  text-align: center !important;
}

.firewall-policy-table .sortable-header .row,
.nat-policy-table .sortable-header .row {
  justify-content: center !important;
  text-align: center !important;
}

.firewall-policy-table .sortable-header span,
.nat-policy-table .sortable-header span {
  text-align: center !important;
  width: 100% !important;
  display: block !important;
}

/* Force all firewall table headers to have identical positioning */
.firewall-policy-table :deep(thead th) {
  height: 48px !important;
  min-height: 48px !important;
  max-height: 48px !important;
  vertical-align: middle !important;
  padding: 8px 6px !important;
  line-height: 1.2 !important;
  display: table-cell !important;
  position: relative !important;
}

.firewall-policy-table :deep(thead th .row) {
  position: absolute !important;
  top: 50% !important;
  left: 50% !important;
  transform: translate(-50%, -50%) !important;
  width: calc(100% - 12px) !important;
  height: auto !important;
  align-items: center !important;
  justify-content: center !important;
}

/* Sort icon styling */
.sortable-header .q-icon {
  color: #1976d2;
  opacity: 0.7;
}

/* Result Tabs */
.result-tabs {
  width: 100%;
}

.result-tabs .q-card {
  width: 100%;
}

/* Ensure full width for tab panels */
.q-tab-panels {
  width: 100%;
}

.q-tab-panel {
  width: 100%;
  padding: 16px !important;
}

/* Make the container full width */
:deep(.q-page-container) {
  padding: 0 !important;
}

.search-container :deep(.q-pa-md) {
  padding: 16px !important;
  max-width: none !important;
}

/* Expanded Row Styling */
.firewall-policy-table :deep(.bg-blue-grey-1 td) {
  padding: 0 !important;
}

.firewall-policy-table :deep(.bg-blue-grey-1 .q-pa-md) {
  padding: 20px !important;
}

/* Custom styling for match indicators */
.text-positive {
  color: #27AE60 !important;
}

/* Better spacing for policy details */
.policy-detail-card {
  margin-bottom: 12px;
}

/* 4 Column Layout for Policy Details */
.policy-details-row {
  display: flex !important;
  flex-wrap: wrap !important;
  width: 100% !important;
  align-items: stretch !important;
}

.policy-detail-column {
  display: flex !important;
  flex-direction: column !important;
  min-height: 300px;
  flex: 1;
  min-width: 0;
}

.policy-detail-column .policy-detail-card,
.policy-detail-column .q-card {
  height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
}

.policy-detail-column .q-card-section:last-child {
  flex: 1 !important;
  display: flex !important;
  flex-direction: column !important;
}

/* Ensure equal height columns on large screens */
@media (min-width: 1024px) {
  .policy-details-row {
    display: flex !important;
    align-items: stretch !important;
  }
  
  .policy-detail-column {
    flex: 1 !important;
    max-width: 25% !important;
    display: flex !important;
  }
}

/* Improve chip readability */
.q-chip {
  white-space: nowrap;
  overflow: visible !important;
  text-overflow: clip !important;
  font-size: 12px !important;
  min-height: 28px !important;
  border-radius: 0px !important;
}

.q-chip :deep(.q-chip__content) {
  overflow: visible !important;
  text-overflow: clip !important;
  font-size: 10px !important;
  font-weight: 500 !important;
  line-height: 1.3 !important;
}

/* Row spacing improvements */
.firewall-policy-table :deep(tbody tr) {
  border-bottom: 1px solid #e0e0e0;
  min-height: 48px !important;
}

.firewall-policy-table :deep(tbody tr:hover) {
  background-color: #f8f9fa !important;
}

/* Disabled NAT Policy Row Styling */
.firewall-policy-table :deep(.disabled-nat-policy) {
  background-color: #ffeaea !important;
}

.firewall-policy-table :deep(.disabled-nat-policy:hover) {
  background-color: #ffcccc !important;
}

.firewall-policy-table :deep(.disabled-nat-policy td) {
  opacity: 0.7;
}

.firewall-policy-table :deep(tbody tr td) {
  min-height: 48px !important;
  padding: 10px 12px !important;
  vertical-align: middle !important;
}

/* Improve chip spacing in cells */
.firewall-policy-table .q-chip {
  margin: 2px 4px 2px 0 !important;
  display: inline-block;
}

/* Expanded view chip styling */
.expanded-chips-container {
  display: flex !important;
  flex-wrap: wrap !important;
  gap: 8px !important;
  align-items: flex-start !important;
  width: 100% !important;
}

.expanded-chips-container.q-gutter-xs {
  margin: 0 !important;
}

.expanded-chip {
  font-size: 12px !important;
  padding: 12px 16px !important;
  border-radius: 0px !important;
  min-height: 48px !important;
  height: auto !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  max-width: 100% !important;
  width: auto !important;
  display: inline-flex !important;
  align-items: flex-start !important;
  margin: 0 !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
}

.expanded-chip :deep(.q-chip__content) {
  overflow: visible !important;
  text-overflow: clip !important;
  white-space: normal !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: flex-start !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.4 !important;
  height: auto !important;
  min-height: inherit !important;
}

/* Clickable chip styling */
.clickable-chip {
  cursor: pointer !important;
  transition: all 0.2s ease !important;
}

.clickable-chip:hover {
  transform: scale(1.05) !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15) !important;
}

/* LTM clickable elements styling */
.ltm-clickable {
  cursor: pointer !important;
  color: #1976d2 !important;
  text-decoration: underline !important;
  text-decoration-color: transparent !important;
  transition: all 0.2s ease !important;
}

.ltm-clickable:hover {
  color: #0d47a1 !important;
  text-decoration-color: #0d47a1 !important;
  background-color: rgba(25, 118, 210, 0.1) !important;
  border-radius: 4px !important;
  padding: 2px 4px !important;
  margin: -2px -4px !important;
}

/* FQDN clickable elements styling */
.fqdn-clickable {
  cursor: pointer !important;
  color: #7b1fa2 !important;
  text-decoration: underline !important;
  text-decoration-color: transparent !important;
  transition: all 0.2s ease !important;
  font-weight: 600 !important;
}

.fqdn-clickable:hover {
  color: #4a148c !important;
  text-decoration-color: #4a148c !important;
  background-color: rgba(123, 31, 162, 0.1) !important;
  border-radius: 4px !important;
  padding: 2px 4px !important;
  margin: -2px -4px !important;
}

/* Force exact same color for FQDN table entries to match IP addresses */
.fqdn-table .fqdn-clickable {
  color: #7b1fa2 !important;
}
.fqdn-table .fqdn-clickable:hover {
  color: #4a148c !important;
}

/* Ensure IP addresses in FQDN table also have hover effects */
.fqdn-table .ip-clickable {
  cursor: pointer !important;
  color: #7b1fa2 !important;
  text-decoration: underline !important;
  text-decoration-color: transparent !important;
  transition: all 0.2s ease !important;
  font-weight: 600 !important;
}
.fqdn-table .ip-clickable:hover {
  color: #4a148c !important;
  text-decoration-color: #4a148c !important;
  background-color: rgba(123, 31, 162, 0.1) !important;
  border-radius: 4px !important;
  padding: 2px 4px !important;
  margin: -2px -4px !important;
}

/* Clickable cell container styling */
.clickable-cell-container {
  display: inline-flex !important;
  align-items: center !important;
  gap: 8px !important;
  position: relative !important;
}

/* Hover link icon styling */
.hover-link-icon {
  opacity: 0.3 !important;
  transition: opacity 0.2s ease !important;
  color: #666 !important;
  cursor: pointer !important;
}

.clickable-cell-container:hover .hover-link-icon {
  opacity: 1 !important;
}

/* FQDN specific icon color */
.fqdn-clickable + .hover-link-icon {
  color: #4a148c !important;
}

/* IP specific icon color */
.ip-clickable + .hover-link-icon {
  color: #4a148c !important;
}

/* Address card styling for firewall policies */
.address-card {
  width: 100%;
}

.address-header {
  margin-bottom: 8px;
}

.address-ips {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ip-item {
  display: flex;
  align-items: center;
  font-size: 13px;
  line-height: 1.4;
}

.ip-bullet {
  margin-right: 8px;
  color: #666;
  font-weight: bold;
}

.ip-address {
  font-family: 'Roboto Mono', monospace;
  font-weight: 500;
}

/* Clickable IP styling */
.clickable-ip {
  cursor: pointer !important;
  color: #1976d2 !important;
  text-decoration: underline !important;
  text-decoration-color: transparent !important;
  transition: all 0.2s ease !important;
  border-radius: 3px !important;
  padding: 1px 3px !important;
  margin: -1px -3px !important;
}

.clickable-ip:hover {
  color: #0d47a1 !important;
  text-decoration-color: #0d47a1 !important;
  background-color: rgba(25, 118, 210, 0.1) !important;
}

/* Clickable group styling */
.clickable-group {
  cursor: pointer !important;
  transition: all 0.2s ease !important;
}

.clickable-group:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
}

/* IP highlighting for matched search results */
.ip-highlight-match {
  background-color: #FFEB3B !important; /* Bright yellow background */
  font-weight: 600 !important;
  color: #333 !important; /* Dark text for better contrast on yellow */
  padding: 2px 4px !important;
  margin: -2px -4px !important;
  border-radius: 4px !important;
  box-shadow: 0 1px 3px rgba(255, 235, 59, 0.5) !important;
}

.ip-highlight-match:hover {
  background-color: #FFC107 !important; /* Slightly darker yellow on hover */
  color: #212121 !important;
  text-decoration-color: #212121 !important;
}

.chip-content {
  display: flex !important;
  flex-direction: column !important;
  align-items: flex-start !important;
  gap: 2px !important;
  width: 100% !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
}

.chip-name {
  font-weight: 600 !important;
  white-space: normal !important;
  font-size: 12px !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.3 !important;
  max-width: 100% !important;
}

.chip-ip {
  font-size: 12px !important;
  opacity: 0.95 !important;
  white-space: normal !important;
  font-weight: 400 !important;
  color: rgba(255,255,255,0.9) !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
  line-height: 1.2 !important;
  max-width: 100% !important;
}

/* IP item styling with bullet points */
.ip-item {
  font-size: 11px !important;
  line-height: 1.3 !important;
  margin-bottom: 2px !important;
  color: rgba(255,255,255,0.95) !important;
  word-wrap: break-word !important;
  word-break: break-word !important;
}

/* Responsive adjustments */
@media (max-width: 1600px) {
  .firewall-policy-table {
    min-width: 1100px;
  }
}

@media (max-width: 1400px) {
  .firewall-policy-table {
    min-width: 1000px;
  }
  
  .address-chip {
    font-size: 10px !important;
    max-width: 120px;
    padding: 4px 8px !important;
    min-height: 22px !important;
  }
  
  .service-chip {
    font-size: 10px !important;
    max-width: 70px;
    padding: 4px 8px !important;
    min-height: 22px !important;
  }
}

@media (max-width: 1200px) {
  .firewall-policy-table {
    min-width: 900px;
  }
  
  .firewall-policy-table :deep(td) {
    padding: 6px 4px !important;
    font-size: 12px !important;
  }
  
  .firewall-policy-table :deep(th) {
    padding: 6px 4px !important;
    font-size: 14px !important;
  }
  
  .address-chip {
    font-size: 10px !important;
    max-width: 100px;
    padding: 4px 8px !important;
    min-height: 22px !important;
  }
  
  .service-chip {
    font-size: 10px !important;
    max-width: 60px;
    padding: 4px 8px !important;
    min-height: 22px !important;
  }
  
  /* IP address clickable elements styling */
  .ip-clickable {
    cursor: pointer !important;
    color: #7b1fa2 !important;
    text-decoration: underline !important;
    text-decoration-color: transparent !important;
    transition: all 0.2s ease !important;
    font-weight: 600 !important;
  }
  .ip-clickable:hover {
    color: #4a148c !important;
    text-decoration-color: #4a148c !important;
    background-color: rgba(123, 31, 162, 0.1) !important;
    border-radius: 4px !important;
    padding: 2px 4px !important;
    margin: -2px -4px !important;
  }

  
  .environment-chip,
  .zone-column .q-chip {
    font-size: 10px !important;
    padding: 4px 8px !important;
    min-height: 22px !important;
    max-width: 60px;
  }
  
  .policy-name-text {
    font-size: 10px !important;
    -webkit-line-clamp: 2;
  }
}

@media (max-width: 1000px) {
  .firewall-policy-table {
    min-width: 800px;
  }
  
  .firewall-policy-table :deep(td) {
    padding: 4px 3px !important;
    font-size: 11px !important;
  }
  
  .firewall-policy-table :deep(th) {
    padding: 4px 3px !important;
    font-size: 14px !important;
  }
  
  .address-chip, .service-chip {
    font-size: 10px !important;
    padding: 4px 8px !important;
    min-height: 22px !important;
  }
  
  .environment-chip,
  .zone-column .q-chip {
    font-size: 10px !important;
    padding: 4px 8px !important;
    min-height: 22px !important;
    max-width: 50px;
  }
  
  .policy-name-text {
    font-size: 9px !important;
    -webkit-line-clamp: 2;
  }
}

/* Improved Main Search Input Clickability */
.main-search-input {
  position: relative;
}

.main-search-input :deep(.q-field__control) {
  cursor: text !important;
  min-height: 56px !important;
  padding: 8px 16px !important;
}

.main-search-input :deep(.q-field__control-container) {
  cursor: text !important;
  padding: 8px 0 !important;
}

.main-search-input :deep(.q-field__native) {
  cursor: text !important;
  padding: 12px 8px !important;
  font-size: 16px !important;
  z-index: 2 !important;
  position: relative !important;
}

.main-search-input :deep(.q-field__label) {
  cursor: text !important;
  z-index: 1 !important;
  transform-origin: left top !important;
}

/* Fix label positioning when field has value */
.main-search-input :deep(.q-field--float .q-field__label) {
  transform: translateY(-120%) scale(0.75) !important;
  top: 24px !important;
  left: 12px !important;
  color: #1976d2 !important;
}

.main-search-input :deep(.q-field--focused .q-field__label) {
  transform: translateY(-120%) scale(0.75) !important;
  top: 24px !important;
  left: 12px !important;
  color: #1976d2 !important;
}

/* When field has content, ensure label moves up */
.main-search-input :deep(.q-field__native:not(:placeholder-shown)) ~ .q-field__label,
.main-search-input :deep(.q-field__native:focus) ~ .q-field__label {
  transform: translateY(-120%) scale(0.75) !important;
  top: 24px !important;
  left: 12px !important;
  color: #1976d2 !important;
}

/* Ensure proper text display over label */
.main-search-input :deep(.q-field__native:not(:placeholder-shown)) {
  color: #212121 !important;
  font-weight: 500 !important;
}

/* Force label to always be above when there's text */
.main-search-input :deep(.q-field__native[value]:not([value=""]) ~ .q-field__label) {
  transform: translateY(-120%) scale(0.75) !important;
  top: 24px !important;
  left: 12px !important;
  color: #1976d2 !important;
}

/* Make the entire input area clickable */
.main-search-input :deep(.q-field__control):hover {
  background-color: rgba(25, 118, 210, 0.02) !important;
}

/* Larger click zone for mobile */
@media (max-width: 768px) {
  .main-search-input :deep(.q-field__control) {
    min-height: 60px !important;
    padding: 12px 16px !important;
  }
  
  .main-search-input :deep(.q-field__native) {
    padding: 16px 8px !important;
    font-size: 18px !important;
  }
}

/* Infrastructure Toggle Styles */
.infra-toggle {
  margin: 4px 8px;
}

.infra-toggle :deep(.q-toggle__inner) {
  transition: all 0.3s ease;
}

.infra-toggle :deep(.q-toggle__track) {
  opacity: 0.8;
}

.infra-toggle :deep(.q-toggle__inner--truthy) .q-toggle__track {
  opacity: 1;
}
</style>