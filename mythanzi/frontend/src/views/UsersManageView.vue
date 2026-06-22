<script setup>
import { onMounted, ref, watch } from 'vue'

import { listUsers } from '@/api/client'

const users = ref([])
const query = ref('')
const error = ref('')
const loading = ref(false)

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const data = await listUsers(query.value ? { q: query.value } : {})
    users.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine ? err.message : 'Cached user data will appear after an online visit.'
  } finally {
    loading.value = false
  }
}

function userHistoryPath(user) {
  const resourceType = user.profile?.role === 'client' ? 'Patient' : 'Practitioner'
  return `/api/fhir/${resourceType}/user-${user.id}/_history/`
}

watch(query, loadUsers)
onMounted(loadUsers)
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>Users</h2>
        <p class="muted">Search and review portal users inside the PWA.</p>
      </div>
      <input v-model="query" type="search" placeholder="Search users">
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading users...</p>

    <div class="data-table">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Username</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.display_name }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.email || '-' }}</td>
            <td>{{ user.profile?.role_display || '-' }}</td>
            <td>{{ user.profile?.is_active === false || user.is_active === false ? 'Inactive' : 'Active' }}</td>
            <td>
              <div class="action-buttons">
                <a class="btn-icon btn-view" :href="`/users/${user.id}/`" title="View user" aria-label="View user">
                  <span class="material-symbols-outlined" aria-hidden="true">visibility</span>
                </a>
                <a class="btn-icon btn-history" :href="userHistoryPath(user)" title="View history" aria-label="View history">
                  <span class="material-symbols-outlined" aria-hidden="true">history</span>
                </a>
                <a class="btn-icon btn-edit" :href="`/users/${user.id}/edit/`" title="Edit user" aria-label="Edit user">
                  <span class="material-symbols-outlined" aria-hidden="true">edit</span>
                </a>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
