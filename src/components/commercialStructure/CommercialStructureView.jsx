import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAppStore } from '../../store/useAppStore'
import CommercialStructureEditor from './CommercialStructureEditor'
import './CommercialStructureView.css'

// Portfolio-level page: regions/countries/branches are still per-company
// data (see CommercialStructureEditor), but this page surfaces the whole
// structure from one place in the sidebar instead of burying it inside a
// single company's Operations tab, with a switcher to pick which company's
// structure to view/edit.
// the company last looked at is remembered in this browser (the region/country/branch selection is saved per company by the editor)
const COMPANY_KEY = 'commercial-structure:company'

function CommercialStructureView() {
  const companies = useAppStore((state) => state.companies)
  // ?add=Grenada&code=GD&region=Caribbean&company=<id> (from Market Analysis ▸ "Add to Commercial Structure"): open that company and
  // walk the editor through the new country (the subsidiary) and its branch.
  const [searchParams] = useSearchParams()
  const addCountry = searchParams.get('add')
  const prefill = addCountry ? { countryName: addCountry, countryCode: searchParams.get('code') || '', regionName: searchParams.get('region') || '' } : null
  const [selectedCompanyId, setSelectedCompanyId] = useState(() => {
    if (searchParams.get('company')) return searchParams.get('company')
    try {
      return window.localStorage.getItem(COMPANY_KEY) || ''
    } catch {
      return ''
    }
  })

  useEffect(() => {
    if (!companies.length) return // still loading (or none): keep the remembered company instead of wiping it
    setSelectedCompanyId((current) => (companies.some((company) => company.id === current) ? current : companies[0].id))
  }, [companies])

  useEffect(() => {
    if (!selectedCompanyId) return
    try {
      window.localStorage.setItem(COMPANY_KEY, selectedCompanyId)
    } catch {
      // storage unavailable: not remembered
    }
  }, [selectedCompanyId])

  const selectedCompany = companies.find((company) => company.id === selectedCompanyId) ?? null

  return (
    <section className="commercial-structure-view">
      <header className="panel-surface commercial-structure-view__header">
        <div>
          <h3>Commercial Structure</h3>
          <p>Regions, countries, and local branches — per company.</p>
        </div>

        {companies.length > 0 && (
          <label className="commercial-structure-view__company-select">
            Company
            <select value={selectedCompanyId} onChange={(event) => setSelectedCompanyId(event.target.value)}>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {companies.length === 0 ? (
        <div className="panel-surface commercial-structure-view__status">No companies yet — add one from the sidebar first.</div>
      ) : (
        <CommercialStructureEditor key={prefill ? `add:${prefill.countryCode}` : 'edit'} companyId={selectedCompany?.id} companyName={selectedCompany?.name ?? ''} prefill={prefill} />
      )}
    </section>
  )
}

export default CommercialStructureView
