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

export async function fetchPayrollScheduleSettings(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-schedule-settings`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load payroll schedule settings'))
  return response.json()
}

export async function updatePayrollScheduleSettings(companyId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-schedule-settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update payroll schedule settings'))
  return response.json()
}
