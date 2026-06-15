<script setup>
import { onMounted, ref, watch } from 'vue'

import { listFacilities } from '@/api/client'

const facilities = ref([])
const query = ref('')
const error = ref('')

async function loadFacilities() {
  try {
    error.value = ''
    const data = await listFacilities(query.value ? { q: query.value } : {})
    facilities.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Facility search is available after cached data is loaded.'
  }
}

watch(query, loadFacilities)
onMounted(loadFacilities)
</script>

<template>
  <section class="panel">
    <div class="section-heading">
      <div>
        <h2>Find a Clinic</h2>
        <p class="muted">Searches the DRF facilities endpoint.</p>
      </div>
      <input v-model="query" type="search" placeholder="Search facilities">
    </div>
    <p v-if="error" class="muted">{{ error }}</p>
    <div v-else class="table-list">
      <article v-for="facility in facilities" :key="facility.id" class="row-card">
        <strong>{{ facility.name }}</strong>
        <span>{{ facility.district_name }}, {{ facility.province_name }}</span>
        <span>{{ facility.level || 'Facility' }}</span>
      </article>
    </div>
  </section>
</template>
