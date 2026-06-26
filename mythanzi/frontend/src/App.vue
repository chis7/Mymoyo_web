<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { getMe, getNotificationSummary, logout } from '@/api/client'

const router = useRouter()
const user = ref(null)
const navigation = ref([])
const online = ref(navigator.onLine)
const deferredInstallPrompt = ref(null)
const installMessage = ref('')
const installed = ref(window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone)
const notificationsOpen = ref(false)
const notificationSummary = ref({ unread_count: 0, results: [] })

const displayName = computed(() => user.value?.display_name || 'MyThanzi')
const facilityName = computed(() => user.value?.profile?.facility_name || '')
const canInstall = computed(() => deferredInstallPrompt.value && !installed.value)

const navIcons = {
  Dashboard: 'home',
  Locations: 'map',
  Users: 'manage_accounts',
  Clients: 'clinical_notes',
  Appointments: 'calendar_month',
  Notifications: 'notifications',
  Profile: 'account_circle'
}

async function refreshSession() {
  try {
    const data = await getMe()
    user.value = data.user
    navigation.value = data.navigation
    await refreshNotifications()
  } catch {
    user.value = null
    navigation.value = []
  }
}

async function refreshNotifications() {
  if (!user.value) return
  try {
    notificationSummary.value = await getNotificationSummary()
  } catch {
    notificationSummary.value = { unread_count: 0, results: [] }
  }
}

async function signOut() {
  await logout().catch(() => null)
  user.value = null
  navigation.value = []
  notificationSummary.value = { unread_count: 0, results: [] }
  router.push('/login')
}

function formatAlertDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

async function installApp() {
  installMessage.value = ''

  if (!deferredInstallPrompt.value) {
    installMessage.value = 'Use your browser menu and choose Install app.'
    return
  }

  deferredInstallPrompt.value.prompt()
  const choice = await deferredInstallPrompt.value.userChoice
  deferredInstallPrompt.value = null

  if (choice.outcome === 'accepted') {
    installed.value = true
    installMessage.value = 'MyThanzi is installing.'
  } else {
    installMessage.value = 'Install cancelled. You can try again from the browser install icon.'
  }
}

onMounted(() => {
  refreshSession()

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferredInstallPrompt.value = event
  })
  window.addEventListener('appinstalled', () => {
    installed.value = true
    deferredInstallPrompt.value = null
    installMessage.value = 'MyThanzi is installed.'
  })
  window.addEventListener('online', () => {
    online.value = true
    refreshSession()
  })
  window.addEventListener('offline', () => {
    online.value = false
  })
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/">
        <span class="brand-icon material-symbols-outlined">health_and_safety</span>
        <span class="brand-name">
          MyThanzi
          <small>My life. My care.</small>
        </span>
      </RouterLink>

      <section v-if="canInstall || installMessage" class="install-card">
        <div>
          <strong>Install MyThanzi</strong>
          <small>{{ installMessage || 'Save this portal to your device for quicker access.' }}</small>
        </div>
        <button v-if="canInstall" type="button" @click="installApp">
          <span class="material-symbols-outlined" aria-hidden="true">download</span>
          Install
        </button>
      </section>

      <nav class="nav-list" aria-label="Primary">
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path.replace('/app', '') || '/'">
          <span class="nav-icon material-symbols-outlined">{{ navIcons[item.label] || 'radio_button_unchecked' }}</span>
          {{ item.label }}
        </RouterLink>
        <RouterLink v-if="!user" to="/login">
          <span class="nav-icon material-symbols-outlined">login</span>
          Sign in
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="user-pill">
          <span class="topbar-life-icon material-symbols-outlined">favorite</span>
          <span>
            <strong>{{ user?.role || 'Portal' }}</strong>
            <small>{{ facilityName || (online ? 'Connected' : 'Offline mode') }}</small>
          </span>
        </div>
      </div>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div class="topbar-life">
          <span class="topbar-life-icon material-symbols-outlined">health_and_safety</span>
          <div>
            <p class="eyebrow">{{ online ? 'Online' : 'Offline mode' }}</p>
            <h1>{{ displayName }}</h1>
            <small v-if="facilityName" class="user-facility">{{ facilityName }}</small>
          </div>
        </div>

        <div class="topbar-actions">
          <div v-if="user" class="topbar-notification-menu">
            <button
              class="topbar-notification-link"
              :class="{ 'has-unread': notificationSummary.unread_count }"
              type="button"
              :aria-expanded="String(notificationsOpen)"
              aria-controls="notificationDropdown"
              @click="notificationsOpen = !notificationsOpen"
            >
              <span class="material-symbols-outlined" aria-hidden="true">notifications</span>
              <span v-if="notificationSummary.unread_count" class="notification-count">
                {{ notificationSummary.unread_count }}
              </span>
            </button>
            <div id="notificationDropdown" class="notification-dropdown" :class="{ open: notificationsOpen }">
              <div class="notification-dropdown-header">
                <span>Alerts</span>
                <span v-if="notificationSummary.unread_count" class="badge">{{ notificationSummary.unread_count }}</span>
              </div>
              <div class="notification-dropdown-list">
                <RouterLink
                  v-for="notification in notificationSummary.results"
                  :key="notification.id"
                  class="notification-dropdown-item"
                  :class="notification.is_unread ? 'is-unread' : 'is-read'"
                  to="/notifications"
                  @click="notificationsOpen = false"
                >
                  <span class="alert-stripe" aria-hidden="true"></span>
                  <span>
                    <span class="notification-dropdown-title">{{ notification.title }}</span>
                    <span class="notification-dropdown-meta">{{ formatAlertDate(notification.created_at) }}</span>
                  </span>
                </RouterLink>
                <div v-if="!notificationSummary.results.length" class="notification-dropdown-empty">No alerts yet.</div>
              </div>
              <div class="notification-dropdown-footer">
                <RouterLink to="/notifications" @click="notificationsOpen = false">View All Alerts</RouterLink>
              </div>
            </div>
          </div>
          <button v-if="canInstall" class="install-button" type="button" @click="installApp">
            <span class="material-symbols-outlined" aria-hidden="true">download</span>
            Install app
          </button>
          <button v-if="user" class="account-menu-button" type="button" title="Sign out" @click="signOut">
            <span class="material-symbols-outlined" aria-hidden="true">logout</span>
            Sign out
          </button>
        </div>
      </header>

      <RouterView @authenticated="refreshSession" />
    </main>
  </div>
</template>
