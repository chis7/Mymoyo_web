const API_ROOT = '/api'
const LOCATION_QUEUE_KEY = 'mythanzi.locationWriteQueue'

function getCookie(name) {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')[1]
}

export async function apiFetch(path, options = {}) {
  const { timeoutMs, ...fetchOptions } = options
  const controller = timeoutMs ? new AbortController() : null
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null
  const headers = new Headers(options.headers || {})
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }

  const csrfToken = getCookie('csrftoken')
  if (csrfToken && !headers.has('X-CSRFToken')) {
    headers.set('X-CSRFToken', decodeURIComponent(csrfToken))
  }

  try {
    const response = await fetch(`${API_ROOT}${path}`, {
      credentials: 'include',
      ...fetchOptions,
      headers,
      signal: controller?.signal || fetchOptions.signal
    })

    if (response.status === 204) {
      return null
    }

    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const fieldErrors = Object.entries(data)
        .filter(([, value]) => Array.isArray(value) || typeof value === 'string')
        .map(([field, value]) => `${field}: ${Array.isArray(value) ? value.join(', ') : value}`)
      const error = new Error(data.detail || data.error || fieldErrors.join(' ') || 'Request failed.')
      error.response = response
      error.data = data
      throw error
    }
    return data
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('Request timed out.')
    }
    throw error
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId)
  }
}

export function getBootstrap() {
  return apiFetch('/app/bootstrap/')
}

export function getMe() {
  return apiFetch('/auth/me/')
}

export async function login(username, password) {
  await apiFetch('/auth/csrf/')
  return apiFetch('/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  })
}

export function logout() {
  return apiFetch('/auth/logout/', { method: 'POST' })
}

export function listUsers(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/users/${query.toString() ? `?${query}` : ''}`)
}

export function listAppointments() {
  return apiFetch('/appointments/')
}

export function createAppointment(payload) {
  return apiFetch('/appointments/', {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function updateAppointment(id, payload) {
  return apiFetch(`/appointments/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function deleteAppointment(id) {
  return apiFetch(`/appointments/${id}/`, {
    method: 'DELETE',
    timeoutMs: 5000
  })
}

export function listClients(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/clients/${query.toString() ? `?${query}` : ''}`)
}

export function getClient(id) {
  return apiFetch(`/clients/${id}/`)
}

export function saveClientLocator(clientId, payload) {
  return apiFetch(`/clients/${clientId}/locator/`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function saveClientConsent(clientId, payload) {
  return apiFetch(`/clients/${clientId}/consent/`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function createClientJourneyEvent(clientId, payload) {
  return apiFetch(`/clients/${clientId}/journey-events/`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function updateClientJourneyEvent(clientId, eventId, payload) {
  return apiFetch(`/clients/${clientId}/journey-events/${eventId}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function deleteClientJourneyEvent(clientId, eventId) {
  return apiFetch(`/clients/${clientId}/journey-events/${eventId}/`, {
    method: 'DELETE',
    timeoutMs: 5000
  })
}

export function createClientReferral(clientId, payload) {
  return apiFetch(`/clients/${clientId}/referrals/`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function updateClientReferral(clientId, referralId, payload) {
  return apiFetch(`/clients/${clientId}/referrals/${referralId}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function deleteClientReferral(clientId, referralId) {
  return apiFetch(`/clients/${clientId}/referrals/${referralId}/`, {
    method: 'DELETE',
    timeoutMs: 5000
  })
}

export function createClientFollowUpTask(clientId, payload) {
  return apiFetch(`/clients/${clientId}/follow-up-tasks/`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function updateClientFollowUpTask(clientId, taskId, payload) {
  return apiFetch(`/clients/${clientId}/follow-up-tasks/${taskId}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function deleteClientFollowUpTask(clientId, taskId) {
  return apiFetch(`/clients/${clientId}/follow-up-tasks/${taskId}/`, {
    method: 'DELETE',
    timeoutMs: 5000
  })
}

export function createClientAppointment(clientId, payload) {
  return apiFetch(`/clients/${clientId}/appointments/`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function listNotifications() {
  return apiFetch('/notifications/')
}

export function getNotificationSummary() {
  return apiFetch('/notifications/summary/')
}

export function markNotificationRead(id) {
  return apiFetch(`/notifications/${id}/read/`, { method: 'POST' })
}

export function getDashboardStats() {
  return apiFetch('/dashboard/stats/')
}

export function listFacilities(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/facilities/${query.toString() ? `?${query}` : ''}`)
}

export function saveFacility(payload, id = null) {
  return apiFetch(`/facilities/${id ? `${id}/` : ''}`, {
    method: id ? 'PATCH' : 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function listProvinces(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/provinces/${query.toString() ? `?${query}` : ''}`)
}

export function saveProvince(payload, id = null) {
  return apiFetch(`/provinces/${id ? `${id}/` : ''}`, {
    method: id ? 'PATCH' : 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

export function listDistricts(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/districts/${query.toString() ? `?${query}` : ''}`)
}

export function saveDistrict(payload, id = null) {
  return apiFetch(`/districts/${id ? `${id}/` : ''}`, {
    method: id ? 'PATCH' : 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 5000
  })
}

function queueId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function readLocationQueue() {
  try {
    return JSON.parse(localStorage.getItem(LOCATION_QUEUE_KEY) || '[]')
  } catch {
    return []
  }
}

function writeLocationQueue(queue) {
  localStorage.setItem(LOCATION_QUEUE_KEY, JSON.stringify(queue))
  window.dispatchEvent(new CustomEvent('mythanzi:location-queue-changed'))
}

export function getLocationWriteQueue() {
  return readLocationQueue()
}

export function enqueueLocationWrite(change) {
  const queue = readLocationQueue()
  const duplicate = queue.find((queued) => (
    queued.resource === change.resource &&
    String(queued.recordId || '') === String(change.recordId || '') &&
    JSON.stringify(queued.payload || {}) === JSON.stringify(change.payload || {})
  ))

  if (duplicate) return duplicate

  const queuedChange = {
    id: queueId(),
    createdAt: new Date().toISOString(),
    status: 'pending',
    ...change
  }
  writeLocationQueue([...queue, queuedChange])
  return queuedChange
}

async function replayLocationWrite(change) {
  if (change.resource === 'provinces') {
    return saveProvince(change.payload, change.recordId)
  }
  if (change.resource === 'districts') {
    return saveDistrict(change.payload, change.recordId)
  }
  if (change.resource === 'facilities') {
    return saveFacility(change.payload, change.recordId)
  }
  throw new Error('Unknown queued location change.')
}

export async function flushLocationWriteQueue() {
  const queue = readLocationQueue()
  const remaining = []
  const synced = []

  for (const change of queue) {
    try {
      await replayLocationWrite(change)
      synced.push(change)
    } catch (error) {
      remaining.push({
        ...change,
        status: 'pending',
        lastError: error.message || 'Still waiting to sync.'
      })
      break
    }
  }

  const processedIds = new Set([...synced, ...remaining].map((change) => change.id))
  writeLocationQueue([...remaining, ...queue.filter((change) => !processedIds.has(change.id))])
  return { synced, remaining: readLocationQueue() }
}
