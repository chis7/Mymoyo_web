<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  enqueueLocationWrite,
  flushLocationWriteQueue,
  getLocationWriteQueue,
  listDistricts,
  listFacilities,
  listProvinces,
  saveDistrict,
  saveFacility,
  saveProvince
} from '@/api/client'

const route = useRoute()
const router = useRouter()

const tabs = [
  { key: 'provinces', label: 'Provinces' },
  { key: 'districts', label: 'Districts' },
  { key: 'facilities', label: 'Facilities' }
]

const activeTab = ref(route.query.tab || 'provinces')
const query = ref('')
const mapped = ref(route.query.mapped || '')
const sortKey = ref('name')
const sortDir = ref('asc')
const page = ref(1)
const pageSize = ref(10)
const rows = ref([])
const count = ref(0)
const provinces = ref([])
const districts = ref([])
const loading = ref(false)
const error = ref('')
const syncMessage = ref('')
const pendingWrites = ref([])
const modalOpen = ref(false)
const editing = ref(null)
const form = ref({})
const saving = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(count.value / pageSize.value)))
const startIndex = computed(() => (count.value ? (page.value - 1) * pageSize.value + 1 : 0))
const endIndex = computed(() => Math.min(page.value * pageSize.value, count.value))
const modalTitle = computed(() => `${editing.value ? 'Edit' : 'Add'} ${activeTab.value.slice(0, -1)}`)
const pendingForTab = computed(() => pendingWrites.value.filter((change) => change.resource === activeTab.value))
const pendingCount = computed(() => pendingWrites.value.length)

const columns = computed(() => {
  if (activeTab.value === 'provinces') return ['name', 'facility_count']
  if (activeTab.value === 'districts') return ['name', 'province_name']
  return ['name', 'code', 'level', 'district_name', 'province_name', 'coordinates']
})

const displayRows = computed(() => [
  ...pendingForTab.value.map(pendingRow),
  ...rows.value
])

function normalizeList(data) {
  rows.value = data.results || data
  count.value = data.count || rows.value.length
}

function refreshQueue() {
  pendingWrites.value = getLocationWriteQueue()
}

function provinceName(id) {
  return provinces.value.find((province) => String(province.id) === String(id))?.name || '-'
}

function districtLabel(id) {
  const district = districts.value.find((item) => String(item.id) === String(id))
  if (!district) return { districtName: '-', provinceName: '-' }
  return {
    districtName: district.name,
    provinceName: district.province_name || provinceName(district.province)
  }
}

function pendingRow(change) {
  const payload = change.payload || {}
  const district = districtLabel(payload.district)
  return {
    id: `queued-${change.id}`,
    __pending: true,
    name: payload.name,
    code: payload.code,
    level: payload.level,
    facility_count: 'Pending sync',
    province: payload.province,
    province_name: payload.province ? provinceName(payload.province) : district.provinceName,
    district: payload.district,
    district_name: district.districtName,
    latitude: payload.latitude,
    longitude: payload.longitude
  }
}

function params() {
  const orderingMap = {
    province_name: 'province__name',
    district_name: 'district__name',
    coordinates: 'latitude'
  }
  const apiSortKey = orderingMap[sortKey.value] || sortKey.value
  const ordering = `${sortDir.value === 'desc' ? '-' : ''}${apiSortKey}`
  return {
    q: query.value || undefined,
    mapped: activeTab.value === 'facilities' ? mapped.value || undefined : undefined,
    page: page.value,
    page_size: pageSize.value,
    ordering
  }
}

async function loadReferenceData() {
  try {
    const [provinceData, districtData] = await Promise.all([listProvinces(), listDistricts()])
    provinces.value = provinceData.results || provinceData
    districts.value = districtData.results || districtData
  } catch {
    syncMessage.value = pendingWrites.value.length
      ? 'Reference data is unavailable, but offline changes are still saved locally.'
      : syncMessage.value
  }
}

async function loadRows() {
  loading.value = true
  error.value = ''
  try {
    if (activeTab.value === 'provinces') normalizeList(await listProvinces(params()))
    if (activeTab.value === 'districts') normalizeList(await listDistricts(params()))
    if (activeTab.value === 'facilities') normalizeList(await listFacilities(params()))
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Cached location data will appear after an online visit.'
  } finally {
    loading.value = false
  }
}

function shouldQueueSave(errorObject) {
  return !errorObject.response || errorObject.response.status >= 500
}

async function syncPendingWrites() {
  refreshQueue()
  if (!pendingWrites.value.length) return

  syncMessage.value = 'Syncing saved offline changes...'
  try {
    const result = await flushLocationWriteQueue()
    refreshQueue()
    if (result.synced.length) {
      syncMessage.value = `${result.synced.length} offline change${result.synced.length === 1 ? '' : 's'} synced.`
      await Promise.all([loadReferenceData(), loadRows()])
    } else if (pendingWrites.value.length) {
      syncMessage.value = 'Offline changes are still waiting to sync.'
    }
  } catch {
    refreshQueue()
    syncMessage.value = 'Offline changes are still waiting to sync.'
  }
}

function setTab(tab) {
  activeTab.value = tab
  page.value = 1
  sortKey.value = 'name'
  router.replace({ query: { tab, mapped: tab === 'facilities' ? mapped.value || undefined : undefined } })
}

function toggleSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
  page.value = 1
}

function openCreate() {
  editing.value = null
  form.value = activeTab.value === 'facilities' ? { district: districts.value[0]?.id || '' } : {}
  if (activeTab.value === 'districts') form.value = { province: provinces.value[0]?.id || '' }
  saving.value = false
  modalOpen.value = true
}

function openEdit(row) {
  editing.value = row
  form.value = { ...row }
  saving.value = false
  modalOpen.value = true
}

async function submitForm() {
  if (saving.value) return
  saving.value = true
  const payload = { ...form.value }
  try {
    if (activeTab.value === 'provinces') await saveProvince({ name: payload.name }, editing.value?.id)
    if (activeTab.value === 'districts') await saveDistrict({ name: payload.name, province: payload.province }, editing.value?.id)
    if (activeTab.value === 'facilities') {
      await saveFacility({
        name: payload.name,
        district: payload.district,
        code: payload.code || '',
        level: payload.level || '',
        latitude: payload.latitude || null,
        longitude: payload.longitude || null
      }, editing.value?.id)
    }
    modalOpen.value = false
    await Promise.all([loadReferenceData(), loadRows()])
  } catch (err) {
    if (!shouldQueueSave(err)) {
      error.value = err.message
      return
    }

    let queuedPayload = {}
    if (activeTab.value === 'provinces') queuedPayload = { name: payload.name }
    if (activeTab.value === 'districts') queuedPayload = { name: payload.name, province: payload.province }
    if (activeTab.value === 'facilities') {
      queuedPayload = {
        name: payload.name,
        district: payload.district,
        code: payload.code || '',
        level: payload.level || '',
        latitude: payload.latitude || null,
        longitude: payload.longitude || null
      }
    }

    enqueueLocationWrite({
      resource: activeTab.value,
      recordId: editing.value?.__pending ? null : editing.value?.id || null,
      payload: queuedPayload
    })
    refreshQueue()
    modalOpen.value = false
    error.value = ''
    syncMessage.value = 'Saved locally. This change will sync when the database is available.'
  } finally {
    saving.value = false
  }
}

watch([activeTab, query, mapped, sortKey, sortDir, page, pageSize], loadRows)
onMounted(async () => {
  refreshQueue()
  window.addEventListener('online', syncPendingWrites)
  window.addEventListener('mythanzi:location-queue-changed', refreshQueue)
  syncPendingWrites()
  await loadReferenceData()
  await loadRows()
})

onBeforeUnmount(() => {
  window.removeEventListener('online', syncPendingWrites)
  window.removeEventListener('mythanzi:location-queue-changed', refreshQueue)
})
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>Locations</h2>
        <p class="muted">Manage provinces, districts, facilities, and unmapped coordinates inside the PWA.</p>
      </div>
      <button type="button" @click="openCreate">Add</button>
    </div>

    <div v-if="pendingCount" class="sync-banner">
      <span>{{ pendingCount }} location change{{ pendingCount === 1 ? '' : 's' }} waiting to sync.</span>
      <button type="button" class="text-button" @click="syncPendingWrites">Retry sync</button>
    </div>

    <div class="segmented">
      <button v-for="tab in tabs" :key="tab.key" type="button" :class="{ active: activeTab === tab.key }" @click="setTab(tab.key)">
        {{ tab.label }}
      </button>
    </div>

    <div class="toolbar">
      <input v-model="query" type="search" placeholder="Search locations">
      <label v-if="activeTab === 'facilities'" class="check-row">
        <input v-model="mapped" type="checkbox" true-value="unmapped" false-value="">
        Unmapped only
      </label>
      <select v-model.number="pageSize">
        <option :value="10">10 rows</option>
        <option :value="25">25 rows</option>
        <option :value="50">50 rows</option>
      </select>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="syncMessage" class="muted">{{ syncMessage }}</p>
    <p v-if="loading" class="muted">Loading locations...</p>

    <div class="data-table">
      <table>
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">
              <button type="button" class="text-button" @click="toggleSort(column)">{{ column.replace('_', ' ') }}</button>
            </th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.id" :class="{ pending: row.__pending }">
            <td v-for="column in columns" :key="column">
              <template v-if="column === 'coordinates'">
                {{ row.latitude && row.longitude ? `${row.latitude}, ${row.longitude}` : '-' }}
              </template>
              <template v-else>{{ row[column] || '-' }}</template>
            </td>
            <td>
              <span v-if="row.__pending" class="muted">Queued</span>
              <div v-else class="action-buttons">
                <button
                  type="button"
                  class="btn-icon btn-edit"
                  :title="activeTab === 'facilities' && (!row.latitude || !row.longitude) ? 'Add coordinates' : 'Edit'"
                  :aria-label="activeTab === 'facilities' && (!row.latitude || !row.longitude) ? 'Add coordinates' : 'Edit'"
                  @click="openEdit(row)"
                >
                  <span class="material-symbols-outlined" aria-hidden="true">
                    {{ activeTab === 'facilities' && (!row.latitude || !row.longitude) ? 'add_location_alt' : 'edit' }}
                  </span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pager">
      <span>Showing {{ startIndex }}-{{ endIndex }} of {{ count }}</span>
      <div>
        <button type="button" :disabled="page <= 1" @click="page -= 1">Prev</button>
        <span>Page {{ page }} of {{ totalPages }}</span>
        <button type="button" :disabled="page >= totalPages" @click="page += 1">Next</button>
      </div>
    </div>

    <div v-if="modalOpen" class="modal-backdrop" @click.self="!saving && (modalOpen = false)">
      <form class="modal-card" @submit.prevent="submitForm">
        <h3>{{ modalTitle }}</h3>
        <label>Name <input v-model="form.name" required></label>
        <label v-if="activeTab === 'districts'">Province
          <select v-model="form.province" required>
            <option v-for="province in provinces" :key="province.id" :value="province.id">{{ province.name }}</option>
          </select>
        </label>
        <template v-if="activeTab === 'facilities'">
          <label>District
            <select v-model="form.district" required>
              <option v-for="district in districts" :key="district.id" :value="district.id">{{ district.name }} - {{ district.province_name }}</option>
            </select>
          </label>
          <label>Code <input v-model="form.code"></label>
          <label>Level <input v-model="form.level"></label>
          <label>Latitude <input v-model="form.latitude" type="number" step="0.0000001"></label>
          <label>Longitude <input v-model="form.longitude" type="number" step="0.0000001"></label>
        </template>
        <div class="modal-actions">
          <button type="button" class="secondary" :disabled="saving" @click="modalOpen = false">Cancel</button>
          <button type="submit" :disabled="saving">{{ saving ? 'Saving...' : 'Save' }}</button>
        </div>
      </form>
    </div>
  </section>
</template>
