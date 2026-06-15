<script setup>
import { onMounted, ref } from 'vue'

import { getMe } from '@/api/client'

const profile = ref(null)

onMounted(async () => {
  profile.value = await getMe()
})
</script>

<template>
  <section class="panel">
    <h2>Profile</h2>
    <dl v-if="profile" class="definition-list">
      <dt>Name</dt>
      <dd>{{ profile.user.display_name }}</dd>
      <dt>Role</dt>
      <dd>{{ profile.user.profile.role_display }}</dd>
      <dt>Email</dt>
      <dd>{{ profile.user.email || 'Not set' }}</dd>
    </dl>
    <p v-else>Loading profile...</p>
  </section>
</template>
