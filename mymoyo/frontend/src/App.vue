<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { getMe, logout } from '@/api/client'

const router = useRouter()
const user = ref(null)
const navigation = ref([])
const online = ref(navigator.onLine)

const displayName = computed(() => user.value?.display_name || 'MyMoyo')

async function refreshSession() {
  try {
    const data = await getMe()
    user.value = data.user
    navigation.value = data.navigation
  } catch {
    user.value = null
    navigation.value = []
  }
}

async function signOut() {
  await logout().catch(() => null)
  user.value = null
  navigation.value = []
  router.push('/login')
}

onMounted(() => {
  refreshSession()
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
        <span class="brand-mark">M</span>
        <span>MyMoyo</span>
      </RouterLink>

      <nav class="nav-list" aria-label="Primary">
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path.replace('/app', '') || '/'">
          {{ item.label }}
        </RouterLink>
        <RouterLink v-if="!user" to="/login">Sign in</RouterLink>
      </nav>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ online ? 'Online' : 'Offline mode' }}</p>
          <h1>{{ displayName }}</h1>
        </div>
        <button v-if="user" class="icon-button" type="button" title="Sign out" @click="signOut">
          <span aria-hidden="true">↪</span>
        </button>
      </header>

      <RouterView @authenticated="refreshSession" />
    </main>
  </div>
</template>
