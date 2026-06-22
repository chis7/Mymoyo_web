<script setup>
import { onMounted, ref } from 'vue'

import { listAppointments } from '@/api/client'

const appointments = ref([])
const error = ref('')

onMounted(async () => {
  try {
    const data = await listAppointments()
    appointments.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Appointments will appear after cached data is available.'
  }
})
</script>

<template>
  <section class="panel">
    <h2>Appointments</h2>
    <p v-if="error" class="muted">{{ error }}</p>
    <div v-else class="table-list">
      <article v-for="appointment in appointments" :key="appointment.id" class="row-card">
        <strong>{{ appointment.visit_purpose_display }}</strong>
        <span>{{ appointment.appointment_date }} at {{ appointment.appointment_time }}</span>
        <span>{{ appointment.facility_name }}</span>
      </article>
    </div>
  </section>
</template>
