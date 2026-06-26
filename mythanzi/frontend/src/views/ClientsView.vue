<script setup>
import { computed, onMounted, ref } from 'vue'

import { listClients } from '@/api/client'

const clients = ref([])
const query = ref('')
const error = ref('')
const loading = ref(true)

const activeClients = computed(() => clients.value.length)
const totalJourneyEvents = computed(() => clients.value.reduce((total, client) => total + (client.journey_count || 0), 0))
const totalOpenTasks = computed(() => clients.value.reduce((total, client) => total + (client.follow_up_count || 0), 0))

async function refreshClients() {
  loading.value = true
  error.value = ''
  try {
    const data = await listClients(query.value ? { q: query.value } : {})
    clients.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Clients will appear after cached data is available.'
  } finally {
    loading.value = false
  }
}

onMounted(refreshClients)
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>Client Management</h2>
        <p class="muted">A switchboard for journey events, referrals, follow-up tasks, appointments, locator notes, and consent.</p>
      </div>
      <a class="secondary-link" href="/users/clients/bulk-upload/">
        <span class="material-symbols-outlined" aria-hidden="true">upload_file</span>
        Bulk Upload
      </a>
    </div>

    <div class="card-grid">
      <article class="metric-card">
        <span>Active Clients</span>
        <strong>{{ activeClients }}</strong>
        <small>visible to your account</small>
      </article>
      <article class="metric-card">
        <span>Journey Events</span>
        <strong>{{ totalJourneyEvents }}</strong>
        <small>recorded touchpoints</small>
      </article>
      <article class="metric-card">
        <span>Follow-Up Tasks</span>
        <strong>{{ totalOpenTasks }}</strong>
        <small>active or historical tasks</small>
      </article>
    </div>

    <div class="toolbar">
      <input v-model="query" placeholder="Search by client name, reference, or phone" @keyup.enter="refreshClients">
      <button type="button" class="secondary" @click="refreshClients">
        <span class="material-symbols-outlined" aria-hidden="true">search</span>
        Search
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Loading clients...</p>
    <div v-else class="data-table">
      <table>
        <thead>
          <tr>
            <th>Reference</th>
            <th>Client</th>
            <th>Population</th>
            <th>Facility</th>
            <th>Journey</th>
            <th>Referrals</th>
            <th>Tasks</th>
            <th>Appointments</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="client in clients" :key="client.id">
            <td>{{ client.reference_number || '-' }}</td>
            <td>
              <strong>{{ client.display_name }}</strong>
              <small class="table-subtext">{{ client.phone || client.username }}</small>
            </td>
            <td>{{ client.population_group || '-' }}</td>
            <td>{{ client.facility_name || '-' }}</td>
            <td>{{ client.journey_count }}</td>
            <td>{{ client.referral_count }}</td>
            <td>{{ client.follow_up_count }}</td>
            <td>{{ client.appointment_count }}</td>
            <td>
              <RouterLink class="btn-icon btn-view" :to="`/clients/${client.id}`" title="Open switchboard">
                <span class="material-symbols-outlined" aria-hidden="true">open_in_new</span>
              </RouterLink>
            </td>
          </tr>
          <tr v-if="!clients.length">
            <td colspan="9" class="empty-state">No clients found.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
