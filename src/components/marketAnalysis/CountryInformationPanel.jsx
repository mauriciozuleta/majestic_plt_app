import { useEffect, useMemo } from 'react'
import CountryCommercialProfile from '../company/tabs/OperationsTab/CountryCommercialProfile'
import MarketAnalysisPanel from '../company/tabs/OperationsTab/MarketAnalysis/MarketAnalysisPanel'
import GlobalTradeDataView from '../globalTradeData/GlobalTradeDataView'
import TaxCalculatorView from '../taxCalculator/TaxCalculatorView'
import { TOURISM_INDICATORS, cellTooltip, formatTourismValue } from '../tourism/tourismFormat'
import { useTaxCalcStore } from '../../store/useTaxCalcStore'
import { IMPORT_DUTY_STRUCTURES } from './importDutyStructures'
import './CountryInformationPanel.css'

const HIDDEN_TOURISM_COLUMNS = ['TOURISM_GDP_TOTAL_PCT', 'TOURISM_EMPLOYMENT']

// The documents of the dashboard table's header, one entry each; `available(country context)` says whether this country has it.
const DOCUMENTS = [
  { key: 'profile', label: 'Commercial Profile', available: () => true },
  { key: 'products', label: 'Country Product Portfolio', available: () => true },
  { key: 'trade-import', label: 'Global Trade Data — Import', available: (ctx) => ctx.reporterCode != null },
  { key: 'trade-export', label: 'Global Trade Data — Export', available: (ctx) => ctx.reporterCode != null },
  { key: 'duties', label: 'Import duties structure', available: (ctx) => ctx.calculator != null },
  { key: 'tourism', label: 'Tourism & Economy', available: () => true },
]

function TourismCard({ country, tourismByIso, tourismState }) {
  const indicators = TOURISM_INDICATORS.filter((indicator) => !HIDDEN_TOURISM_COLUMNS.includes(indicator.code))
  const values = tourismByIso[(country.country_code || '').toUpperCase()] || {}
  return (
    <div className="country-info__tourism">
      <p className="country-info__hint">
        Latest stored value per indicator, each with its own year (Tools ▸ Tourism &amp; Economic Dependency holds the history and the charts).
        {tourismState === 'loading' ? ' Loading…' : ''}
      </p>
      <table className="country-info__tourism-table">
        <thead>
          <tr>
            <th>Indicator</th>
            <th className="is-num">Value</th>
            <th className="is-num">Year</th>
          </tr>
        </thead>
        <tbody>
          {indicators.map((indicator) => {
            const cell = values[indicator.code]
            return (
              <tr key={indicator.code} title={cell ? cellTooltip(cell) : undefined}>
                <td>{indicator.label}</td>
                <td className="is-num">{cell?.value != null ? formatTourismValue(indicator.kind, cell.value) : '—'}</td>
                <td className="is-num">{cell?.value != null ? cell.year : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// Country Information: pick a country and one of its documents, and the document is shown right below. The countries are the ones of the Dashboard table; the documents are
// its column headers (Commercial Profile, Country Product Portfolio, Global Trade Data import/export, Import duties structure, Tourism & Economy), listed only when the country has them.
function CountryInformationPanel({ countries, selection, onSelect, tradeCountryCodes, dutyCalculators, tourismByIso, tourismState, onBuilt }) {
  const country = countries.find((item) => item.id === selection.countryId) || null

  const context = useMemo(() => {
    if (!country) return {}
    const name = country.name.trim().toLowerCase()
    return {
      reporterCode: tradeCountryCodes[name] ?? tradeCountryCodes[`iso:${(country.country_code || '').toUpperCase()}`],
      calculator: dutyCalculators[name],
    }
  }, [country, tradeCountryCodes, dutyCalculators])

  const documents = useMemo(() => DOCUMENTS.filter((document) => document.available(context)), [context])
  const documentKey = documents.some((document) => document.key === selection.docKey) ? selection.docKey : documents[0]?.key

  // a document the new country does not have falls back to the first one it has
  useEffect(() => {
    if (country && documentKey !== selection.docKey) onSelect({ docKey: documentKey })
  }, [country, documentKey, selection.docKey, onSelect])

  // the import-tax calculator works on the country held in its own store: point it at this one
  useEffect(() => {
    if (documentKey === 'duties' && context.calculator) {
      useTaxCalcStore.getState().update({ destination: context.calculator.country, line: null, lineNote: '', result: null })
    }
  }, [documentKey, context.calculator])

  const byRegion = useMemo(() => {
    const groups = new Map()
    countries.forEach((item) => {
      if (!groups.has(item.region)) groups.set(item.region, [])
      groups.get(item.region).push(item)
    })
    return [...groups.entries()]
  }, [countries])

  const renderDocument = () => {
    if (!country) return <p className="country-info__hint">Choose a country to see its documents.</p>
    if (documentKey === 'profile') return <CountryCommercialProfile key={country.id} companyId={country.company_id} country={country} onBuilt={onBuilt} />
    if (documentKey === 'products') {
      return <MarketAnalysisPanel key={`${country.id}:${selection.hsCode || ''}`} companyId={country.company_id} country={country} initialTabKey="products" initialHsCode={selection.hsCode || null} hideTabs onBuilt={onBuilt} />
    }
    if (documentKey === 'trade-import' || documentKey === 'trade-export') {
      return <GlobalTradeDataView key={`${documentKey}:${context.reporterCode}`} initialCountry={String(context.reporterCode)} initialFlow={documentKey === 'trade-export' ? 'X' : 'M'} />
    }
    if (documentKey === 'duties') {
      return (
        <div className="country-info__duties">
          <p className="country-info__hint">{IMPORT_DUTY_STRUCTURES[context.calculator.country.toLowerCase()] || context.calculator.source}</p>
          <TaxCalculatorView key={context.calculator.country} />
        </div>
      )
    }
    if (documentKey === 'tourism') return <TourismCard country={country} tourismByIso={tourismByIso} tourismState={tourismState} />
    return null
  }

  return (
    <div className="country-info">
      <div className="country-info__pickers">
        <label htmlFor="country-info-country">
          Country
          <select id="country-info-country" value={selection.countryId || ''} onChange={(event) => onSelect({ countryId: event.target.value, hsCode: null })}>
            <option value="">Select a country…</option>
            {byRegion.map(([region, items]) => (
              <optgroup key={region} label={region}>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label htmlFor="country-info-document">
          Document
          <select id="country-info-document" value={documentKey || ''} onChange={(event) => onSelect({ docKey: event.target.value, hsCode: null })} disabled={!country}>
            {documents.map((document) => (
              <option key={document.key} value={document.key}>
                {document.label}
              </option>
            ))}
          </select>
        </label>
        {country && (
          <span className="country-info__meta">
            {country.region} · {country.company_name}
          </span>
        )}
      </div>

      <div className="country-info__document">{renderDocument()}</div>
    </div>
  )
}

export default CountryInformationPanel
