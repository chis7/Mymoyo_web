<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { getDashboardStats } from '@/api/client'

const stats = ref(null)
const error = ref('')

onMounted(async () => {
  try {
    stats.value = await getDashboardStats()
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Dashboard data will appear after it has been cached online.'
  }
})
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>Dashboard</h2>
        <p class="muted">PWA command center for administration and service delivery.</p>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <div v-else-if="stats" class="card-grid">
      <RouterLink v-for="card in stats.cards" :key="card.title" class="metric-card" :to="card.path">
        <span>{{ card.title }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.meta }}</small>
      </RouterLink>
    </div>
    <p v-else class="muted">Loading dashboard...</p>

    <section v-if="stats" class="panel">
      <h3>Users by role</h3>
      <div class="table-list">
        <article v-for="role in stats.roles" :key="role.role" class="row-card tight">
          <strong>{{ role.label }}</strong>
          <span>{{ role.count }}</span>
        </article>
      </div>
    </section>
  </section>
</template>
