<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  createClientAppointment,
  createClientFollowUpTask,
  createClientJourneyEvent,
  createClientReferral,
  deleteAppointment,
  deleteClientFollowUpTask,
  deleteClientJourneyEvent,
  deleteClientReferral,
  getClient,
  listFacilities,
  updateAppointment,
  updateClientFollowUpTask,
  updateClientJourneyEvent,
  updateClientReferral
} from '@/api/client'

const route = useRoute()
const client = ref(null)
const facilities = ref([])
const activeTab = ref('journey')
const modalType = ref('')
const editingRecord = ref(null)
const error = ref('')
const saveError = ref('')
const loading = ref(true)
const saving = ref(false)

const stageChoices = [
  ['contact', 'Contact'],
  ['risk_assessment', 'Risk assessment'],
  ['referral', 'Referral'],
  ['hivst', 'HIVST'],
  ['prep_len_initiation', 'PrEP/LEN initiation'],
  ['follow_up', 'Follow-up'],
  ['continuation', 'Continuation']
]
const outcomeChoices = [
  ['pending', 'Pending'],
  ['completed', 'Completed'],
  ['missed', 'Missed'],
  ['referred', 'Referred'],
  ['continued', 'Continued'],
  ['stopped', 'Stopped']
]
const referralStatusChoices = [
  ['generated', 'Generated'],
  ['sent', 'Sent'],
  ['received', 'Received'],
  ['attended', 'Attended'],
  ['initiated', 'Initiated'],
  ['not_attended', 'Not attended'],
  ['closed', 'Closed']
]
const initiationOutcomeChoices = [
  ['pending', 'Pending'],
  ['len_prep_initiated', 'LEN/PrEP initiated'],
  ['hivst_received', 'HIVST received'],
  ['referred_elsewhere', 'Referred elsewhere'],
  ['declined', 'Declined']
]
const taskReasonChoices = [
  ['missed_appointment', 'Missed appointment'],
  ['tracing', 'Tracing'],
  ['re_engagement', 'Re-engagement'],
  ['referral_confirmation', 'Referral confirmation'],
  ['other', 'Other']
]
const taskStatusChoices = [
  ['open', 'Open'],
  ['in_progress', 'In progress'],
  ['completed', 'Completed'],
  ['cancelled', 'Cancelled']
]
const priorityChoices = [
  ['low', 'Low'],
  ['normal', 'Normal'],
  ['high', 'High'],
  ['urgent', 'Urgent']
]
const visitPurposes = [
  ['clinical_review', 'Clinical Review (Checkup)'],
  ['lab_collection', 'Lab Collection'],
  ['medication_refill', 'Medication Refill'],
  ['follow_up', 'Follow-up Visit']
]

const tabs = computed(() => [
  { id: 'journey', label: 'Journey Events', count: client.value?.journey_events?.length || 0 },
  { id: 'referrals', label: 'Referral', count: client.value?.referral_records?.length || 0 },
  { id: 'tasks', label: 'Follow-Up Task', count: client.value?.follow_up_tasks?.length || 0 },
  { id: 'appointments', label: 'Appointment', count: client.value?.appointments?.length || 0 }
])

const forms = ref(defaultForms())

function today() {
  return new Date().toISOString().slice(0, 10)
}

function defaultForms() {
  return {
    journey: {
      stage: 'contact',
      event_date: today(),
      outcome: 'pending',
      notes: ''
    },
    referrals: {
      receiving_facility: '',
      confirmation_status: 'generated',
      initiation_outcome: 'pending',
      referred_on: today(),
      notes: ''
    },
    tasks: {
      reason: 'tracing',
      status: 'open',
      priority: 'normal',
      due_date: today(),
      notes: '',
      outcome_notes: ''
    },
    appointments: {
      visit_purpose: 'clinical_review',
      appointment_date: today(),
      appointment_time: '',
      facility: '',
      notes: ''
    }
  }
}

function modalTitle(type) {
  const verb = editingRecord.value ? 'Edit' : 'Add'
  return {
    journey: `${verb} Journey Event`,
    referrals: `${verb} Referral`,
    tasks: `${verb} Follow-Up Task`,
    appointments: editingRecord.value ? 'Edit Appointment' : 'Create Appointment'
  }[type]
}

function openModal(type) {
  modalType.value = type
  editingRecord.value = null
  forms.value[type] = defaultForms()[type]
  saveError.value = ''
}

function editRecord(type, record) {
  modalType.value = type
  editingRecord.value = record
  saveError.value = ''
  if (type === 'journey') {
    forms.value.journey = {
      stage: record.stage,
      event_date: record.event_date,
      outcome: record.outcome,
      notes: record.notes || ''
    }
  }
  if (type === 'referrals') {
    forms.value.referrals = {
      receiving_facility: record.receiving_facility || '',
      confirmation_status: record.confirmation_status,
      initiation_outcome: record.initiation_outcome,
      referred_on: record.referred_on,
      notes: record.notes || ''
    }
  }
  if (type === 'tasks') {
    forms.value.tasks = {
      assigned_to: record.assigned_to || '',
      reason: record.reason,
      status: record.status,
      priority: record.priority,
      due_date: record.due_date,
      notes: record.notes || '',
      outcome_notes: record.outcome_notes || ''
    }
  }
  if (type === 'appointments') {
    forms.value.appointments = {
      visit_purpose: record.visit_purpose,
      appointment_date: record.appointment_date,
      appointment_time: record.appointment_time,
      facility: record.facility || '',
      notes: record.notes || ''
    }
  }
}

async function refreshClient() {
  loading.value = true
  error.value = ''
  try {
    client.value = await getClient(route.params.id)
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Client record will appear after cached data is available.'
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

async function saveModal() {
  saving.value = true
  saveError.value = ''
  const type = modalType.value
  const payload = { ...forms.value[type] }
  if (payload.facility) payload.facility = Number(payload.facility)
  if (payload.receiving_facility) payload.receiving_facility = Number(payload.receiving_facility)

  try {
    if (editingRecord.value) {
      if (type === 'journey') await updateClientJourneyEvent(client.value.id, editingRecord.value.id, payload)
      if (type === 'referrals') await updateClientReferral(client.value.id, editingRecord.value.id, payload)
      if (type === 'tasks') await updateClientFollowUpTask(client.value.id, editingRecord.value.id, payload)
      if (type === 'appointments') await updateAppointment(editingRecord.value.id, payload)
    } else {
      if (type === 'journey') await createClientJourneyEvent(client.value.id, payload)
      if (type === 'referrals') await createClientReferral(client.value.id, payload)
      if (type === 'tasks') await createClientFollowUpTask(client.value.id, payload)
      if (type === 'appointments') await createClientAppointment(client.value.id, payload)
    }
    modalType.value = ''
    editingRecord.value = null
    await refreshClient()
  } catch (err) {
    saveError.value = err.message
  } finally {
    saving.value = false
  }
}

async function removeRecord(type, record) {
  if (!window.confirm('Delete this record? The client will be notified.')) return
  saving.value = true
  error.value = ''
  try {
    if (type === 'journey') await deleteClientJourneyEvent(client.value.id, record.id)
    if (type === 'referrals') await deleteClientReferral(client.value.id, record.id)
    if (type === 'tasks') await deleteClientFollowUpTask(client.value.id, record.id)
    if (type === 'appointments') await deleteAppointment(record.id)
    await refreshClient()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([refreshClient(), loadFacilities()])
})
</script>

<template>
  <section class="workspace client-switchboard">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Loading client switchboard...</p>
    <template v-else-if="client">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">Client switchboard</p>
          <h2>{{ client.display_name }}</h2>
          <p class="muted">{{ client.reference_number || client.username }} · {{ client.population_group || 'Population group not set' }}</p>
        </div>
        <RouterLink class="secondary-link" to="/clients">
          <span class="material-symbols-outlined" aria-hidden="true">arrow_back</span>
          Clients
        </RouterLink>
      </div>

      <div class="switchboard-layout">
        <aside class="client-profile-panel">
          <h3>Profile</h3>
          <dl>
            <div>
              <dt>Phone</dt>
              <dd>{{ client.phone || '-' }}</dd>
            </div>
            <div>
              <dt>Facility</dt>
              <dd>{{ client.facility_name || '-' }}</dd>
            </div>
            <div>
              <dt>Locator</dt>
              <dd>{{ client.locator?.service_point_name || client.locator?.mobiliser_zone || '-' }}</dd>
            </div>
            <div>
              <dt>Consent</dt>
              <dd>{{ client.consent?.consent_to_follow_up ? 'Follow-up allowed' : 'Follow-up not confirmed' }}</dd>
            </div>
          </dl>
        </aside>

        <main class="switchboard-panel">
          <div class="switchboard-tabs" role="tablist">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              :class="{ active: activeTab === tab.id }"
              @click="activeTab = tab.id"
            >
              {{ tab.label }}
              <span>{{ tab.count }}</span>
            </button>
          </div>

          <div class="switchboard-toolbar">
            <h3>{{ tabs.find((tab) => tab.id === activeTab)?.label }}</h3>
            <button type="button" @click="openModal(activeTab)">
              <span class="material-symbols-outlined" aria-hidden="true">add</span>
              Add New
            </button>
          </div>

          <div v-if="activeTab === 'journey'" class="data-table">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Stage</th>
                  <th>Outcome</th>
                  <th>Notes</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="event in client.journey_events" :key="event.id">
                  <td>{{ event.event_date }}</td>
                  <td>{{ event.stage_display }}</td>
                  <td>{{ event.outcome_display }}</td>
                  <td>{{ event.notes || '-' }}</td>
                  <td>
                    <div class="action-buttons">
                      <button type="button" class="btn-icon btn-view" title="Edit" @click="editRecord('journey', event)">
                        <span class="material-symbols-outlined" aria-hidden="true">edit</span>
                      </button>
                      <button type="button" class="btn-icon btn-delete" title="Delete" @click="removeRecord('journey', event)">
                        <span class="material-symbols-outlined" aria-hidden="true">delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!client.journey_events.length">
                  <td colspan="5" class="empty-state">No journey events yet.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="activeTab === 'referrals'" class="data-table">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Code</th>
                  <th>Receiving Facility</th>
                  <th>Status</th>
                  <th>Outcome</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="referral in client.referral_records" :key="referral.id">
                  <td>{{ referral.referred_on }}</td>
                  <td>{{ referral.referral_code }}</td>
                  <td>{{ referral.receiving_facility_name || referral.receiving_hub || '-' }}</td>
                  <td>{{ referral.confirmation_status_display }}</td>
                  <td>{{ referral.initiation_outcome_display }}</td>
                  <td>
                    <div class="action-buttons">
                      <button type="button" class="btn-icon btn-view" title="Edit" @click="editRecord('referrals', referral)">
                        <span class="material-symbols-outlined" aria-hidden="true">edit</span>
                      </button>
                      <button type="button" class="btn-icon btn-delete" title="Delete" @click="removeRecord('referrals', referral)">
                        <span class="material-symbols-outlined" aria-hidden="true">delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!client.referral_records.length">
                  <td colspan="6" class="empty-state">No referrals yet.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="activeTab === 'tasks'" class="data-table">
            <table>
              <thead>
                <tr>
                  <th>Due</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Notes</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="task in client.follow_up_tasks" :key="task.id">
                  <td>{{ task.due_date }}</td>
                  <td>{{ task.reason_display }}</td>
                  <td>{{ task.status_display }}</td>
                  <td>{{ task.priority_display }}</td>
                  <td>{{ task.notes || task.outcome_notes || '-' }}</td>
                  <td>
                    <div class="action-buttons">
                      <button type="button" class="btn-icon btn-view" title="Edit" @click="editRecord('tasks', task)">
                        <span class="material-symbols-outlined" aria-hidden="true">edit</span>
                      </button>
                      <button type="button" class="btn-icon btn-delete" title="Delete" @click="removeRecord('tasks', task)">
                        <span class="material-symbols-outlined" aria-hidden="true">delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!client.follow_up_tasks.length">
                  <td colspan="6" class="empty-state">No follow-up tasks yet.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="activeTab === 'appointments'" class="data-table">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Purpose</th>
                  <th>Facility</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="appointment in client.appointments" :key="appointment.id">
                  <td>{{ appointment.appointment_date }}</td>
                  <td>{{ appointment.appointment_time }}</td>
                  <td>{{ appointment.visit_purpose_display }}</td>
                  <td>{{ appointment.facility_name }}</td>
                  <td>{{ appointment.status_display }}</td>
                  <td>
                    <div class="action-buttons">
                      <button type="button" class="btn-icon btn-view" title="Edit" @click="editRecord('appointments', appointment)">
                        <span class="material-symbols-outlined" aria-hidden="true">edit</span>
                      </button>
                      <button type="button" class="btn-icon btn-delete" title="Delete" @click="removeRecord('appointments', appointment)">
                        <span class="material-symbols-outlined" aria-hidden="true">delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!client.appointments.length">
                  <td colspan="6" class="empty-state">No appointments yet.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </template>

    <div v-if="modalType" class="modal-backdrop" @click.self="!saving && (modalType = '')">
      <form class="modal-card wide" @submit.prevent="saveModal">
        <h3>{{ modalTitle(modalType) }}</h3>
        <p v-if="saveError" class="error">{{ saveError }}</p>

        <div v-if="modalType === 'journey'" class="form-grid">
          <label>
            Stage
            <select v-model="forms.journey.stage" required>
              <option v-for="[value, label] in stageChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Event date
            <input v-model="forms.journey.event_date" type="date" required>
          </label>
          <label>
            Outcome
            <select v-model="forms.journey.outcome" required>
              <option v-for="[value, label] in outcomeChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label class="full-width">
            Notes
            <textarea v-model="forms.journey.notes" rows="3"></textarea>
          </label>
        </div>

        <div v-if="modalType === 'referrals'" class="form-grid">
          <label class="full-width">
            Receiving facility
            <select v-model="forms.referrals.receiving_facility" required>
              <option value="">Select facility</option>
              <option v-for="facility in facilities" :key="facility.id" :value="facility.id">
                {{ facility.name }} - {{ facility.district_name }}, {{ facility.province_name }}
              </option>
            </select>
          </label>
          <label>
            Status
            <select v-model="forms.referrals.confirmation_status" required>
              <option v-for="[value, label] in referralStatusChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Outcome
            <select v-model="forms.referrals.initiation_outcome" required>
              <option v-for="[value, label] in initiationOutcomeChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Referred on
            <input v-model="forms.referrals.referred_on" type="date" required>
          </label>
          <label class="full-width">
            Notes
            <textarea v-model="forms.referrals.notes" rows="3"></textarea>
          </label>
        </div>

        <div v-if="modalType === 'tasks'" class="form-grid">
          <label>
            Reason
            <select v-model="forms.tasks.reason" required>
              <option v-for="[value, label] in taskReasonChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Due date
            <input v-model="forms.tasks.due_date" type="date" required>
          </label>
          <label>
            Status
            <select v-model="forms.tasks.status" required>
              <option v-for="[value, label] in taskStatusChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Priority
            <select v-model="forms.tasks.priority" required>
              <option v-for="[value, label] in priorityChoices" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label class="full-width">
            Notes
            <textarea v-model="forms.tasks.notes" rows="3"></textarea>
          </label>
          <label class="full-width">
            Outcome notes
            <textarea v-model="forms.tasks.outcome_notes" rows="3"></textarea>
          </label>
        </div>

        <div v-if="modalType === 'appointments'" class="form-grid">
          <label>
            Visit purpose
            <select v-model="forms.appointments.visit_purpose" required>
              <option v-for="[value, label] in visitPurposes" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>
            Appointment date
            <input v-model="forms.appointments.appointment_date" type="date" required>
          </label>
          <label>
            Time
            <input v-model="forms.appointments.appointment_time" type="time" required>
          </label>
          <label class="full-width">
            Facility
            <select v-model="forms.appointments.facility" required>
              <option value="">Select facility</option>
              <option v-for="facility in facilities" :key="facility.id" :value="facility.id">
                {{ facility.name }} - {{ facility.district_name }}, {{ facility.province_name }}
              </option>
            </select>
          </label>
          <label class="full-width">
            Notes
            <textarea v-model="forms.appointments.notes" rows="3"></textarea>
          </label>
        </div>

        <div class="modal-actions">
          <button type="button" class="secondary" :disabled="saving" @click="modalType = ''">Cancel</button>
          <button type="submit" :disabled="saving">{{ saving ? 'Saving...' : 'Save' }}</button>
        </div>
      </form>
    </div>
  </section>
</template>
