import { API_BASE } from './apiBase'
import { triggerBlobDownload } from './fileDownload'

export async function downloadPayrollTemplate(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-template`)
  if (!response.ok) throw new Error('Failed to generate the payroll template')
  const blob = await response.blob()
  triggerBlobDownload(blob, `${companyId}-payroll-template.xlsx`)
}
