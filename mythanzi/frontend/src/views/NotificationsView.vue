<script setup>
import { onMounted, ref } from 'vue'

import { listNotifications, markNotificationRead } from '@/api/client'

const notifications = ref([])
const error = ref('')
const loading = ref(true)

function directionsUrl(notification) {
  const appointment = notification.appointment_detail
  if (!appointment) return ''
  const query = [
    appointment.facility_name,
    appointment.district_name,
    appointment.province_name
  ].filter(Boolean).join(' ')
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`
}

async function refreshNotifications() {
  loading.value = true
  error.value = ''
  try {
    const data = await listNotifications()
    notifications.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Notifications will appear after cached data is available.'
  } finally {
    loading.value = false
  }
}

async function markRead(notification) {
  await markNotificationRead(notification.id)
  await refreshNotifications()
}

onMounted(refreshNotifications)
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>My Notifications</h2>
        <p class="muted">Appointment updates and portal messages sent to your account.</p>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Loading notifications...</p>
    <div v-else class="alert-list-panel">
      <article
        v-for="notification in notifications"
        :key="notification.id"
        class="alert-row"
        :class="{ unread: notification.is_unread }"
      >
        <span class="alert-row-stripe" aria-hidden="true"></span>
        <div>
          <div class="alert-row-head">
            <strong>{{ notification.title }}</strong>
            <span>{{ new Date(notification.created_at).toLocaleString() }}</span>
          </div>
          <p>{{ notification.message }}</p>
          <div v-if="notification.appointment_detail" class="alert-row-meta">
            <span>{{ notification.appointment_detail.appointment_date }} at {{ notification.appointment_detail.appointment_time }}</span>
            <span>{{ notification.appointment_detail.facility_name }}</span>
          </div>
          <div class="action-buttons">
            <a
              v-if="notification.appointment_detail"
              class="secondary-link"
              :href="directionsUrl(notification)"
              target="_blank"
              rel="noopener noreferrer"
            >
              <span class="material-symbols-outlined" aria-hidden="true">directions</span>
              Directions
            </a>
            <button v-if="notification.is_unread" type="button" class="secondary small-button" @click="markRead(notification)">
              Mark as read
            </button>
          </div>
        </div>
      </article>
      <p v-if="!notifications.length" class="muted empty-state">No notifications yet.</p>
    </div>
  </section>
</template>
