import { useEffect, useMemo, useRef, useState } from 'react'
import { useAppStore } from '../../store/useAppStore'
import {
  createCommercialBranch,
  createCommercialCountry,
  createCommercialRegion,
  deleteCommercialBranch,
  deleteCommercialCountry,
  deleteCommercialRegion,
  fetchRegionAssignments,
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
  // "Same as regional manager": the region is assigned to the selected
  // company, so that company IS the regional manager - when it also handles
  // the country directly (e.g. FRESH24, based in Miami, running the US local
  // branches), the subsidiary is that same company and no second name has
  // to be typed in (stored in the same manager_name field).
  const [sameAsParent, setSameAsParent] = useState(false)
  // A region belongs to exactly one company - name -> owning company id, so
  // the dropdown can grey out regions another company already holds (the
  // backend enforces the same rule; this just keeps it from being offered).
  const [regionAssignments, setRegionAssignments] = useState([])
  const companies = useAppStore((state) => state.companies)
  const formRef = useRef(null)

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

  const loadRegionAssignments = () => fetchRegionAssignments().then(setRegionAssignments).catch(() => undefined)

  useEffect(() => {
    loadRegionAssignments()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId])

  const regionOwnerFor = (regionName) => {
    const assignment = regionAssignments.find((item) => item.name === regionName && item.company_id !== companyId)
    if (!assignment) return null
    return companies.find((company) => company.id === assignment.company_id)?.name ?? 'another company'
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
      setSelectedBranchId('')
      return
    }

    if (kind === 'country') {
      const region = regions.find((item) => item.id === record.region_id)
      if (region) setSelectedRegionName(region.name)
      setSelectedCountryCode(record.country_code || '')
      setSelectedBranchId('')
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

  // Edit icon on a node: select it (which loads its values into the form
  // above and scrolls there) - a branch opens its own edit dialog instead.
  const handleChartNodeEdit = (kind, record) => {
    handleChartNodeSelect(kind, record)
    if (kind === 'branch') {
      setAirportModal({ mode: 'edit', branch: record })
      return
    }
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleChartNodeDelete = async (kind, record) => {
    const confirmed = window.confirm(
      kind === 'region'
        ? `Delete region "${record.name}" and all of its countries and branches? This can't be undone.`
        : kind === 'country'
          ? `Delete "${record.name}" and all of its branches? This can't be undone.`
          : `Delete branch "${record.name}"? This can't be undone.`,
    )
    if (!confirmed) return

    try {
      if (kind === 'region') {
        await deleteCommercialRegion(companyId, record.id)
        if (record.id === selectedRegion?.id) {
          setSelectedRegionName('')
          setSelectedCountryCode('')
          setSelectedBranchId('')
        }
        await loadRegionAssignments()
      } else if (kind === 'country') {
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
    setSameAsParent(Boolean(savedCountry?.manager_name) && savedCountry.manager_name === companyName)
  }, [savedCountry, companyName])

  const handleSameAsParentChange = (checked) => {
    setSameAsParent(checked)
    setForm((previous) => ({ ...previous, countryManager: checked ? companyName || '' : '' }))
  }

  const handleSaveRegion = async () => {
    if (!companyId || !selectedRegionName.trim()) return

    try {
      if (selectedRegion) {
        await updateCommercialRegion(companyId, selectedRegion.id, {
          manager_name: selectedRegion.manager_name ?? null,
          user_name: form.regionUser || null,
        })
      } else {
        await createCommercialRegion(companyId, {
          name: selectedRegionName,
          user_name: form.regionUser || null,
        })
      }
      await Promise.all([loadStructure(), loadRegionAssignments()])
    } catch (error) {
      window.alert(error.message || 'Failed to save region')
    }
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
      // Stay on "-- Select --" after adding, so the button keeps reading
      // "Add Branch" for the next one instead of flipping to "Edit Branch".
      await createCommercialBranch(companyId, { ...payload, country_id: savedCountry.id })
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
        <div ref={formRef} style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '22px' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(180px, 240px) minmax(0, 1fr) auto',
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
                {referenceRegions.map((regionName) => {
                  const owner = regionOwnerFor(regionName)
                  return (
                    <option key={regionName} value={regionName} disabled={Boolean(owner)}>
                      {regionName}
                      {owner ? ` (assigned to ${owner})` : ''}
                    </option>
                  )
                })}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', color: '#cfe0f8', fontWeight: 600 }}>Region director</label>
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
              {selectedRegion ? 'Update region' : 'Assign region'}
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
              <div style={{ minHeight: '48px', marginBottom: '8px' }}><label style={{ display: 'block', color: '#cfe0f8', fontWeight: 600, whiteSpace: 'nowrap' }}>Activate country</label></div>
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
              <div style={{ minHeight: '48px', marginBottom: '8px' }}>
                <label style={{ display: 'block', color: '#cfe0f8', fontWeight: 600, whiteSpace: 'nowrap' }}>Country subsidiary</label>
                <label
                  title={companyName ? `${companyName} runs this region, so it also handles this country's local branches` : undefined}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    marginTop: '4px',
                    color: '#cfe0f8',
                    fontSize: '13px',
                    whiteSpace: 'nowrap',
                    cursor: selectedRegion ? 'pointer' : 'not-allowed',
                    opacity: selectedRegion ? 1 : 0.5,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={sameAsParent}
                    onChange={(event) => handleSameAsParentChange(event.target.checked)}
                    disabled={!selectedRegion}
                    style={{ margin: 0 }}
                  />
                  Same as regional manager
                </label>
              </div>
              <input
                type="text"
                value={form.countryManager}
                onChange={(event) => handleInputChange('countryManager', event.target.value)}
                placeholder="Enter subsidiary name"
                disabled={!selectedRegion || sameAsParent}
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
              <div style={{ minHeight: '48px', marginBottom: '8px' }}><label style={{ display: 'block', color: '#cfe0f8', fontWeight: 600, whiteSpace: 'nowrap' }}>Country subsidiary director</label></div>
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
              {savedCountry ? 'Update subsidiary' : 'Create subsidiary'}
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
              {selectedBranch ? 'Edit Branch' : 'Add Branch'}
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
              onEditNode={handleChartNodeEdit}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default CommercialStructureEditor
