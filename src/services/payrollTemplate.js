import { API_BASE } from './apiBase'

export async function generatePayrollTemplate(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-template`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to generate the payroll template')
  return response.json()
}

export async function fetchPayrollTemplateStatus(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-template/status`)
  if (!response.ok) throw new Error('Failed to check the payroll template')
  return response.json()
}

export async function fetchPayrollTemplateFile(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-template/file`)
  if (!response.ok) throw new Error('Failed to read the saved payroll template')
  return response.arrayBuffer()
}
