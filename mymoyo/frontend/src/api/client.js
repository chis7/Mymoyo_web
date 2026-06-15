const API_ROOT = '/api'

function getCookie(name) {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')[1]
}

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }

  const csrfToken = getCookie('csrftoken')
  if (csrfToken && !headers.has('X-CSRFToken')) {
    headers.set('X-CSRFToken', decodeURIComponent(csrfToken))
  }

  const response = await fetch(`${API_ROOT}${path}`, {
    credentials: 'include',
    ...options,
    headers
  })

  if (response.status === 204) {
    return null
  }

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.detail || data.error || 'Request failed.')
    error.response = response
    error.data = data
    throw error
  }
  return data
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

export function listAppointments() {
  return apiFetch('/appointments/')
}

export function listFacilities(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/facilities/${query.toString() ? `?${query}` : ''}`)
}

export function listProvinces() {
  return apiFetch('/provinces/')
}
