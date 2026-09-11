import { useEffect, useMemo, useState } from 'react'
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
} from '../../services/commercialStructure'
import AddAirportModal from './AddAirportModal'
import CommercialStructureChart from './CommercialStructureChart/CommercialStructureChart'

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

// The regions/countries/branches editor + org chart, extracted out of the
// per-company Operations tab so it can be driven by whichever company a
// portfolio-level page picks (see CommercialStructureView), instead of
// always reading companyId from the route.
function CommercialStructureEditor({ companyId, companyName }) {
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
    setSelectedRegionName('')
    setSelectedCountryCode('')
    setSelectedBranchId('')
    loadStructure().catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  return (
    <div className="panel-surface" style={{ padding: '16px 0', boxSizing: 'border-box' }}>
      <div style={{ padding: '0 8px', width: '100%' }}>
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

export default CommercialStructureEditor
