import { API_BASE } from './apiBase'

export async function fetchPayrollLevels() {
  const response = await fetch(`${API_BASE}/payroll-levels`)
  if (!response.ok) throw new Error('Failed to load payroll levels')
  return response.json()
}

export async function savePayrollLevels(levels) {
  const response = await fetch(`${API_BASE}/payroll-levels`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(
      levels.map((level) => ({
        level: level.level,
        yearly: Number(level.yearly) || 0,
        percentage: level.percentage === '' || level.percentage == null ? null : Number(level.percentage),
        monthly: level.monthly === '' || level.monthly == null ? null : Number(level.monthly),
      })),
    ),
  })
  if (!response.ok) throw new Error('Failed to save payroll levels')
  return response.json()
}
