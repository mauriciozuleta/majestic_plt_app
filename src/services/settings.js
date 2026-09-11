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

export async function updateEnabledBenefits(benefitKeys) {
  const response = await fetch(`${API_BASE}/settings/enabled-benefits`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ benefit_keys: benefitKeys }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update enabled benefits'))
  return response.json()
}

export async function updateInflation(inflationPct) {
  const response = await fetch(`${API_BASE}/settings/inflation`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inflation_pct: inflationPct }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update inflation'))
  return response.json()
}

export async function updateColombiaExchangeRate(copPerUsd) {
  const response = await fetch(`${API_BASE}/settings/colombia-exchange-rate`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cop_per_usd: copPerUsd }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update the Colombia exchange rate'))
  return response.json()
}

export async function updateColombiaReferenceFigures(smmlvCop, uvtCop) {
  const response = await fetch(`${API_BASE}/settings/colombia-reference-figures`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ smmlv_cop: smmlvCop, uvt_cop: uvtCop }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update the Colombia reference figures'))
  return response.json()
}

export async function updatePayrollSchedule(payload) {
  const response = await fetch(`${API_BASE}/settings/payroll-schedule`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update the payroll schedule'))
  return response.json()
}