import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createCommercialCountry,
  createCommercialRegion,
  fetchCommercialBranches,
  fetchCommercialCountries,
  fetchCommercialRegions,
  fetchReferenceCountries,
  fetchReferenceRegions,
} from '../../../../services/commercialStructure'

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
  const [regions, setRegions] = useState([])
  const [countries, setCountries] = useState([])
  const [branches, setBranches] = useState([])
  const [referenceRegions, setReferenceRegions] = useState([])
  const [allReferenceCountries, setAllReferenceCountries] = useState([])
  const [selectedRegionName, setSelectedRegionName] = useState('')
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
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

  const overviewRows = useMemo(() => {
    return branches.map((branch) => {
      const country = countries.find((item) => item.id === branch.country_id)
      const region = regions.find((item) => item.id === country?.region_id)
      return {
        region: region?.name ?? '—',
        regionalManager: region?.manager_name ?? '—',
        regionUser: region?.user_name ?? '—',
        country: country?.name ?? '—',
        countryCode: country?.country_code ?? '—',
        currency: country?.currency_code ?? country?.currency ?? '—',
        countryManager: country?.manager_name ?? '—',
        countryUser: country?.user_name ?? '—',
        airport: branch.airport ?? '—',
        branch: branch.name,
        branchManager: branch.manager_name ?? '—',
        branchUser: branch.user_name ?? '—',
      }
    })
  }, [branches, countries, regions])

  useEffect(() => {
    if (!selectedRegion) return
    setForm((previous) => ({
      ...previous,
      regionName: selectedRegion.name,
      regionManager: selectedRegion.manager_name ?? '',
      regionUser: selectedRegion.user_name ?? '',
    }))
  }, [selectedRegion])

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

  const handleCreateRegion = async () => {
    if (!companyId || !selectedRegionName.trim()) return
    await createCommercialRegion(companyId, {
      name: selectedRegionName,
      manager_name: form.regionManager || null,
      user_name: form.regionUser || null,
    })
    await loadStructure()
  }

  const handleCreateCountry = async () => {
    if (!companyId || !selectedRegionName || !form.countryName.trim()) return

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
    return (
      <div className="panel-surface" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <h3>Operations</h3>
        <p>Operational plan, service delivery, and execution status.</p>
        <button type="button" className="payroll-view__btn payroll-view__btn--primary">
          Add branch
        </button>
      </div>
    )
  }

  if (activeSub === 'overview-management') {
    return (
      <div className="panel-surface" style={{ padding: '16px 0', boxSizing: 'border-box' }}>
        <div style={{ padding: '0 8px', width: '100%' }}>
          <h3 style={{ margin: '0 0 18px', fontSize: '2rem', fontWeight: 700, color: '#e6edf8' }}>
            Commercial Structure Management
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Regional Manager</label>
                <input
                  type="text"
                  value={form.regionManager}
                  onChange={(event) => handleInputChange('regionManager', event.target.value)}
                  placeholder="Enter manager name"
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Region User</label>
                <input
                  type="text"
                  value={form.regionUser}
                  onChange={(event) => handleInputChange('regionUser', event.target.value)}
                  placeholder="Enter user name"
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

              <button type="button" style={buttonStyle} onClick={handleCreateRegion}>
                Edit Region
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
                  onChange={(event) => setSelectedCountryCode(event.target.value)}
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
                  {filteredReferenceCountries.map((country) => (
                    <option key={country.country_code} value={country.country_code}>
                      {country.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Country Manager</label>
                <input
                  type="text"
                  value={form.countryManager}
                  onChange={(event) => handleInputChange('countryManager', event.target.value)}
                  placeholder="Enter country manager name"
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Country User</label>
                <input
                  type="text"
                  value={form.countryUser}
                  onChange={(event) => handleInputChange('countryUser', event.target.value)}
                  placeholder="Enter country user name"
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

              <button type="button" style={buttonStyle} onClick={handleCreateCountry}>
                Add Country
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Country Code / Currency</label>
                <input
                  type="text"
                  value={form.countryCode && form.currencyCode ? `${form.countryCode} / ${form.currencyCode}` : ''}
                  readOnly
                  placeholder="Auto from selected country"
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Branch Manager</label>
                <input
                  type="text"
                  value={form.branchManager}
                  onChange={(event) => handleInputChange('branchManager', event.target.value)}
                  placeholder="Enter branch manager name"
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Branch User</label>
                <input
                  type="text"
                  value={form.branchUser}
                  onChange={(event) => handleInputChange('branchUser', event.target.value)}
                  placeholder="Enter branch user name"
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

              <button type="button" style={buttonStyle} onClick={handleCreateRegion}>
                Region Core Data
              </button>
            </div>
          </div>

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

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1000px' }}>
                <thead>
                  <tr style={{ background: '#2d425d' }}>
                    {['Region', 'Regional Manager', 'Region User', 'Country', 'Country Code', 'Currency', 'Country Manager', 'Country User', 'Airport', 'Branch', 'Branch Manager', 'Branch User'].map((header) => (
                      <th key={header} style={{ border: '1px solid rgba(148,163,184,0.25)', padding: '12px 10px', textAlign: 'left', color: '#eaf3ff', fontWeight: 700 }}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {overviewRows.length === 0 ? (
                    <tr>
                      <td colSpan={12} style={{ padding: '18px', color: '#cfe0f8', textAlign: 'center' }}>
                        No commercial structure data yet.
                      </td>
                    </tr>
                  ) : (
                    overviewRows.map((row, index) => (
                      <tr key={`${row.region}-${row.country}-${row.branch}-${index}`} style={{ background: index % 2 === 0 ? '#1f2d3d' : '#1a2435' }}>
                        {[
                          row.region,
                          row.regionalManager,
                          row.regionUser,
                          row.country,
                          row.countryCode,
                          row.currency,
                          row.countryManager,
                          row.countryUser,
                          row.airport,
                          row.branch,
                          row.branchManager,
                          row.branchUser,
                        ].map((cell, cellIndex) => (
                          <td key={`${index}-${cellIndex}`} style={{ border: '1px solid rgba(148,163,184,0.25)', padding: '12px 10px', color: '#dbeafe', verticalAlign: 'top' }}>
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="panel-surface">
      <h3>Operations</h3>
      <p>Market analysis insights and local demand review.</p>
    </div>
  )
}

export default OperationsTab
