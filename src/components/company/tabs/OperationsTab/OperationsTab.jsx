import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  fetchCommercialBranches,
  fetchCommercialCountries,
  fetchCommercialRegions,
  fetchReferenceCountries,
  fetchReferenceRegions,
} from '../../../../services/commercialStructure'

const emptyForm = {
  regionManager: '',
  regionUser: '',
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
  const [referenceCountries, setReferenceCountries] = useState([])
  const [selectedRegionName, setSelectedRegionName] = useState('')
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
  const [selectedBranchId, setSelectedBranchId] = useState('')
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

    if (nextRegions[0]) {
      setSelectedRegionName((previous) => previous || nextRegions[0].name)
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
      })
      .catch(() => setReferenceRegions(fallbackRegions))
  }, [])

  useEffect(() => {
    if (!selectedRegionName) {
      setReferenceCountries([])
      return
    }

    fetchReferenceCountries(selectedRegionName)
      .then((rows) => setReferenceCountries(Array.isArray(rows) ? rows : []))
      .catch(() => setReferenceCountries([]))
  }, [selectedRegionName])

  const selectedRegion = useMemo(
    () => regions.find((region) => region.name === selectedRegionName) ?? null,
    [regions, selectedRegionName],
  )

  const selectedCountry = useMemo(
    () => countries.find((country) => country.country_code === selectedCountryCode) ?? null,
    [countries, selectedCountryCode],
  )

  const filteredBranches = useMemo(() => {
    if (!selectedCountry) return []
    return branches.filter((branch) => branch.country_id === selectedCountry.id)
  }, [branches, selectedCountry])

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
    setForm({
      regionManager: selectedRegion?.manager_name ?? '',
      regionUser: selectedRegion?.user_name ?? '',
    })
  }, [selectedRegion])

  useEffect(() => {
    setSelectedCountryCode('')
  }, [selectedRegionName])

  useEffect(() => {
    setSelectedBranchId('')
  }, [selectedCountry])

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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
            <h3 style={{ margin: 0, fontSize: '2rem', fontWeight: 700, color: '#e6edf8' }}>
              Commercial Structure Management
            </h3>
            <button type="button" style={buttonStyle} onClick={() => {}}>
              Edit Structure Information
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '22px' }}>
            {/* Region Selection Row */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(180px, 240px) minmax(0, 1fr) minmax(0, 1fr)',
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
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Regional Manager</label>
                <input
                  type="text"
                  value={form.regionManager}
                  onChange={(event) => handleInputChange('regionManager', event.target.value)}
                  placeholder="Auto-populated from DB"
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
                  placeholder="Auto-populated from DB"
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
            </div>

            {/* Country Selection Row */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(180px, 240px) minmax(0, 1fr) minmax(0, 1fr)',
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
                  {referenceCountries.map((country) => (
                    <option key={country.country_code} value={country.country_code}>
                      {country.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Branches</label>
                <select
                  value={selectedBranchId}
                  onChange={(event) => setSelectedBranchId(event.target.value)}
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
                  {filteredBranches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name}
                    </option>
                  ))}
                </select>
              </div>

              <div />
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
