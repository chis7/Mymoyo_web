<script setup>
import { onMounted, ref } from 'vue'

import { getBootstrap } from '@/api/client'

const data = ref(null)

onMounted(async () => {
  data.value = await getBootstrap()
})
</script>

<template>
  <section class="panel">
    <h2>Command Center</h2>
    <p class="muted">Role-aware dashboard data from the Django REST API.</p>
    <pre v-if="data">{{ data.appointment_summary }}</pre>
    <p v-else>Loading dashboard...</p>
  </section>
</template>
