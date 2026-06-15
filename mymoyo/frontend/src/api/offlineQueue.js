const QUEUE_KEY = 'mymoyo:offline-queue'

export function loadOfflineQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]')
  } catch {
    return []
  }
}

export function queueOfflineRequest(request) {
  const queue = loadOfflineQueue()
  queue.push({
    ...request,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString()
  })
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
  return queue
}

export function clearOfflineQueue() {
  localStorage.removeItem(QUEUE_KEY)
}
