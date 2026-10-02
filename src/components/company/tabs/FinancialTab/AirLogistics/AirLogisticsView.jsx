import { useEffect, useMemo, useState } from 'react'
import {
  deleteCharterProvider,
  fetchAircraftCatalogue,
  fetchCharterProviders,
  saveCharterProvider,
} from '../../../../../services/airLogistics'
import { fetchReferenceCountries } from '../../../../../services/commercialStructure'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import AircraftCatalogue from './AircraftCatalogue'
import { Link } from 'react-router-dom'
import CharterProviderModal from './CharterProviderModal'
import { PROVIDER_TYPES } from './providerTypes'
import './AirLogistics.css'

// Ported from AI_FRESH24's Administrator ▸ Logistics ▸ Air ▸ Mode: charter
// providers (each flying one aircraft from a main-base airport at a block-hour
// cost), plus the aircraft catalog they need.
function AirLogisticsView({ companyId, showAircraft = true, fleetPath }) {
  const [providers, setProviders] = useState([])
  const [aircraftList, setAircraftList] = useState([])
  const [countries, setCountries] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [selectedProviderId, setSelectedProviderId] = useState(null)
  const [providerModal, setProviderModal] = useState(null) // null | 'add' | provider

  const reload = async () => {
    const [nextProviders, nextAircraft] = await Promise.all([fetchCharterProviders(companyId), fetchAircraftCatalogue(companyId)])
    setProviders(nextProviders)
    setAircraftList(nextAircraft)
  }

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchCharterProviders(companyId), fetchAircraftCatalogue(companyId), fetchReferenceCountries().catch(() => [])])
      .then(([nextProviders, nextAircraft, nextCountries]) => {
        if (cancelled) return
        setProviders(nextProviders)
        setAircraftList(nextAircraft)
        setCountries([...nextCountries].sort((a, b) => a.name.localeCompare(b.name)))
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setStatus('error')
      })
    const refreshLinkedData = () => {
      Promise.all([fetchCharterProviders(companyId), fetchAircraftCatalogue(companyId)])
        .then(([nextProviders, nextAircraft]) => {
          if (cancelled) return
          setProviders(nextProviders)
          setAircraftList(nextAircraft)
          setError('')
          setStatus('ready')
        })
        .catch(err => { if (!cancelled) setError(err.message) })
    }
    const onVisible = () => { if (document.visibilityState === 'visible') refreshLinkedData() }
    window.addEventListener('focus', refreshLinkedData)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      window.removeEventListener('focus', refreshLinkedData)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [companyId])

  const aircraftById = useMemo(() => new Map(aircraftList.map((item) => [item.id, item])), [aircraftList])
  const typeLabel = (value) => PROVIDER_TYPES.find((type) => type.value === value)?.label ?? value

  const handleSaveProvider = async (payload) => {
    const saved = await saveCharterProvider(companyId, providerModal === 'add' ? null : providerModal.id, payload)
    setProviderModal(null)
    await reload()
    setSelectedProviderId(saved.id)
  }

  const handleDeleteProvider = async () => {
    const provider = providers.find((item) => item.id === selectedProviderId)
    if (!provider || !window.confirm(`Delete charter provider "${provider.name}"?`)) return
    setError('')
    try {
      await deleteCharterProvider(companyId, provider.id)
      setSelectedProviderId(null)
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  if (status === 'loading') return <p className="air-logistics__empty">Loading air logistics…</p>

  const selectedProvider = providers.find((item) => item.id === selectedProviderId)

  return (
    <div>
      {error && <div className="air-logistics__error">{error}</div>}
      {fleetPath && <p className="air-logistics__empty">Aircraft linked by default to <Link to={fleetPath}>Majestic Cargo · Fleet Management</Link> · {aircraftList.length} aircraft database records available.</p>}

      <section className="air-logistics__section">
        <h4>Charter Providers</h4>
        <p>Air charter operators available to move cargo. Select a row to edit or delete it.</p>
        <div className="air-logistics__table-wrap">
          <table className="air-logistics__table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Country</th>
                <th>Main Base</th>
                <th>Aircraft</th>
                <th className="num">Block Hour Cost</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider) => {
                const aircraft = aircraftById.get(provider.aircraft_id)
                return (
                  <tr
                    key={provider.id}
                    className={provider.id === selectedProviderId ? 'is-selected' : ''}
                    onClick={() => setSelectedProviderId(provider.id === selectedProviderId ? null : provider.id)}
                  >
                    <td>{provider.name}</td>
                    <td>{provider.country_name}</td>
                    <td title={provider.main_base_name || undefined}>
                      {provider.main_base_iata || 'Not set'}
                      {provider.main_base_city ? ` — ${provider.main_base_city}` : ''}
                    </td>
                    <td>{aircraft ? `${aircraft.short_name} (${aircraft.model})` : '—'}</td>
                    <td className="num">{provider.block_hour_cost == null ? 'Not set' : formatCurrencyValue(provider.block_hour_cost, 'USD')}</td>
                    <td>{typeLabel(provider.provider_type)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {providers.length === 0 && <div className="air-logistics__empty">No charter providers yet.</div>}
        </div>
        <div className="air-logistics__actions">
          <button
            type="button"
            className="air-logistics__btn air-logistics__btn--primary"
            onClick={() => setProviderModal('add')}
            disabled={aircraftList.length === 0}
            title={aircraftList.length === 0 ? 'Add an aircraft in the aircraft catalogue first — every provider flies one' : undefined}
          >
            Add Charter Provider
          </button>
          <button type="button" className="air-logistics__btn" onClick={() => setProviderModal(selectedProvider)} disabled={!selectedProvider}>
            Edit Selected
          </button>
          <button type="button" className="air-logistics__btn air-logistics__btn--danger" onClick={handleDeleteProvider} disabled={!selectedProvider}>
            Delete Selected
          </button>
        </div>
      </section>

      {showAircraft && <AircraftCatalogue key={companyId} companyId={companyId} onChanged={reload} />}

      {providerModal && (
        <CharterProviderModal
          provider={providerModal === 'add' ? null : providerModal}
          countries={countries}
          aircraftList={aircraftList}
          fleetLinked={!!fleetPath}
          onSave={handleSaveProvider}
          onCancel={() => setProviderModal(null)}
        />
      )}

    </div>
  )
}

export default AirLogisticsView
