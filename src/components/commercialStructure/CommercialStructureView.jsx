import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/useAppStore'
import CommercialStructureEditor from './CommercialStructureEditor'
import './CommercialStructureView.css'

// Portfolio-level page: regions/countries/branches are still per-company
// data (see CommercialStructureEditor), but this page surfaces the whole
// structure from one place in the sidebar instead of burying it inside a
// single company's Operations tab, with a switcher to pick which company's
// structure to view/edit.
function CommercialStructureView() {
  const companies = useAppStore((state) => state.companies)
  const [selectedCompanyId, setSelectedCompanyId] = useState('')

  useEffect(() => {
    if (!companies.length) {
      setSelectedCompanyId('')
      return
    }
    setSelectedCompanyId((current) => (companies.some((company) => company.id === current) ? current : companies[0].id))
  }, [companies])

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
        <CommercialStructureEditor companyId={selectedCompany?.id} companyName={selectedCompany?.name ?? ''} />
      )}
    </section>
  )
}

export default CommercialStructureView
