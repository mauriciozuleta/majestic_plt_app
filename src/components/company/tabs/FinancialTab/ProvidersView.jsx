import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import AirLogisticsView from './AirLogistics/AirLogisticsView'
import ExpenseProvidersView from './ExpenseProvidersView'
import './AirLogistics/AirLogistics.css'
import './RevenueStreamsView.css'

const CATEGORIES = [
  { key: 'air-logistics', label: 'Air Logistics' },
  { key: 'expenses', label: 'Expenses' },
]

// COS/Expenses ▸ Providers, organised by category of provider.
function ProvidersView() {
  const { companyId } = useParams()
  const [category, setCategory] = useState(CATEGORIES[0].key)
  const companies = useAppStore(state => state.companies)
  const company = companies.find(item => item.id === companyId)
  const cargo = companies.find(item => /majestic.*cargo/i.test(item.name))
  const moved = !!cargo && (/^fresh\s*24$/i.test(company?.name || '') || companyId === cargo.id)
  const fleetPath = moved ? `/company/${cargo.id}/management/air-operations-management/fleet-management` : undefined

  return (
    <div className="panel-surface">
      <h4>Providers</h4>
      <div className="providers-view__categories">
        {CATEGORIES.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`providers-view__category ${category === item.key ? 'is-active' : ''}`}
            onClick={() => setCategory(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {category === 'air-logistics' && <AirLogisticsView key={companyId} companyId={companyId} showAircraft={!moved} fleetPath={fleetPath} />}
      {category === 'expenses' && <ExpenseProvidersView key={companyId} companyId={companyId} />}
    </div>
  )
}

export default ProvidersView
