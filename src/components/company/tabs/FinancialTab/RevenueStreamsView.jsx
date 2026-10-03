import { Fragment, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createRevenueStream,
  createRevenueStreamRoute,
  deleteRevenueStreamRoute,
  fetchRevenueStreamRoutes,
  fetchRevenueStreams,
  updateRevenueStreamRoute,
  updateRevenueStreamRouteSettings,
} from '../../../../services/revenueStreams'
import { fetchCommercialBranches } from '../../../../services/commercialStructure'
import { fetchAircraftCatalogue, fetchCharterProviders } from '../../../../services/airLogistics'
import { useAppStore } from '../../../../store/useAppStore'
import AddRevenueStreamModal from './AddRevenueStreamModal'
import AddRouteModal from './AddRouteModal'
import ShipmentBuilderModal from './ShipmentBuilder/ShipmentBuilderModal'
import { RETURN_TYPES, aircraftLabel, branchCode, branchLabel } from './branchLabel'
import { computeRouteMetrics } from './routeMetrics'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import './RevenueStreamsView.css'

const REVENUE_TYPE_LABELS = { main: 'Main', secondary: 'Secondary' }

const formatNumber = (value, digits = 2) =>
  Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
// What the return leg is, given the type of return chosen on the outbound leg.
const RETURN_LEG_TYPE_LABELS = { full: 'GSA operated', compensated: 'Compensated' }

// Per-leg percentages: target cargo % and leg cost % (the share of the whole
// flight's cost the leg assumes).
const PCT_FIELDS = {
  target: { outbound: 'outbound_target_cargo_pct', return: 'return_target_cargo_pct' },
  cost: { outbound: 'outbound_leg_cost_pct', return: 'return_leg_cost_pct' },
}
const complementPct = (value) => (value == null ? null : Math.round((100 - value) * 1e6) / 1e6)
const otherLeg = (legKey) => (legKey === 'outbound' ? 'return' : 'outbound')

// The fields to save when one leg's percentage changes. With a compensated
// return the two legs' leg cost % add up to 100 %, so the other leg follows;
// target cargo % is set independently on each leg.
function pctChanges(route, kind, legKey, value, returnType = route.return_type) {
  const changes = { [PCT_FIELDS[kind][legKey]]: value }
  if (kind === 'cost' && returnType === 'compensated') changes[PCT_FIELDS.cost[otherLeg(legKey)]] = complementPct(value)
  return changes
}

// Switching to compensated: whichever leg has a leg cost % (outbound first)
// sets the other's.
function compensatedChanges(route) {
  const legKey = ['outbound', 'return'].find((key) => route[PCT_FIELDS.cost[key]] != null)
  return legKey ? pctChanges(route, 'cost', legKey, route[PCT_FIELDS.cost[legKey]], 'compensated') : {}
}

// A number saved when the field loses focus (or on Enter); empty clears it.
// Values outside min–max are not saved and the field is outlined in red.
function CardNumberInput({ value, label, min = 0, max = Infinity, placeholder, prefix, suffix, onSave }) {
  const [draft, setDraft] = useState(value ?? '')
  const [invalid, setInvalid] = useState(false)
  const commit = () => {
    const text = String(draft).trim()
    if (text === '') {
      setInvalid(false)
      if (value != null) onSave(null)
      return
    }
    const number = Number(text)
    if (!Number.isFinite(number) || number < min || number > max) {
      setInvalid(true)
      return
    }
    setInvalid(false)
    if (number !== value) onSave(number)
  }
  return (
    <span className="revenue-streams-view__pct">
      {prefix}
      <input
        type="number"
        min={min}
        max={Number.isFinite(max) ? max : undefined}
        step="any"
        inputMode="decimal"
        value={draft}
        placeholder={placeholder}
        aria-label={label}
        aria-invalid={invalid}
        title={invalid ? (Number.isFinite(max) ? `Enter a value between ${min} and ${max}` : `Enter a value of ${min} or more`) : undefined}
        className={invalid ? 'is-invalid' : ''}
        onChange={(event) => {
          setDraft(event.target.value)
          setInvalid(false)
        }}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
        }}
      />
      {suffix}
    </span>
  )
}

// Every active airport branch across all companies in the commercial
// structure — a route usually links branches owned by different companies
// (e.g. a Colombia company's airport to a Caribbean one).
async function fetchAllBranches(companies) {
  const lists = await Promise.all(
    companies.map((company) =>
      fetchCommercialBranches(company.id)
        .then((branches) => branches.map((branch) => ({ ...branch, companyName: company.name })))
        .catch(() => []),
    ),
  )
  return lists
    .flat()
    .filter((branch) => branch.active !== 'inactive')
    .sort((a, b) => (a.airport || a.name).localeCompare(b.airport || b.name))
}

function RevenueStreamsView() {
  const { companyId } = useParams()
  const companies = useAppStore((state) => state.companies)
  const [streams, setStreams] = useState([])
  const [routes, setRoutes] = useState([])
  const [branches, setBranches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  // { stream, route } — route is null when adding, the route being edited otherwise
  const [routeModal, setRouteModal] = useState(null)
  const [providers, setProviders] = useState([])
  const [aircraftCatalogue, setAircraftCatalogue] = useState([])
  const [expandedRouteIds, setExpandedRouteIds] = useState(new Set())
  // `${routeId}:outbound` / `${routeId}:return` — legs whose sub-cards are open
  const [expandedLegKeys, setExpandedLegKeys] = useState(new Set())
  // { origin, destination } branches of the route whose Shipment builder is open
  const [shipmentBuilder, setShipmentBuilder] = useState(null)

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const [nextStreams, nextRoutes] = await Promise.all([fetchRevenueStreams(companyId), fetchRevenueStreamRoutes(companyId)])
      setStreams(nextStreams)
      setRoutes(nextRoutes)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId])

  useEffect(() => {
    let cancelled = false
    fetchAllBranches(companies).then((list) => !cancelled && setBranches(list))
    return () => {
      cancelled = true
    }
  }, [companies])

  // Air logistics providers (Providers ▸ Air Logistics) and the full aircraft
  // catalogue — a provider's aircraft isn't necessarily in the selected fleet.
  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    Promise.all([fetchCharterProviders(companyId).catch(() => []), fetchAircraftCatalogue(companyId).catch(() => [])]).then(
      ([nextProviders, nextAircraft]) => {
        if (cancelled) return
        setProviders(nextProviders)
        setAircraftCatalogue(nextAircraft)
      },
    )
    return () => {
      cancelled = true
    }
  }, [companyId])

  const branchById = useMemo(() => new Map(branches.map((branch) => [branch.id, branch])), [branches])
  const aircraftById = useMemo(() => new Map(aircraftCatalogue.map((item) => [item.id, item])), [aircraftCatalogue])
  const providerById = useMemo(() => new Map(providers.map((item) => [item.id, item])), [providers])

  const handleSave = async (payload) => {
    await createRevenueStream(companyId, payload)
    setModalOpen(false)
    await reload()
  }

  const handleSaveRoute = async (payload) => {
    const { stream, route } = routeModal
    if (route) {
      const updated = await updateRevenueStreamRoute(companyId, stream.id, route.id, payload)
      setRoutes((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
    } else {
      const created = await createRevenueStreamRoute(companyId, stream.id, payload)
      setRoutes((prev) => [...prev, created])
    }
    setRouteModal(null)
  }

  const handleRouteSettings = async (route, changes) => {
    setError('')
    try {
      const updated = await updateRevenueStreamRouteSettings(companyId, route.stream_id, route.id, changes)
      // Only the fields this call changed: saves overlap (e.g. leaving one
      // field for another), and an older response mustn't undo a newer one.
      const saved = Object.fromEntries(Object.keys(changes).map((field) => [field, updated[field]]))
      setRoutes((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...saved } : item)))
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDeleteRoute = async (stream, route) => {
    const label = `${describeBranch(route.origin_branch_id)} → ${describeBranch(route.destination_branch_id)}`
    if (!window.confirm(`Delete this route?
${label}`)) return
    setError('')
    try {
      await deleteRevenueStreamRoute(companyId, stream.id, route.id)
      setRoutes((prev) => prev.filter((item) => item.id !== route.id))
    } catch (err) {
      setError(err.message)
    }
  }

  // Each leg — origin → destination, then destination → return — is
  // calculated on its own (see routeMetrics.js, ported from AI_FRESH24's
  // Routes module) and laid out as one row of cards in the leg's colour; the
  // columns line up across both rows and scroll sideways when there isn't
  // room. Each leg opens its own sub-row: Shipment distribution, Leg cost %,
  // Leg cost, Target Cargo %, Available cargo and Price x Kg.
  const renderRouteDetails = (route) => {
    const origin = branchById.get(route.origin_branch_id)
    const destination = branchById.get(route.destination_branch_id)
    const returnBranch = route.return_branch_id ? branchById.get(route.return_branch_id) : null
    const aircraft = aircraftById.get(route.aircraft_id)
    const provider = providerById.get(route.charter_provider_id)
    const code = (branch) => (branch ? branchCode(branch) : '—')
    const legs = [
      { key: 'outbound', title: 'Outbound', from: origin, to: destination, pctField: 'outbound_target_cargo_pct' },
      { key: 'return', title: 'Return', from: destination, to: returnBranch, pctField: 'return_target_cargo_pct' },
    ].map((leg) => ({ ...leg, metrics: computeRouteMetrics({ origin: leg.from, destination: leg.to, aircraft, provider }) }))
    // Available cargo = target cargo % × the aircraft's max payload.
    const capacityKg = aircraft?.max_payload_kg ?? null
    const availableKg = (leg) => {
      const pct = route[leg.pctField]
      return pct != null && capacityKg ? (pct / 100) * capacityKg : null
    }
    // Leg cost = the whole flight's cost (both legs) × the leg cost %; the
    // price per kg is the leg cost over the leg's available cargo.
    // - Full: the outbound leg assumes the whole flight (100 %); the return
    //   leg assumes none and its price per kg is entered by hand.
    // - Compensated: leg cost % is entered, and the two legs add up to 100 %.
    const [outboundLeg, returnLeg] = legs
    const flightCost =
      outboundLeg.metrics.blockHoursCost != null && returnLeg.metrics.blockHoursCost != null
        ? outboundLeg.metrics.blockHoursCost + returnLeg.metrics.blockHoursCost
        : null
    const legCostPct = (leg) => {
      if (route.return_type === 'full') return leg.key === 'outbound' ? 100 : 0
      return route[PCT_FIELDS.cost[leg.key]] ?? null
    }
    const legCost = (leg) => {
      const pct = legCostPct(leg)
      if (flightCost == null || pct == null) return null
      return (flightCost * pct) / 100
    }
    const priceFor = (leg) => {
      if (!route.return_type) return { value: null, note: 'Select the type of return' }
      if (flightCost == null) return { value: null, note: 'Needs both legs’ block hours cost' }
      const cost = legCost(leg)
      const kg = availableKg(leg)
      if (cost == null) return { value: null, note: `Enter the ${leg.title.toLowerCase()} leg cost %` }
      if (route[leg.pctField] == null) return { value: null, note: `Enter the ${leg.title.toLowerCase()} target cargo %` }
      if (!capacityKg) return { value: null, note: "Missing the aircraft's max payload" }
      if (!kg) return { value: null, note: 'No cargo on this leg' }
      return { value: cost / kg, note: `${formatCurrencyValue(cost, 'USD')} leg cost ÷ ${formatNumber(kg, 0)} kg` }
    }
    return (
      <div className="revenue-streams-view__details">
        <div className="revenue-streams-view__legs">
          {legs.map((leg) => {
            const { metrics } = leg
            const legKg = availableKg(leg)
            // Shown as the leg card's tooltip, with the card outlined in red.
            const missing =
              leg.key === 'return' && !route.return_branch_id
                ? 'Return airport not set — edit the route'
                : metrics.missing.length
                  ? `Missing ${metrics.missing.join(', ')}`
                  : null
            const legKey = `${route.id}:${leg.key}`
            const legOpen = expandedLegKeys.has(legKey)
            const card = (label, value, extraClass = '') => (
              <div className={`revenue-streams-view__metric is-${leg.key} ${extraClass}`}>
                <span className="revenue-streams-view__metric-label">{label}</span>
                <span className="revenue-streams-view__metric-value">{value}</span>
              </div>
            )
            return (
              <Fragment key={leg.key}>
                <div className={`revenue-streams-view__metric is-${leg.key} ${missing ? 'is-warn' : ''}`} title={missing ?? undefined}>
                  <span className="revenue-streams-view__metric-label">
                    <button
                      type="button"
                      className="revenue-streams-view__leg-toggle"
                      onClick={() => toggleLeg(legKey)}
                      aria-expanded={legOpen}
                      aria-label={legOpen ? `Hide ${leg.title.toLowerCase()} details` : `Show ${leg.title.toLowerCase()} details`}
                    >
                      {legOpen ? '▾' : '▸'}
                    </button>
                    {leg.title}
                  </span>
                  <span className="revenue-streams-view__metric-value">{`${code(leg.from)} → ${code(leg.to)}`}</span>
                </div>
                {leg.key === 'outbound' ? (
                  <div className="revenue-streams-view__metric is-outbound">
                    <span className="revenue-streams-view__metric-label">Type of return</span>
                    <select
                      className="revenue-streams-view__metric-select"
                      value={route.return_type ?? ''}
                      onChange={(event) => {
                        const returnType = event.target.value || null
                        // Switching to compensated links the two leg cost % (they add up to 100).
                        handleRouteSettings(route, { return_type: returnType, ...(returnType === 'compensated' ? compensatedChanges(route) : {}) })
                      }}
                      aria-label="Type of return"
                    >
                      <option value="">Select…</option>
                      {RETURN_TYPES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  card('Type', RETURN_LEG_TYPE_LABELS[route.return_type] ?? '—')
                )}
                {card('Distance', metrics.distanceNm != null ? `${formatNumber(metrics.distanceNm)} nm` : '—')}
                {card('Flight time', metrics.flightTimeHours != null ? `${formatNumber(metrics.flightTimeHours)} h` : '—')}
                {card('Block hours', metrics.blockHours != null ? `${formatNumber(metrics.blockHours, 1)} h` : '—')}
                {card('Block hours cost', metrics.blockHoursCost != null ? formatCurrencyValue(metrics.blockHoursCost, 'USD') : '—')}
                {legOpen && (
                  <>
                    {leg.key === 'outbound' ? (
                      <div className="revenue-streams-view__metric is-outbound revenue-streams-view__metric--filled">
                        <span className="revenue-streams-view__metric-label">Shipment builder</span>
                        <button
                          type="button"
                          className="revenue-streams-view__builder-btn"
                          onClick={() => setShipmentBuilder({ origin, destination })}
                          disabled={!origin || !destination}
                        >
                          Build shipment
                        </button>
                      </div>
                    ) : (
                      card('Shipment builder', '—', 'revenue-streams-view__metric--filled')
                    )}
                    {route.return_type === 'full' ? (
                      <div className={`revenue-streams-view__metric is-${leg.key}`} title="Full: the outbound leg assumes the whole flight">
                        <span className="revenue-streams-view__metric-label">Leg cost %</span>
                        <span className="revenue-streams-view__metric-value">{`${legCostPct(leg)}%`}</span>
                      </div>
                    ) : (
                      <div className={`revenue-streams-view__metric is-${leg.key}`}>
                        <span className="revenue-streams-view__metric-label">Leg cost %</span>
                        <CardNumberInput
                          key={`${route.id}:${leg.key}:cost:${route[PCT_FIELDS.cost[leg.key]] ?? ''}`}
                          value={route[PCT_FIELDS.cost[leg.key]]}
                          label={`${leg.title} leg cost %`}
                          max={100}
                          placeholder="0–100"
                          suffix="%"
                          onSave={(value) => handleRouteSettings(route, pctChanges(route, 'cost', leg.key, value))}
                        />
                      </div>
                    )}
                    <div
                      className={`revenue-streams-view__metric is-${leg.key}`}
                      title={
                        legCost(leg) != null
                          ? `${formatCurrencyValue(flightCost, 'USD')} flight cost (both legs) × ${formatNumber(legCostPct(leg), 1)}%`
                          : undefined
                      }
                    >
                      <span className="revenue-streams-view__metric-label">Leg cost</span>
                      <span className="revenue-streams-view__metric-value">{legCost(leg) != null ? formatCurrencyValue(legCost(leg), 'USD') : '—'}</span>
                    </div>
                    <div className={`revenue-streams-view__metric is-${leg.key}`}>
                      <span className="revenue-streams-view__metric-label">Target Cargo %</span>
                      <CardNumberInput
                        key={`${route.id}:${leg.key}:target:${route[leg.pctField] ?? ''}`}
                        value={route[leg.pctField]}
                        label={`${leg.title} target cargo %`}
                        max={100}
                        placeholder="0–100"
                        suffix="%"
                        onSave={(value) => handleRouteSettings(route, pctChanges(route, 'target', leg.key, value))}
                      />
                    </div>
                    <div
                      className={`revenue-streams-view__metric is-${leg.key}`}
                      title={legKg != null ? `${formatNumber(route[leg.pctField], 1)}% × ${formatNumber(capacityKg, 0)} kg max payload` : undefined}
                    >
                      <span className="revenue-streams-view__metric-label">Available cargo</span>
                      <span className="revenue-streams-view__metric-value">{legKg != null ? `${formatNumber(legKg, 0)} kg` : '—'}</span>
                    </div>
                    {leg.key === 'outbound' || route.return_type !== 'full' ? (
                      (() => {
                        const price = priceFor(leg)
                        return (
                          <div className={`revenue-streams-view__metric is-${leg.key}`} title={price.note}>
                            <span className="revenue-streams-view__metric-label">Price x Kg</span>
                            <span className="revenue-streams-view__metric-value">
                              {price.value != null ? formatCurrencyValue(price.value, 'USD') : '—'}
                            </span>
                          </div>
                        )
                      })()
                    ) : (
                      <div className="revenue-streams-view__metric is-return">
                        <span className="revenue-streams-view__metric-label">Price x Kg</span>
                        <CardNumberInput
                          key={`${route.id}:return-price:${route.return_price_per_kg ?? ''}`}
                          value={route.return_price_per_kg}
                          label="Return price per kg"
                          placeholder="0.00"
                          prefix="USD $"
                          onSave={(value) => handleRouteSettings(route, { return_price_per_kg: value })}
                        />
                      </div>
                    )}
                  </>
                )}
              </Fragment>
            )
          })}
        </div>
      </div>
    )
  }

  // Current names when the provider/aircraft still exist; the names saved
  // with the route otherwise.
  const describeProvider = (route) => providerById.get(route.charter_provider_id)?.name ?? route.provider_name ?? '—'
  const describeAircraft = (route) => aircraftLabel(aircraftById.get(route.aircraft_id)) ?? route.aircraft_name ?? '—'

  const toggleLeg = (legKey) =>
    setExpandedLegKeys((prev) => {
      const next = new Set(prev)
      if (next.has(legKey)) next.delete(legKey)
      else next.add(legKey)
      return next
    })

  const toggleRoute = (routeId) =>
    setExpandedRouteIds((prev) => {
      const next = new Set(prev)
      if (next.has(routeId)) next.delete(routeId)
      else next.add(routeId)
      return next
    })

  // The IATA code in the cell, the full airport/city/company in its tooltip.
  const branchCell = (id) => {
    const branch = branchById.get(id)
    if (!branch) return <span title="Branch no longer in the commercial structure">—</span>
    return (
      <span className="revenue-streams-view__code" title={branchLabel(branch)}>
        {branchCode(branch)}
      </span>
    )
  }

  const describeBranch = (id) => {
    const branch = branchById.get(id)
    return branch ? branchLabel(branch) : 'Branch no longer in the commercial structure'
  }

  return (
    <div className="panel-surface revenue-streams-view">
      <h3>Revenue</h3>
      <p>Break revenue down by stream. Click a stream to add an origin and destination to it.</p>
      <button type="button" className="revenue-streams-view__add-btn" onClick={() => setModalOpen(true)}>
        + Add New Revenue Stream
      </button>

      {error && <div className="revenue-streams-view__error">{error}</div>}

      {!loading && streams.length > 0 && (
        <ul className="revenue-streams-view__list">
          {streams.map((stream) => {
            const streamRoutes = routes.filter((route) => route.stream_id === stream.id)
            return (
              <li key={stream.id} className="revenue-streams-view__stream">
                <div
                  className="revenue-streams-view__item"
                  role="button"
                  tabIndex={0}
                  onClick={() => setRouteModal({ stream, route: null })}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setRouteModal({ stream, route: null })
                    }
                  }}
                >
                  <span className="revenue-streams-view__item-type">{REVENUE_TYPE_LABELS[stream.revenue_type] ?? stream.revenue_type}</span>
                  <span className="revenue-streams-view__item-name">{stream.name}</span>
                  <button type="button" className="revenue-streams-view__products-btn">
                    Add Products
                  </button>
                </div>
                {streamRoutes.length > 0 && (
                  <table className="revenue-streams-view__routes">
                    <thead>
                      <tr>
                        <th className="revenue-streams-view__toggle-col" aria-label="Details" />
                        <th>#</th>
                        <th>Origin</th>
                        <th>Destination</th>
                        <th>Return</th>
                        <th>Provider</th>
                        <th>Aircraft</th>
                        <th className="revenue-streams-view__actions-col" aria-label="Actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {streamRoutes.map((route, index) => {
                        const expanded = expandedRouteIds.has(route.id)
                        return (
                          <Fragment key={route.id}>
                            <tr className={expanded ? 'is-expanded' : ''}>
                              <td className="revenue-streams-view__toggle-col">
                                <button
                                  type="button"
                                  className="revenue-streams-view__toggle"
                                  onClick={() => toggleRoute(route.id)}
                                  aria-expanded={expanded}
                                  aria-label={expanded ? 'Hide calculations' : 'Show calculations'}
                                >
                                  {expanded ? '▾' : '▸'}
                                </button>
                              </td>
                              <td>{index + 1}</td>
                              <td>{branchCell(route.origin_branch_id)}</td>
                              <td>{branchCell(route.destination_branch_id)}</td>
                              <td>{route.return_branch_id ? branchCell(route.return_branch_id) : '—'}</td>
                              <td>{describeProvider(route)}</td>
                              <td>{describeAircraft(route)}</td>
                              <td className="revenue-streams-view__actions-col">
                                <button type="button" className="revenue-streams-view__row-btn" onClick={() => setRouteModal({ stream, route })}>
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="revenue-streams-view__row-btn revenue-streams-view__row-btn--danger"
                                  onClick={() => handleDeleteRoute(stream, route)}
                                >
                                  Delete
                                </button>
                              </td>
                            </tr>
                            {expanded && (
                              <tr className="revenue-streams-view__details-row">
                                <td colSpan={8}>{renderRouteDetails(route)}</td>
                              </tr>
                            )}
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {modalOpen && <AddRevenueStreamModal onSave={handleSave} onCancel={() => setModalOpen(false)} />}
      {shipmentBuilder && (
        <ShipmentBuilderModal origin={shipmentBuilder.origin} destination={shipmentBuilder.destination} onClose={() => setShipmentBuilder(null)} />
      )}
      {routeModal && (
        <AddRouteModal
          streamName={routeModal.stream.name}
          branches={branches}
          providers={providers}
          aircraftById={aircraftById}
          initialRoute={routeModal.route}
          onSave={handleSaveRoute}
          onCancel={() => setRouteModal(null)}
        />
      )}
    </div>
  )
}

export default RevenueStreamsView
