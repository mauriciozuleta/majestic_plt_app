import { useState } from 'react'
import { useParams } from 'react-router-dom'
import AirLogisticsView from './AirLogistics/AirLogisticsView'
import './AirLogistics/AirLogistics.css'
import './RevenueStreamsView.css'

const CATEGORIES = [{ key: 'air-logistics', label: 'Air Logistics' }]

// COS/Expenses ▸ Providers, organised by category of provider.
function ProvidersView() {
  const { companyId } = useParams()
  const [category, setCategory] = useState(CATEGORIES[0].key)

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
      {category === 'air-logistics' && <AirLogisticsView companyId={companyId} />}
    </div>
  )
}

export default ProvidersView
