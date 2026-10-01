import { useEffect, useMemo, useState } from 'react'
import {
  deleteAircraft,
  deleteCharterProvider,
  fetchAircraft,
  fetchCharterProviders,
  saveAircraft,
  saveCharterProvider,
} from '../../../../../services/airLogistics'
import { fetchReferenceCountries } from '../../../../../services/commercialStructure'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import AircraftModal from './AircraftModal'
import CharterProviderModal from './CharterProviderModal'
import { PROVIDER_TYPES } from './providerTypes'
import './AirLogistics.css'

const formatNumber = (value, digits = 0) =>
  value == null ? '—' : Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })

// Ported from AI_FRESH24's Administrator ▸ Logistics ▸ Air ▸ Mode: charter
// providers (each flying one aircraft from a main-base airport at a block-hour
// cost), plus the aircraft catalog they need.
function AirLogisticsView({ companyId }) {
  const [providers, setProviders] = useState([])
  const [aircraftList, setAircraftList] = useState([])
  const [countries, setCountries] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [selectedProviderId, setSelectedProviderId] = useState(null)
  const [selectedAircraftId, setSelectedAircraftId] = useState(null)
  const [providerModal, setProviderModal] = useState(null) // null | 'add' | provider
  const [aircraftModal, setAircraftModal] = useState(null) // null | 'add' | aircraft

  const reload = async () => {
    const [nextProviders, nextAircraft] = await Promise.all([fetchCharterProviders(companyId), fetchAircraft(companyId)])
    setProviders(nextProviders)
    setAircraftList(nextAircraft)
  }

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchCharterProviders(companyId), fetchAircraft(companyId), fetchReferenceCountries().catch(() => [])])
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
    return () => {
      cancelled = true
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

  const handleSaveAircraft = async (payload) => {
    const saved = await saveAircraft(companyId, aircraftModal === 'add' ? null : aircraftModal.id, payload)
    setAircraftModal(null)
    await reload()
    setSelectedAircraftId(saved.id)
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

  const handleDeleteAircraft = async () => {
    const aircraft = aircraftById.get(selectedAircraftId)
    if (!aircraft || !window.confirm(`Delete aircraft "${aircraft.short_name}"?`)) return
    setError('')
    try {
      await deleteAircraft(companyId, aircraft.id)
      setSelectedAircraftId(null)
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  if (status === 'loading') return <p className="air-logistics__empty">Loading air logistics…</p>

  const selectedProvider = providers.find((item) => item.id === selectedProviderId)
  const selectedAircraft = aircraftById.get(selectedAircraftId)

  return (
    <div>
      {error && <div className="air-logistics__error">{error}</div>}

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
                      {provider.main_base_iata}
                      {provider.main_base_city ? ` — ${provider.main_base_city}` : ''}
                    </td>
                    <td>{aircraft ? `${aircraft.short_name} (${aircraft.model})` : '—'}</td>
                    <td className="num">{formatCurrencyValue(provider.block_hour_cost, 'USD')}</td>
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
            title={aircraftList.length === 0 ? 'Add an aircraft below first — every provider flies one' : undefined}
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

      <section className="air-logistics__section">
        <h4>Aircraft</h4>
        <p>Aircraft types the charter providers fly — weights in kg, fuel in US gallons.</p>
        <div className="air-logistics__table-wrap">
          <table className="air-logistics__table">
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>Manufacturer</th>
                <th className="num">MTOW (kg)</th>
                <th className="num">Max Payload (kg)</th>
                <th className="num">Fuel Burn (gal/h)</th>
                <th className="num">Positions (Main / Lower)</th>
                <th className="num">Cruise (kt)</th>
                <th className="num">Range @ Max Payload (nm)</th>
              </tr>
            </thead>
            <tbody>
              {aircraftList.map((item) => (
                <tr
                  key={item.id}
                  className={item.id === selectedAircraftId ? 'is-selected' : ''}
                  onClick={() => setSelectedAircraftId(item.id === selectedAircraftId ? null : item.id)}
                >
                  <td>
                    {item.short_name} ({item.model})
                  </td>
                  <td>{item.manufacturer}</td>
                  <td className="num">{formatNumber(item.mtow_kg)}</td>
                  <td className="num">{formatNumber(item.max_payload_kg)}</td>
                  <td className="num">{formatNumber(item.fuel_burn_gal_hr)}</td>
                  <td className="num">
                    {item.cargo_positions_main_deck} / {item.cargo_positions_lower_deck}
                  </td>
                  <td className="num">{formatNumber(item.cruise_speed_kt)}</td>
                  <td className="num">{formatNumber(item.max_range_at_max_payload_nm)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {aircraftList.length === 0 && <div className="air-logistics__empty">No aircraft yet — add one before creating a charter provider.</div>}
        </div>
        <div className="air-logistics__actions">
          <button type="button" className="air-logistics__btn air-logistics__btn--primary" onClick={() => setAircraftModal('add')}>
            Add Aircraft
          </button>
          <button type="button" className="air-logistics__btn" onClick={() => setAircraftModal(selectedAircraft)} disabled={!selectedAircraft}>
            Edit Selected
          </button>
          <button type="button" className="air-logistics__btn air-logistics__btn--danger" onClick={handleDeleteAircraft} disabled={!selectedAircraft}>
            Delete Selected
          </button>
        </div>
      </section>

      {providerModal && (
        <CharterProviderModal
          provider={providerModal === 'add' ? null : providerModal}
          countries={countries}
          aircraftList={aircraftList}
          onSave={handleSaveProvider}
          onCancel={() => setProviderModal(null)}
        />
      )}
      {aircraftModal && (
        <AircraftModal aircraft={aircraftModal === 'add' ? null : aircraftModal} onSave={handleSaveAircraft} onCancel={() => setAircraftModal(null)} />
      )}
    </div>
  )
}

export default AirLogisticsView
