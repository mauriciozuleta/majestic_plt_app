import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import {
  createCommercialBranch,
  createCommercialCountry,
  createCommercialRegion,
  deleteCommercialBranch,
  deleteCommercialCountry,
  fetchCommercialBranches,
  fetchCommercialCountries,
  fetchCommercialRegions,
  fetchReferenceCountries,
  fetchReferenceRegions,
  updateCommercialBranch,
  updateCommercialCountry,
  updateCommercialRegion,
} from '../../../../services/commercialStructure'
import CommercialOperationsView from './CommercialOperationsView/CommercialOperationsView'
import AddAirportModal from './AddAirportModal'
import CountryCommercialProfile from './CountryCommercialProfile'
import CountryCompetitivenessAnalysis from './CountryCompetitivenessAnalysis'
import CommercialStructureChart from './CommercialStructureChart/CommercialStructureChart'
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

const emptyForm = {
  regionName: '',
  regionManager: '',
  regionUser: '',
  countryName: '',
  countryCode: '',
  currency: '',
  currencyCode: '',
  countryManager: '',
  countryUser: '',
  branchName: '',
  branchManager: '',
  branchUser: '',
  airport: '',
}

const fallbackRegions = [
  'Africa',
  'Antarctica',
  'Asia-Pacific',
  'Caribbean',
  'Eastern Europe',
  'North America',
  'Oceania',
  'South-Central America',
  'Western Europe',
]

function OperationsTab() {
  const { sub, companyId } = useParams()
  const activeSub = sub ?? 'commercial-structure'
  const companies = useAppStore((state) => state.companies)
  const companyName = companies.find((company) => company.id === companyId)?.name ?? ''
  const isFresh24 = companyName.trim().toUpperCase() === FRESH24_COMPANY_NAME
  const [marketAnalysisCountryId, setMarketAnalysisCountryId] = useState(null)
  const [marketAnalysisTab, setMarketAnalysisTab] = useState(null)
  const [marketAnalysisSection, setMarketAnalysisSection] = useState(null)
  const [regions, setRegions] = useState([])
  const [countries, setCountries] = useState([])
  const [branches, setBranches] = useState([])
  const [referenceRegions, setReferenceRegions] = useState([])
  const [allReferenceCountries, setAllReferenceCountries] = useState([])
  const [selectedRegionName, setSelectedRegionName] = useState('')
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
  const [selectedBranchId, setSelectedBranchId] = useState('')
  const [airportModal, setAirportModal] = useState(null)
  const [form, setForm] = useState(emptyForm)

  const loadStructure = async () => {
    if (!companyId) return

    const [nextRegions, nextCountries, nextBranches] = await Promise.all([
      fetchCommercialRegions(companyId),
      fetchCommercialCountries(companyId),
      fetchCommercialBranches(companyId),
    ])

    setRegions(nextRegions)
    setCountries(nextCountries)
    setBranches(nextBranches)

    if (!selectedRegionName && nextRegions[0]) {
      setSelectedRegionName(nextRegions[0].name)
    }
  }

  useEffect(() => {
    loadStructure().catch(() => undefined)
  }, [companyId])

  useEffect(() => {
    fetchReferenceRegions()
      .then((rows) => {
        const normalized = (Array.isArray(rows) ? rows : [])
          .map((row) => (typeof row === 'string' ? row : row?.region))
          .filter(Boolean)
        setReferenceRegions(normalized.length > 0 ? normalized : fallbackRegions)
        if (!selectedRegionName && normalized[0]) {
          setSelectedRegionName(normalized[0])
        }
      })
      .catch(() => setReferenceRegions(fallbackRegions))
  }, [])

  const selectedRegion = useMemo(
    () => regions.find((region) => region.name === selectedRegionName) ?? null,
    [regions, selectedRegionName],
  )

  const filteredReferenceCountries = useMemo(() => {
    const normalizedRegion = selectedRegionName.trim().toLowerCase()
    if (!normalizedRegion) return []

    return allReferenceCountries.filter(
      (country) => (country.region ?? '').trim().toLowerCase() === normalizedRegion,
    )
  }, [allReferenceCountries, selectedRegionName])

  const selectedReferenceCountry = useMemo(
    () => filteredReferenceCountries.find((country) => country.country_code === selectedCountryCode) ?? null,
    [filteredReferenceCountries, selectedCountryCode],
  )

  const savedCountry = useMemo(
    () =>
      countries.find(
        (country) => country.region_id === selectedRegion?.id && country.country_code === selectedCountryCode,
      ) ?? null,
    [countries, selectedRegion, selectedCountryCode],
  )

  const branchesForCountry = useMemo(
    () => branches.filter((branch) => branch.country_id === savedCountry?.id),
    [branches, savedCountry],
  )

  const selectedBranch = useMemo(
    () => branchesForCountry.find((branch) => branch.id === selectedBranchId) ?? null,
    [branchesForCountry, selectedBranchId],
  )

  const handleChartNodeSelect = (kind, record) => {
    if (kind === 'region') {
      setSelectedRegionName(record.name)
      setSelectedCountryCode('')
      return
    }

    if (kind === 'country') {
      const region = regions.find((item) => item.id === record.region_id)
      if (region) setSelectedRegionName(region.name)
      setSelectedCountryCode(record.country_code || '')
      return
    }

    const country = countries.find((item) => item.id === record.country_id)
    if (country) {
      const region = regions.find((item) => item.id === country.region_id)
      if (region) setSelectedRegionName(region.name)
      setSelectedCountryCode(country.country_code || '')
    }
    setSelectedBranchId(record.id)
  }

  const handleChartNodeDelete = async (kind, record) => {
    const confirmed = window.confirm(
      kind === 'country'
        ? `Delete "${record.name}" and all of its branches? This can't be undone.`
        : `Delete branch "${record.name}"? This can't be undone.`,
    )
    if (!confirmed) return

    try {
      if (kind === 'country') {
        await deleteCommercialCountry(companyId, record.id)
        if (record.id === savedCountry?.id) {
          setSelectedCountryCode('')
          setSelectedBranchId('')
        }
      } else {
        await deleteCommercialBranch(companyId, record.id)
        if (record.id === selectedBranchId) {
          setSelectedBranchId('')
        }
      }
      await loadStructure()
    } catch (error) {
      window.alert(error.message || `Failed to delete ${kind}`)
    }
  }

  useEffect(() => {
    setForm((previous) => ({
      ...previous,
      regionName: selectedRegionName,
      regionManager: selectedRegion?.manager_name ?? '',
      regionUser: selectedRegion?.user_name ?? '',
    }))
  }, [selectedRegionName, selectedRegion])

  useEffect(() => {
    if (!selectedRegionName) {
      setAllReferenceCountries([])
      setSelectedCountryCode('')
      return
    }

    setSelectedCountryCode('')
    fetchReferenceCountries()
      .then((rows) => {
        const normalized = (Array.isArray(rows) ? rows : [])
          .map((row) => ({
            ...row,
            name: row?.name ?? row?.country ?? '',
            country_code: row?.country_code ?? row?.code ?? '',
            currency: row?.currency ?? '',
            currency_code: row?.currency_code ?? '',
            region: row?.region ?? '',
          }))
          .filter((row) => row.name)
        setAllReferenceCountries(normalized)
      })
      .catch(() => setAllReferenceCountries([]))
  }, [selectedRegionName])

  useEffect(() => {
    if (!selectedReferenceCountry) {
      setForm((previous) => ({
        ...previous,
        countryName: '',
        countryCode: '',
        currency: '',
        currencyCode: '',
      }))
      return
    }

    setForm((previous) => ({
      ...previous,
      countryName: selectedReferenceCountry.name,
      countryCode: selectedReferenceCountry.country_code,
      currency: selectedReferenceCountry.currency,
      currencyCode: selectedReferenceCountry.currency_code,
    }))
  }, [selectedReferenceCountry])

  useEffect(() => {
    setForm((previous) => ({
      ...previous,
      countryManager: savedCountry?.manager_name ?? '',
      countryUser: savedCountry?.user_name ?? '',
    }))
  }, [savedCountry])

  const handleSaveRegion = async () => {
    if (!companyId || !selectedRegionName.trim()) return

    if (selectedRegion) {
      await updateCommercialRegion(companyId, selectedRegion.id, {
        manager_name: form.regionManager || null,
        user_name: form.regionUser || null,
      })
    } else {
      await createCommercialRegion(companyId, {
        name: selectedRegionName,
        manager_name: form.regionManager || null,
        user_name: form.regionUser || null,
      })
    }
    await loadStructure()
  }

  const handleSaveCountry = async () => {
    if (!companyId || !selectedRegionName || !form.countryName.trim()) return

    if (savedCountry) {
      await updateCommercialCountry(companyId, savedCountry.id, {
        manager_name: form.countryManager || null,
        user_name: form.countryUser || null,
      })
      await loadStructure()
      return
    }

    let targetRegionId = selectedRegion?.id
    if (!targetRegionId) {
      const createdRegion = await createCommercialRegion(companyId, {
        name: selectedRegionName,
        manager_name: form.regionManager || null,
        user_name: form.regionUser || null,
      })
      targetRegionId = createdRegion.id
      await loadStructure()
    }

    await createCommercialCountry(companyId, {
      region_id: targetRegionId,
      name: form.countryName,
      country_code: form.countryCode || null,
      currency: form.currency || null,
      currency_code: form.currencyCode || null,
      manager_name: form.countryManager || null,
      user_name: form.countryUser || null,
    })
    await loadStructure()
  }

  const handleInputChange = (field, value) => {
    setForm((previous) => ({ ...previous, [field]: value }))
  }

  const handleSaveAirport = async (payload) => {
    if (!companyId || !savedCountry) return

    if (airportModal?.mode === 'edit' && airportModal.branch) {
      await updateCommercialBranch(companyId, airportModal.branch.id, payload)
    } else {
      const created = await createCommercialBranch(companyId, { ...payload, country_id: savedCountry.id })
      setSelectedBranchId(created.id)
    }
    setAirportModal(null)
    await loadStructure()
  }

  const buttonStyle = {
    background: '#1d4ed8',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    padding: '10px 18px',
    fontWeight: 700,
    cursor: 'pointer',
    minWidth: '160px',
  }

  if (activeSub === 'commercial-structure') {
    return <CommercialOperationsView companyId={companyId} />
  }

  if (activeSub === 'overview-management') {
    return (
      <div className="panel-surface" style={{ padding: '16px 0', boxSizing: 'border-box' }}>
        <div style={{ padding: '0 8px', width: '100%' }}>
          <h3 style={{ margin: '0 0 18px', fontSize: '2rem', fontWeight: 700, color: '#e6edf8' }}>
            Commercial Structure
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '22px' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(180px, 240px) minmax(0, 1fr) minmax(0, 1fr) auto',
                gap: '18px',
                alignItems: 'end',
              }}
            >
              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Select Region</label>
                <select
                  value={selectedRegionName}
                  onChange={(event) => {
                    setSelectedRegionName(event.target.value)
                    setSelectedCountryCode('')
                    setSelectedBranchId('')
                  }}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                  }}
                >
                  <option value="">-- Select --</option>
                  {referenceRegions.map((regionName) => (
                    <option key={regionName} value={regionName}>
                      {regionName}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Regional Branch</label>
                <input
                  type="text"
                  value={form.regionManager}
                  onChange={(event) => handleInputChange('regionManager', event.target.value)}
                  placeholder="Enter branch name"
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Region Branch director</label>
                <input
                  type="text"
                  value={form.regionUser}
                  onChange={(event) => handleInputChange('regionUser', event.target.value)}
                  placeholder="Enter director name"
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                  }}
                />
              </div>

              <button type="button" style={buttonStyle} onClick={handleSaveRegion} disabled={!selectedRegionName.trim()}>
                {selectedRegion ? 'Edit Region Branch' : 'Add Regional Branch'}
              </button>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(180px, 240px) minmax(0, 1fr) minmax(0, 1fr) auto',
                gap: '18px',
                alignItems: 'end',
              }}
            >
              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Select Country</label>
                <select
                  value={selectedCountryCode}
                  onChange={(event) => {
                    setSelectedCountryCode(event.target.value)
                    setSelectedBranchId('')
                  }}
                  disabled={!selectedRegion}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                    opacity: selectedRegion ? 1 : 0.5,
                    cursor: selectedRegion ? 'auto' : 'not-allowed',
                  }}
                >
                  <option value="">-- Select --</option>
                  {filteredReferenceCountries.map((country) => (
                    <option key={country.country_code} value={country.country_code}>
                      {country.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Country Branch</label>
                <input
                  type="text"
                  value={form.countryManager}
                  onChange={(event) => handleInputChange('countryManager', event.target.value)}
                  placeholder="Enter branch name"
                  disabled={!selectedRegion}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                    opacity: selectedRegion ? 1 : 0.5,
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Country Branch director</label>
                <input
                  type="text"
                  value={form.countryUser}
                  onChange={(event) => handleInputChange('countryUser', event.target.value)}
                  placeholder="Enter director name"
                  disabled={!selectedRegion}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                    opacity: selectedRegion ? 1 : 0.5,
                  }}
                />
              </div>

              <button
                type="button"
                style={buttonStyle}
                onClick={handleSaveCountry}
                disabled={!selectedRegion || !form.countryName.trim()}
              >
                {savedCountry ? 'Edit Country Branch' : 'Add Country Branch'}
              </button>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(180px, 240px) minmax(0, 1fr) minmax(0, 1fr) auto',
                gap: '18px',
                alignItems: 'end',
              }}
            >
              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Local Branches</label>
                <select
                  value={selectedBranchId}
                  onChange={(event) => setSelectedBranchId(event.target.value)}
                  disabled={!savedCountry || branchesForCountry.length === 0}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                    opacity: savedCountry && branchesForCountry.length > 0 ? 1 : 0.5,
                    cursor: savedCountry && branchesForCountry.length > 0 ? 'auto' : 'not-allowed',
                  }}
                >
                  <option value="">
                    {branchesForCountry.length === 0 ? 'No local branches yet' : '-- Select --'}
                  </option>
                  {branchesForCountry.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name} {branch.airport ? `(${branch.airport})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Branch Manager</label>
                <input
                  type="text"
                  value={selectedBranch?.manager_name ?? ''}
                  readOnly
                  placeholder="Select a local branch"
                  disabled={!savedCountry}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                    opacity: savedCountry ? 1 : 0.5,
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Branch User</label>
                <input
                  type="text"
                  value={selectedBranch?.user_name ?? ''}
                  readOnly
                  placeholder="Select a local branch"
                  disabled={!savedCountry}
                  style={{
                    width: '100%',
                    background: '#111f31',
                    color: '#eaf3ff',
                    border: '1px solid #3b82f6',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '15px',
                    opacity: savedCountry ? 1 : 0.5,
                  }}
                />
              </div>

              <button
                type="button"
                style={buttonStyle}
                onClick={() => setAirportModal(selectedBranch ? { mode: 'edit', branch: selectedBranch } : { mode: 'create' })}
                disabled={!savedCountry}
              >
                {selectedBranch ? 'Edit Airport' : 'Add Airport'}
              </button>
            </div>
          </div>

          {airportModal && (
            <AddAirportModal
              mode={airportModal.mode}
              initialBranch={airportModal.mode === 'edit' ? airportModal.branch : null}
              countryName={savedCountry?.name ?? ''}
              onSave={handleSaveAirport}
              onCancel={() => setAirportModal(null)}
            />
          )}

          <div
            style={{
              border: '2px solid #3b82f6',
              borderRadius: '12px',
              background: '#1a2435',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                background: '#0f172a',
                borderBottom: '1px solid #3b82f6',
                padding: '14px 20px',
                fontSize: '2rem',
                fontWeight: 700,
                textAlign: 'center',
                color: '#eaf3ff',
              }}
            >
              Commercial Structure Overview
            </div>

            <div style={{ padding: '14px' }}>
              <CommercialStructureChart
                companyName={companyName}
                regions={regions}
                countries={countries}
                branches={branches}
                selectedRegionId={selectedRegion?.id}
                selectedCountryId={savedCountry?.id}
                selectedBranchId={selectedBranchId}
                onSelectNode={handleChartNodeSelect}
                onDeleteNode={handleChartNodeDelete}
              />
            </div>
          </div>
        </div>
      </div>
    )
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
