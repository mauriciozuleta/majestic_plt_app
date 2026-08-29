import { API_BASE } from './apiBase'

function toFrontendCompany(company) {
  return {
    id: company.id,
    name: company.name,
    logo: company.logo || '',
    companyType: company.company_type,
    companyDependency: company.company_dependency,
    parentCompanyId: company.parent_company_id || null,
    accentFrom: company.accent_from,
    accentTo: company.accent_to,
  }
}

function toBackendCompany(company) {
  return {
    name: company.name,
    logo: company.logo || '',
    company_type: company.companyType,
    company_dependency: company.companyDependency,
    parent_company_id: company.parentCompanyId || null,
    accent_from: company.accentFrom || '#35D399',
    accent_to: company.accentTo || '#0EA5E9',
  }
}

export async function fetchCompanies() {
  const response = await fetch(`${API_BASE}/companies`)
  if (!response.ok) throw new Error('Failed to load companies')
  const companies = await response.json()
  return companies.map(toFrontendCompany)
}

export async function addCompany(company) {
  const response = await fetch(`${API_BASE}/companies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toBackendCompany(company)),
  })
  if (!response.ok) throw new Error('Failed to create company')
  return toFrontendCompany(await response.json())
}

export async function deleteCompany(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error('Failed to delete company')
  }

  return response.json()
}
