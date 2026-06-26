<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { listFacilities } from '@/api/client'

const facilities = ref([])
const selectedFacility = ref(null)
const query = ref('')
const error = ref('')
const loading = ref(true)

const mappedFacilities = computed(() => facilities.value.filter((facility) => hasCoordinates(facility)))
const unmappedCount = computed(() => facilities.value.length - mappedFacilities.value.length)

const selectedMapUrl = computed(() => {
  if (!hasCoordinates(selectedFacility.value)) return ''
  const latitude = Number(selectedFacility.value.latitude)
  const longitude = Number(selectedFacility.value.longitude)
  const offset = 0.018
  const bbox = [
    longitude - offset,
    latitude - offset,
    longitude + offset,
    latitude + offset
  ].join(',')
  return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${latitude},${longitude}`
})

const directionsUrl = computed(() => {
  if (!selectedFacility.value) return ''
  if (hasCoordinates(selectedFacility.value)) {
    return `https://www.google.com/maps/dir/?api=1&destination=${selectedFacility.value.latitude},${selectedFacility.value.longitude}&travelmode=driving`
  }
  const queryText = [
    selectedFacility.value.name,
    selectedFacility.value.district_name,
    selectedFacility.value.province_name
  ].filter(Boolean).join(' ')
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(queryText)}`
})

function hasCoordinates(facility) {
  return Boolean(facility?.latitude && facility?.longitude)
}

function selectFacility(facility) {
  selectedFacility.value = facility
}

async function loadFacilities() {
  loading.value = true
  try {
    error.value = ''
    const data = await listFacilities(query.value ? { q: query.value } : {})
    facilities.value = data.results || data
    selectedFacility.value = mappedFacilities.value[0] || facilities.value[0] || null
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Facility search is available after cached data is loaded.'
  } finally {
    loading.value = false
  }
}

watch(query, loadFacilities)
onMounted(loadFacilities)
</script>

<template>
  <section class="workspace clinic-finder">
    <div class="section-heading compact">
      <div>
        <h2>Find a Clinic</h2>
        <p class="muted">Search facilities, view mapped clinics, and open driving directions.</p>
      </div>
      <input v-model="query" type="search" placeholder="Search facilities, districts, or services">
    </div>

    <div class="clinic-map-layout">
      <aside class="clinic-list-panel">
        <div class="clinic-list-summary">
          <strong>{{ mappedFacilities.length }}</strong>
          <span>mapped clinics</span>
          <small v-if="unmappedCount">{{ unmappedCount }} without coordinates</small>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <p v-else-if="loading" class="muted">Loading facilities...</p>
        <div v-else class="clinic-list">
          <button
            v-for="facility in facilities"
            :key="facility.id"
            type="button"
            class="clinic-list-item"
            :class="{ active: selectedFacility?.id === facility.id }"
            @click="selectFacility(facility)"
          >
            <span class="material-symbols-outlined" aria-hidden="true">
              {{ hasCoordinates(facility) ? 'location_on' : 'location_off' }}
            </span>
            <span>
              <strong>{{ facility.name }}</strong>
              <small>{{ facility.district_name }}, {{ facility.province_name }}</small>
            </span>
          </button>
          <p v-if="!facilities.length" class="empty-state">No facilities found.</p>
        </div>
      </aside>

      <main class="clinic-map-panel">
        <div v-if="selectedFacility" class="clinic-map-header">
          <div>
            <p class="eyebrow">{{ selectedFacility.level || 'Facility' }}</p>
            <h3>{{ selectedFacility.name }}</h3>
            <p class="muted">{{ selectedFacility.district_name }}, {{ selectedFacility.province_name }}</p>
          </div>
          <a class="primary-action" :href="directionsUrl" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined" aria-hidden="true">directions</span>
            Directions
          </a>
        </div>

        <div v-if="selectedMapUrl" class="clinic-map-frame">
          <iframe
            title="Selected clinic map"
            :src="selectedMapUrl"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"
          ></iframe>
        </div>
        <div v-else class="clinic-map-empty">
          <span class="material-symbols-outlined" aria-hidden="true">add_location_alt</span>
          <h3>{{ selectedFacility ? 'No map coordinates yet' : 'Select a facility' }}</h3>
          <p class="muted">Facilities with latitude and longitude will appear on the map.</p>
        </div>

        <div v-if="selectedFacility" class="clinic-detail-strip">
          <span>{{ selectedFacility.facility_type || 'Clinic' }}</span>
          <span>{{ selectedFacility.service_names?.length ? selectedFacility.service_names.join(', ') : 'Services not mapped' }}</span>
          <span v-if="hasCoordinates(selectedFacility)">{{ selectedFacility.latitude }}, {{ selectedFacility.longitude }}</span>
        </div>
      </main>
    </div>
  </section>
</template>
