<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { login } from '@/api/client'

const emit = defineEmits(['authenticated'])
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value, password.value)
    emit('authenticated')
    router.push('/')
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <form class="panel form-panel" @submit.prevent="submit">
    <h2>Sign in</h2>
    <label>
      Username
      <input v-model="username" autocomplete="username" required>
    </label>
    <label>
      Password
      <input v-model="password" type="password" autocomplete="current-password" required>
    </label>
    <p v-if="error" class="error">{{ error }}</p>
    <button type="submit" :disabled="loading">{{ loading ? 'Signing in...' : 'Sign in' }}</button>
  </form>
</template>
