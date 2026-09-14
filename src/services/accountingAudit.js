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

export async function fetchAuditSettings() {
  const response = await fetch(`${API_BASE}/accounting-audit/settings`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load the Accounting Health Check settings'))
  return response.json()
}

export async function updateAuditSettings(payload) {
  const response = await fetch(`${API_BASE}/accounting-audit/settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update the Accounting Health Check settings'))
  return response.json()
}

export async function runAuditNow(scopeCompanyId) {
  const response = await fetch(`${API_BASE}/accounting-audit/run-now`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope_company_id: scopeCompanyId || null }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to run the accounting audit'))
  return response.json()
}

export async function fetchAuditRuns(limit = 50) {
  const response = await fetch(`${API_BASE}/accounting-audit/runs?limit=${limit}`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load audit run history'))
  return response.json()
}

export async function fetchAuditRun(runId) {
  const response = await fetch(`${API_BASE}/accounting-audit/runs/${runId}`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load the audit run'))
  return response.json()
}
