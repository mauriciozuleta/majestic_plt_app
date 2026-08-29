import { API_BASE } from './apiBase'

export async function fetchRoadmapTasks(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/roadmap-tasks`)
  if (!response.ok) throw new Error('Failed to load roadmap tasks')
  return response.json()
}

export async function createRoadmapTask(companyId, task) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/roadmap-tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(task),
  })
  if (!response.ok) throw new Error('Failed to create task')
  return response.json()
}

export async function updateRoadmapTask(taskId, updates) {
  const response = await fetch(`${API_BASE}/roadmap-tasks/${taskId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!response.ok) throw new Error('Failed to update task')
  return response.json()
}

export async function deleteRoadmapTask(taskId) {
  const response = await fetch(`${API_BASE}/roadmap-tasks/${taskId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error('Failed to delete task')
}
