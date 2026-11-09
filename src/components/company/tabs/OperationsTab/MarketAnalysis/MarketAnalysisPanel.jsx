import { useState } from 'react'
import CountryCommercialProfile from '../CountryCommercialProfile'
import ColombiaProductAnalysisView from './ColombiaProductAnalysisView'
import USASourcingView from './USASourcingView'
import CustomSourceProductsView from './CustomSourceProductsView'

// Every country's Market Analysis view is exactly these two pills — no
// second pill layer underneath either one; each renders its content
// directly the moment it's selected.
const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'products', label: 'Country Product Portfolio' },
]

// The analysis for one active country: Overview (the country's commercial
// profile, straight away — no extra click) and Country Product Portfolio
// (every product from every source added for this country, wholesaler and
// retail together, see CustomSourceProductsView). `companyId` is the
// company that holds this country in its commercial structure (a region —
// and so its countries — belongs to exactly one company). Mount with
// key={country.id} so switching country starts from a clean tab.
// `initialTabKey` lets a caller (the Market Analysis table's status
// columns) open straight to a pill instead of making the user click it;
// `initialHsCode` lets a caller (Available Categories' country-code links)
// additionally pre-filter the Country Product Portfolio pill down to just
// the product(s) classified under that HS code — see each product view's
// own `highlightHsCode` prop for how it's applied; `onBuilt` fires whenever
// the commercial profile build actually completes, so that caller can
// refresh its "has a document" status.
function MarketAnalysisPanel({ companyId, country, initialTabKey = null, initialHsCode = null, onBuilt, hideTabs = false }) {
  const [tabKey, setTabKey] = useState(initialTabKey || 'overview')

  const renderContent = () => {
    if (tabKey === 'overview') {
      return <CountryCommercialProfile companyId={companyId} country={country} onBuilt={onBuilt} />
    }
    if (tabKey === 'products') {
      const name = country.name.trim().toLowerCase()
      if (name === 'colombia' || name === 'united states') {
        return (
          <div style={{ display: 'grid', gap: '24px' }}>
            {name === 'colombia' ? (
              <ColombiaProductAnalysisView companyId={companyId} highlightHsCode={initialHsCode} />
            ) : (
              <USASourcingView companyId={companyId} highlightHsCode={initialHsCode} />
            )}
            <CustomSourceProductsView countryName={country.name} companyId={companyId} showEmptyHint={false} highlightHsCode={initialHsCode} />
          </div>
        )
      }
      return <CustomSourceProductsView countryName={country.name} companyId={companyId} highlightHsCode={initialHsCode} />
    }
    return null
  }

  return (
    <div>
      {!hideTabs && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {TABS.map((tab) => (
            <button key={tab.key} type="button" onClick={() => setTabKey(tab.key)} className={`app-tab ${tabKey === tab.key ? 'is-active' : ''}`} style={{ borderRadius: '999px', padding: '7px 16px', fontSize: '0.82rem', cursor: 'pointer', border: '1px solid transparent' }}>
              {tab.label}
            </button>
          ))}
        </div>
      )}

      <div style={{ marginTop: hideTabs ? 0 : '16px', border: '1px solid #2a3f5c', borderRadius: '12px', background: '#111f31', padding: '16px' }}>
        {renderContent()}
      </div>
    </div>
  )
}

export default MarketAnalysisPanel
