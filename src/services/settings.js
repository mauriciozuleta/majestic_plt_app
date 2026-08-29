import { API_BASE } from './apiBase'

async function readErrorDetail(response, fallbackMessage) {
  try {
    const payload = await response.json()
    if (payload?.detail) return payload.detail
  } catch {
    // Ignore parse errors and use fallback message.
  }

  return fallbackMessage
}

export async function fetchSettings() {
  const response = await fetch(`${API_BASE}/settings`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load settings'))
  return response.json()
}

export async function updateCalendarMode(mode, realStartDate) {
  const response = await fetch(`${API_BASE}/settings/calendar-mode`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, real_start_date: realStartDate }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update calendar mode'))
  return response.json()
}

export async function assignSimulationStartDate(realStartDate) {
  const response = await fetch(`${API_BASE}/settings/assign-start-date`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ real_start_date: realStartDate }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to convert simulation dates'))
  return response.json()
}

export async function updateTimeProjection(projectionYears) {
  const response = await fetch(`${API_BASE}/settings/time-projection`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projection_years: projectionYears }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update time projection'))
  return response.json()
}