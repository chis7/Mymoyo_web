<script setup>
import { computed, onMounted, ref } from 'vue'

import { createAppointment, listAppointments, listFacilities } from '@/api/client'

const appointments = ref([])
const facilities = ref([])
const error = ref('')
const saveError = ref('')
const loading = ref(true)
const saving = ref(false)
const modalOpen = ref(false)
const form = ref({
  beneficiary_reference: '',
  visit_purpose: 'clinical_review',
  appointment_date: '',
  appointment_time: '',
  facility: '',
  notes: ''
})

const visitPurposes = [
  ['clinical_review', 'Clinical Review (Checkup)'],
  ['lab_collection', 'Lab Collection'],
  ['medication_refill', 'Medication Refill'],
  ['follow_up', 'Follow-up Visit']
]

const upcomingCount = computed(() => appointments.value.filter((item) => item.status === 'upcoming').length)
const completedCount = computed(() => appointments.value.filter((item) => item.status === 'completed').length)
const missedCount = computed(() => appointments.value.filter((item) => item.status === 'missed').length)

function resetForm() {
  form.value = {
    beneficiary_reference: '',
    visit_purpose: 'clinical_review',
    appointment_date: '',
    appointment_time: '',
    facility: '',
    notes: ''
  }
  saveError.value = ''
}

async function refreshAppointments() {
  loading.value = true
  error.value = ''
  try {
    const data = await listAppointments()
    appointments.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Appointments will appear after cached data is available.'
  } finally {
    loading.value = false
  }
}

async function loadFacilities() {
  try {
    const data = await listFacilities()
    facilities.value = data.results || data
  } catch {
    facilities.value = []
  }
}

async function saveAppointment() {
  saving.value = true
  saveError.value = ''
  try {
    await createAppointment({
      ...form.value,
      facility: Number(form.value.facility)
    })
    modalOpen.value = false
    resetForm()
    await refreshAppointments()
  } catch (err) {
    saveError.value = err.message
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([refreshAppointments(), loadFacilities()])
})
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>Appointments</h2>
        <p class="muted">Manage upcoming clinical visits, refills, and lab collections.</p>
      </div>
      <button type="button" @click="modalOpen = true">
        <span class="material-symbols-outlined" aria-hidden="true">add</span>
        New Appointment
      </button>
    </div>

    <div class="card-grid">
      <article class="metric-card">
        <span>Upcoming</span>
        <strong>{{ upcomingCount }}</strong>
        <small>scheduled visits</small>
      </article>
      <article class="metric-card">
        <span>Completed</span>
        <strong>{{ completedCount }}</strong>
        <small>closed visits</small>
      </article>
      <article class="metric-card">
        <span>Missed</span>
        <strong>{{ missedCount }}</strong>
        <small>requires follow-up</small>
      </article>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Loading appointments...</p>
    <div v-else class="data-table">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Time</th>
            <th>Client</th>
            <th>Purpose</th>
            <th>Facility</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="appointment in appointments" :key="appointment.id">
            <td>{{ appointment.appointment_date }}</td>
            <td>{{ appointment.appointment_time }}</td>
            <td>{{ appointment.beneficiary_detail?.display_name || appointment.beneficiary_reference || '-' }}</td>
            <td>{{ appointment.visit_purpose_display }}</td>
            <td>{{ appointment.facility_name }}</td>
            <td>{{ appointment.status_display }}</td>
          </tr>
          <tr v-if="!appointments.length">
            <td colspan="6" class="empty-state">No appointments yet.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="modalOpen" class="modal-backdrop" @click.self="!saving && (modalOpen = false)">
      <form class="modal-card wide" @submit.prevent="saveAppointment">
        <h3>Create Appointment</h3>
        <p v-if="saveError" class="error">{{ saveError }}</p>
        <div class="form-grid">
          <label>
            Client reference
            <input v-model="form.beneficiary_reference" placeholder="MM-000001" required>
          </label>
          <label>
            Visit purpose
            <select v-model="form.visit_purpose" required>
              <option v-for="[value, label] in visitPurposes" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Date
            <input v-model="form.appointment_date" type="date" required>
          </label>
          <label>
            Time
            <input v-model="form.appointment_time" type="time" required>
          </label>
          <label class="full-width">
            Facility
            <select v-model="form.facility" required>
              <option value="">Select facility</option>
              <option v-for="facility in facilities" :key="facility.id" :value="facility.id">
                {{ facility.name }} - {{ facility.district_name }}, {{ facility.province_name }}
              </option>
            </select>
          </label>
          <label class="full-width">
            Notes
            <input v-model="form.notes" placeholder="Optional notes">
          </label>
        </div>
        <div class="modal-actions">
          <button class="secondary" type="button" :disabled="saving" @click="modalOpen = false">Cancel</button>
          <button type="submit" :disabled="saving">{{ saving ? 'Saving...' : 'Book Appointment' }}</button>
        </div>
      </form>
    </div>
  </section>
</template>
