import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import { fetchCommercialCountries } from '../../../../services/commercialStructure'
import CommercialOperationsView from './CommercialOperationsView/CommercialOperationsView'
import CountryCommercialProfile from './CountryCommercialProfile'
import CountryCompetitivenessAnalysis from './CountryCompetitivenessAnalysis'
import ColombiaProductAnalysisView from './MarketAnalysis/ColombiaProductAnalysisView'
import USASourcingView from './MarketAnalysis/USASourcingView'

const FRESH24_COMPANY_NAME = 'FRESH24'
// Each country's Market Analysis view is grouped into 3 tabs. Import
// Analysis deliberately mirrors Export Analysis's pill labels but is not
// wired to any real content yet — its sections all render the same
// "coming soon" placeholder regardless of which pill is picked.
const MARKET_ANALYSIS_TABS = [
  {
    key: 'overview',
    label: 'Overview',
    sections: [
      { key: 'commercial-profile', label: 'Country Commercial Profile' },
      { key: 'country-competitiveness', label: 'Country Competitiveness Analysis' },
    ],
  },
  {
    key: 'export-analysis',
    label: 'Export Analysis',
    sections: [
      { key: 'products', label: 'Product Analysis' },
      { key: 'historical', label: 'Historical Analysis' },
      { key: 'product-competitiveness', label: 'Product Competitiveness Analysis' },
    ],
  },
  {
    key: 'import-analysis',
    label: 'Import Analysis',
    inert: true,
    sections: [
      { key: 'import-products', label: 'Product Analysis' },
      { key: 'import-historical', label: 'Historical Analysis' },
      { key: 'import-product-competitiveness', label: 'Product Competitiveness Analysis' },
    ],
  },
]

function OperationsTab() {
  const { sub, companyId } = useParams()
  const activeSub = sub ?? 'commercial-operations'
  const companies = useAppStore((state) => state.companies)
  const companyName = companies.find((company) => company.id === companyId)?.name ?? ''
  const isFresh24 = companyName.trim().toUpperCase() === FRESH24_COMPANY_NAME
  const [marketAnalysisCountryId, setMarketAnalysisCountryId] = useState(null)
  const [marketAnalysisTab, setMarketAnalysisTab] = useState(null)
  const [marketAnalysisSection, setMarketAnalysisSection] = useState(null)
  const [countries, setCountries] = useState([])

  useEffect(() => {
    if (!companyId) return
    fetchCommercialCountries(companyId)
      .then(setCountries)
      .catch(() => setCountries([]))
  }, [companyId])

  if (activeSub === 'commercial-operations') {
    return <CommercialOperationsView companyId={companyId} />
  }

  return (
    <div className="panel-surface" style={{ padding: '16px 0', boxSizing: 'border-box' }}>
      <div style={{ padding: '0 8px', width: '100%' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: '2rem', fontWeight: 700, color: '#e6edf8' }}>Market Analysis</h3>
        <p style={{ color: '#cfe0f8', marginBottom: '18px' }}>Market analysis insights and local demand review.</p>

        <div>
          <span style={{ display: 'block', marginBottom: '10px', color: '#cfe0f8', fontWeight: 600 }}>
            Countries in Commercial Structure
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {countries.length === 0 ? (
              <span style={{ color: '#8ea3c2', fontSize: '0.85rem' }}>No countries added yet.</span>
            ) : (
              countries.map((country) => {
                const isSelected = marketAnalysisCountryId === country.id
                return (
                  <button
                    key={country.id}
                    type="button"
                    onClick={
                      isFresh24
                        ? () => {
                            setMarketAnalysisCountryId(isSelected ? null : country.id)
                            setMarketAnalysisTab(null)
                            setMarketAnalysisSection(null)
                          }
                        : undefined
                    }
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '6px 14px',
                      borderRadius: '999px',
                      border: isSelected ? '1px solid #f59e0b' : '1px solid #2a3f5c',
                      background: isSelected ? 'rgba(245, 158, 11, 0.3)' : 'transparent',
                      boxShadow: isSelected ? '0 0 0 1px rgba(245, 158, 11, 0.35)' : 'none',
                      color: isSelected ? '#fff7ed' : '#8ea3c2',
                      fontSize: '0.8rem',
                      fontWeight: isSelected ? 700 : 500,
                      cursor: isFresh24 ? 'pointer' : 'default',
                    }}
                  >
                    {country.name}
                  </button>
                )
              })
            )}
          </div>
        </div>

        {isFresh24 && marketAnalysisCountryId && (
          <div style={{ marginTop: '26px' }}>
            <span style={{ display: 'block', marginBottom: '10px', color: '#cfe0f8', fontWeight: 600 }}>
              {countries.find((item) => item.id === marketAnalysisCountryId)?.name ?? 'Selected country'}
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {MARKET_ANALYSIS_TABS.map((tab) => {
                const isSelected = marketAnalysisTab === tab.key
                return (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => {
                      setMarketAnalysisTab(tab.key)
                      setMarketAnalysisSection(null)
                    }}
                    style={{
                      padding: '7px 16px',
                      borderRadius: '999px',
                      border: isSelected ? '1px solid #3b82f6' : '1px solid #2a3f5c',
                      background: isSelected ? 'rgba(59, 130, 246, 0.28)' : 'transparent',
                      boxShadow: isSelected ? '0 0 0 1px rgba(59, 130, 246, 0.4)' : 'none',
                      color: isSelected ? '#eaf3ff' : '#8ea3c2',
                      fontSize: '0.82rem',
                      fontWeight: isSelected ? 700 : 600,
                      cursor: 'pointer',
                    }}
                  >
                    {tab.label}
                  </button>
                )
              })}
            </div>

            {marketAnalysisTab &&
              (() => {
                const activeTab = MARKET_ANALYSIS_TABS.find((tab) => tab.key === marketAnalysisTab)
                if (!activeTab) return null
                return (
                  <div style={{ marginTop: '18px' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {activeTab.sections.map((section) => {
                        const isSelected = marketAnalysisSection === section.key
                        return (
                          <button
                            key={section.key}
                            type="button"
                            onClick={() => setMarketAnalysisSection(section.key)}
                            style={{
                              padding: '6px 14px',
                              borderRadius: '999px',
                              border: isSelected ? '1px solid #35D399' : '1px solid #2a3f5c',
                              background: isSelected ? 'rgba(53, 211, 153, 0.3)' : 'transparent',
                              boxShadow: isSelected ? '0 0 0 1px rgba(53, 211, 153, 0.35)' : 'none',
                              color: isSelected ? '#ecfdf5' : '#8ea3c2',
                              fontSize: '0.76rem',
                              fontWeight: isSelected ? 700 : 500,
                              cursor: 'pointer',
                            }}
                          >
                            {section.label}
                          </button>
                        )
                      })}
                    </div>

                    {marketAnalysisSection && (
                      <div
                        style={{
                          marginTop: '16px',
                          border: '1px solid #2a3f5c',
                          borderRadius: '12px',
                          background: '#111f31',
                          padding: '16px',
                        }}
                      >
                        {activeTab.inert ? (
                          <p style={{ color: '#8ea3c2', margin: 0 }}>
                            Import Analysis is not wired up yet — this pill is a placeholder for a future module.
                          </p>
                        ) : (
                          <>
                            {marketAnalysisSection === 'products' &&
                              (() => {
                                const country = countries.find((item) => item.id === marketAnalysisCountryId)
                                const countryName = country?.name?.trim().toLowerCase()
                                if (countryName === 'colombia') {
                                  return <ColombiaProductAnalysisView />
                                }
                                if (countryName === 'united states') {
                                  return <USASourcingView />
                                }
                                return (
                                  <p style={{ color: '#8ea3c2', margin: 0 }}>
                                    Product analysis is not yet available for {country?.name ?? 'this country'}.
                                  </p>
                                )
                              })()}

                            {marketAnalysisSection === 'historical' && (
                              <p style={{ color: '#8ea3c2', margin: 0 }}>Historical analysis is coming soon.</p>
                            )}

                            {marketAnalysisSection === 'commercial-profile' &&
                              (() => {
                                const country = countries.find((item) => item.id === marketAnalysisCountryId)
                                if (!country) {
                                  return <p style={{ color: '#8ea3c2', margin: 0 }}>Select a country to build its commercial profile.</p>
                                }
                                return <CountryCommercialProfile companyId={companyId} country={country} />
                              })()}

                            {marketAnalysisSection === 'country-competitiveness' &&
                              (() => {
                                const country = countries.find((item) => item.id === marketAnalysisCountryId)
                                if (!country) {
                                  return <p style={{ color: '#8ea3c2', margin: 0 }}>Select a country to run a competitiveness analysis.</p>
                                }
                                return <CountryCompetitivenessAnalysis companyId={companyId} sourceCountry={country} />
                              })()}

                            {marketAnalysisSection === 'product-competitiveness' && (
                              <p style={{ color: '#8ea3c2', margin: 0 }}>Product Competitiveness Analysis is coming soon.</p>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })()}
          </div>
        )}
      </div>
    </div>
  )
}

export default OperationsTab
