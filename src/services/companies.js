import { API_BASE } from './apiBase'

// The backend stores a bare path for anything it serves itself
// (/company-logos/<id>.<ext> — see persist_logo in routers/companies.py),
// not a full URL, since it doesn't know what origin the frontend is
// running on. Resolve it against API_BASE here instead; leave anything
// else (a data: URL momentarily held mid-upload, or some other absolute
// URL) untouched.
function resolveLogoUrl(logo) {
  if (!logo) return ''
  return logo.startsWith('/') ? `${API_BASE}${logo}` : logo
}

function toFrontendCompany(company) {
  return {
    id: company.id,
    name: company.name,
    logo: resolveLogoUrl(company.logo),
    companyType: company.company_type,
    companyDependency: company.company_dependency,
    parentCompanyId: company.parent_company_id || null,
    accentFrom: company.accent_from,
    accentTo: company.accent_to,
    countryName: company.country_name || '',
    countryCode: company.country_code || '',
    currencyName: company.currency_name || '',
    currencyCode: company.currency_code || '',
    phaseNumber: company.phase_number || null,
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
    country_name: company.countryName || null,
    country_code: company.countryCode || null,
    currency_name: company.currencyName || null,
    currency_code: company.currencyCode || null,
    phase_number: company.phaseNumber || null,
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

export async function updateCompany(companyId, company) {
  const response = await fetch(`${API_BASE}/companies/${companyId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toBackendCompany(company)),
  })
  if (!response.ok) throw new Error('Failed to update company')
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
