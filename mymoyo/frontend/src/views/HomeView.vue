<script setup>
import { onMounted, ref } from 'vue'

import { getBootstrap } from '@/api/client'
import { loadOfflineQueue } from '@/api/offlineQueue'

const loading = ref(true)
const bootstrap = ref(null)
const error = ref('')
const queuedItems = ref(loadOfflineQueue())

onMounted(async () => {
  try {
    bootstrap.value = await getBootstrap()
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Showing the app shell while offline. Cached API data will appear after your first online visit.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page-grid">
    <article class="panel hero-panel">
      <p class="eyebrow">Offline-ready portal</p>
      <h2>Care tools that keep working when the network is unreliable.</h2>
      <p>
        This Vue PWA uses the Django REST API for live data and caches the app shell for offline access.
      </p>
    </article>

    <article class="panel">
      <h3>Appointments</h3>
      <p v-if="loading">Loading summary...</p>
      <p v-else-if="error" class="muted">{{ error }}</p>
      <div v-else class="metric-grid">
        <span><strong>{{ bootstrap.appointment_summary.upcoming }}</strong> upcoming</span>
        <span><strong>{{ bootstrap.appointment_summary.completed }}</strong> completed</span>
        <span><strong>{{ bootstrap.appointment_summary.missed }}</strong> missed</span>
      </div>
    </article>

    <article class="panel">
      <h3>Offline queue</h3>
      <p class="muted">{{ queuedItems.length }} item{{ queuedItems.length === 1 ? '' : 's' }} waiting to sync.</p>
    </article>
  </section>
</template>
