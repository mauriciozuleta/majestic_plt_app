import { Fragment, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createRevenueStream,
  createRevenueStreamRoute,
  deleteRevenueStreamRoute,
  fetchRevenueStreamRoutes,
  fetchRevenueStreams,
  saveRouteOutboundShipment,
  saveRouteReturnShipment,
  updateRevenueStreamRoute,
  updateRevenueStreamRouteSettings,
} from '../../../../services/revenueStreams'
import { fetchCommercialBranches, fetchMarketAnalysisRegions } from '../../../../services/commercialStructure'
import { fetchAircraftCatalogue, fetchCharterProviders } from '../../../../services/airLogistics'
import { useAppStore } from '../../../../store/useAppStore'
import AddRevenueStreamModal from './AddRevenueStreamModal'
import AddRouteModal from './AddRouteModal'
import ShipmentBuilderModal from './ShipmentBuilder/ShipmentBuilderModal'
import ShipmentPanel from './ShipmentBuilder/ShipmentPanel'
import RouteFinanceCells from './ShipmentBuilder/RouteFinanceCells'
import LegFinanceCards from './ShipmentBuilder/LegFinanceCards'
import { revenueProductFormFor } from './companyRevenueForms'
import { RETURN_TYPES, aircraftLabel, branchCode, branchLabel } from './branchLabel'
import { computeRouteMetrics } from './routeMetrics'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import { usePersistentSet } from '../../../../utils/usePersistentSet'
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
  const navigate = useNavigate()
  // Market Analysis countries by id, to open a leg's comparison in Market Opportunities
  const [countryNameById, setCountryNameById] = useState(() => new Map())
  useEffect(() => {
    let cancelled = false
    fetchMarketAnalysisRegions()
      .then((regions) => !cancelled && setCountryNameById(new Map(regions.flatMap((row) => row.countries.map((country) => [country.id, country.name])))))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])
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
  const [expandedRouteIds, setExpandedRouteIds] = usePersistentSet('revenue-routes:expanded')
  // { origin, destination } branches of the route whose Shipment builder is open
  const [shipmentBuilder, setShipmentBuilder] = useState(null)
  // `${routeId}:outbound` / `${routeId}:return` — legs whose built shipment is shown
  const [shownShipments, setShownShipments] = usePersistentSet('revenue-routes:shipments')
  const toggleShipment = (routeId) =>
    setShownShipments((prev) => {
      const next = new Set(prev)
      if (next.has(routeId)) next.delete(routeId)
      else next.add(routeId)
      return next
    })
  // `${routeId}:outbound` / `${routeId}:return` — legs whose Air Logistics Builder details (type of return,
  // distance, flight time, block hours…) are shown
  const [shownRoutes, setShownRoutes] = usePersistentSet('revenue-routes:route-details')
  const toggleRouteCards = (legKey) =>
    setShownRoutes((prev) => {
      const next = new Set(prev)
      if (next.has(legKey)) next.delete(legKey)
      else next.add(legKey)
      return next
    })
  // ids of the routes whose GSA terms card (the return leg's price) is open
  const [shownGsa, setShownGsa] = usePersistentSet('revenue-routes:gsa')
  const toggleGsa = (routeId) =>
    setShownGsa((prev) => {
      const next = new Set(prev)
      if (next.has(routeId)) next.delete(routeId)
      else next.add(routeId)
      return next
    })
  // Saves an edited shipment of one leg (a weight changed in Details ▸ Edit); throws the server's reason when it is refused.
  const handleSaveShipment = async (route, leg, shipment) => {
    const save = leg === 'return' ? saveRouteReturnShipment : saveRouteOutboundShipment
    const field = leg === 'return' ? 'return_shipment' : 'outbound_shipment'
    const updated = await save(companyId, route.stream_id, route.id, {
      capacity_kg: shipment.capacity_kg,
      aircraft_name: shipment.aircraft_name,
      items: shipment.items,
    })
    setRoutes((prev) => prev.map((item) => (item.id === updated.id ? { ...item, [field]: updated[field] } : item)))
  }
  const handleBuildShipment = async (shipment) => {
    const { route, leg } = shipmentBuilder
    const save = leg === 'return' ? saveRouteReturnShipment : saveRouteOutboundShipment
    const field = leg === 'return' ? 'return_shipment' : 'outbound_shipment'
    const updated = await save(companyId, route.stream_id, route.id, shipment)
    setRoutes((prev) => prev.map((item) => (item.id === updated.id ? { ...item, [field]: updated[field] } : item)))
    setShipmentBuilder(null)
    setShownShipments((prev) => new Set(prev).add(`${route.id}:${leg}`))
  }

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
            const routeShown = shownRoutes.has(legKey)
            const card = (label, value, extraClass = '') => (
              <div className={`revenue-streams-view__metric is-${leg.key} ${extraClass}`}>
                <span className="revenue-streams-view__metric-label">{label}</span>
                <span className="revenue-streams-view__metric-value">{value}</span>
              </div>
            )
            const detail = (label, value, title) => (
              <div className="revenue-streams-view__shipment-card" title={title}>
                <span className="revenue-streams-view__shipment-name">{label}</span>
                <span className="revenue-streams-view__shipment-kg">{value}</span>
              </div>
            )
            return (
              <Fragment key={leg.key}>
                <div
                  className={`revenue-streams-view__metric is-${leg.key} ${missing ? 'is-warn' : ''}`}
                  style={leg.key === 'return' ? { gridColumnStart: 1 } : undefined}
                  title={missing ?? undefined}
                >
                  <span className="revenue-streams-view__metric-label">
                    {leg.title}
                  </span>
                  <span className="revenue-streams-view__metric-value">{`${code(leg.from)} → ${code(leg.to)}`}</span>
                </div>
                <div className={`revenue-streams-view__metric is-${leg.key} revenue-streams-view__metric--filled revenue-streams-view__metric--air`}>
                  <span className="revenue-streams-view__metric-label">Air Logistics Builder</span>
                  <div className="revenue-streams-view__builder-actions">
                    <button
                      type="button"
                      className="revenue-streams-view__builder-btn"
                      onClick={() => toggleRouteCards(legKey)}
                      aria-expanded={routeShown}
                    >
                      {routeShown ? 'Hide route' : 'View route'}
                    </button>
                  </div>
                </div>
                {(() => {
                  const shipment = leg.key === 'outbound' ? route.outbound_shipment : route.return_shipment
                  const full = leg.key === 'return' && route.return_type === 'full'
                  // The return leg's shipment depends on the type of return chosen on the outbound leg.
                  if (leg.key === 'return' && !route.return_type) {
                    return card('Shipment builder', '—', 'revenue-streams-view__metric--filled')
                  }
                  return (
                    <div className={`revenue-streams-view__metric is-${leg.key} revenue-streams-view__metric--filled`}>
                      <span className="revenue-streams-view__metric-label">
                        Shipment builder
                        {(() => {
                          // payload still free: the aircraft's max payload minus what the built shipment carries
                          const free = shipment && capacityKg ? capacityKg - shipment.items.reduce((sum, item) => sum + item.kg, 0) : 0
                          return free >= 1 ? (
                            <button
                              type="button"
                              className="revenue-streams-view__pl-pill"
                              title={`${formatNumber(free, 0)} kg of the aircraft's ${formatNumber(capacityKg, 0)} kg max payload are still free — open this route's Market Opportunities`}
                              onClick={() => {
                                const params = new URLSearchParams({ tab: 'market-opportunities' })
                                const source = countryNameById.get(leg.from?.country_id)
                                const target = countryNameById.get(leg.to?.country_id)
                                if (source && target) {
                                  params.set('source', source)
                                  params.set('target', target)
                                }
                                navigate(`/market-analysis?${params.toString()}`)
                              }}
                            >
                              Available P/L
                            </button>
                          ) : null
                        })()}
                      </span>
                      <div className="revenue-streams-view__builder-actions">
                        {full ? (
                          <button type="button" className="revenue-streams-view__builder-btn" onClick={() => toggleGsa(route.id)} aria-expanded={shownGsa.has(route.id)}>
                            {shownGsa.has(route.id) ? 'Hide GSA terms' : route.return_price_per_kg != null || route.return_cos_per_kg != null ? 'Update GSA terms' : 'Add GSA terms'}
                          </button>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="revenue-streams-view__builder-btn"
                              onClick={() =>
                                setShipmentBuilder({
                                  route,
                                  leg: leg.key,
                                  origin: leg.from,
                                  destination: leg.to,
                                  capacityKg,
                                  airfarePerKg: priceFor(leg).value,
                                  aircraftName: aircraft ? aircraftLabel(aircraft) : route.aircraft_name,
                                })
                              }
                              disabled={!leg.from || !leg.to}
                            >
                              {shipment ? 'Update shipment' : 'Build shipment'}
                            </button>
                            {leg.key === 'return' && (
                              <button type="button" className="revenue-streams-view__builder-btn" onClick={() => toggleGsa(route.id)} aria-expanded={shownGsa.has(route.id)}>
                                {shownGsa.has(route.id) ? 'Hide COS' : route.return_cos_per_kg != null ? 'Update COS' : 'Add COS'}
                              </button>
                            )}
                            {shipment && (
                              <button
                                type="button"
                                className="revenue-streams-view__builder-btn"
                                onClick={() => toggleShipment(`${route.id}:${leg.key}`)}
                                aria-expanded={shownShipments.has(`${route.id}:${leg.key}`)}
                              >
                                {shownShipments.has(`${route.id}:${leg.key}`) ? 'Hide shipment' : 'View shipment'}
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  )
                })()}
                <LegFinanceCards
                  route={route}
                  legKey={leg.key}
                  branches={{ origin, destination, returnBranch, aircraft, provider }}
                />
                {leg.key === 'return' && route.return_type && shownGsa.has(route.id) && (
                  <div className="revenue-streams-view__shipment is-return">
                    <div className="revenue-streams-view__shipment-head">
                      <strong>{route.return_type === 'full' ? 'GSA terms' : 'Return terms'}</strong> ·{' '}
                      {route.return_type === 'full'
                        ? 'what the GSA pays per kg of the return cargo, and what it costs per kg'
                        : 'the return route’s price per kg, and what the cargo costs per kg'}
                    </div>
                    <div className="revenue-streams-view__shipment-cards">
                      {route.return_type === 'full' ? (
                        <div className="revenue-streams-view__shipment-card">
                          <span className="revenue-streams-view__shipment-name">GSA price x Kg</span>
                          <CardNumberInput
                            key={`${route.id}:return-price:${route.return_price_per_kg ?? ''}`}
                            value={route.return_price_per_kg}
                            label="GSA price per kg"
                            placeholder="0.00"
                            prefix="USD $"
                            onSave={(value) => handleRouteSettings(route, { return_price_per_kg: value })}
                          />
                        </div>
                      ) : (
                        detail('Return route price x Kg', priceFor(leg).value != null ? formatCurrencyValue(priceFor(leg).value, 'USD') : '—', priceFor(leg).note || undefined)
                      )}
                      <div className="revenue-streams-view__shipment-card">
                        <span className="revenue-streams-view__shipment-name">COS x Kg</span>
                        <CardNumberInput
                          key={`${route.id}:return-cos:${route.return_cos_per_kg ?? ''}`}
                          value={route.return_cos_per_kg}
                          label="COS per kg"
                          placeholder="0.00"
                          prefix="USD $"
                          onSave={(value) => handleRouteSettings(route, { return_cos_per_kg: value })}
                        />
                      </div>
                    </div>
                  </div>
                )}
                {routeShown && (
                  <div className={`revenue-streams-view__shipment is-${leg.key}`}>
                    <div className="revenue-streams-view__shipment-head">
                      <strong>{leg.title} route</strong> · {`${code(leg.from)} → ${code(leg.to)}`}
                    </div>
                    <div className="revenue-streams-view__shipment-cards">
                      <div className="revenue-streams-view__shipment-card">
                        <span className="revenue-streams-view__shipment-name">{leg.key === 'outbound' ? 'Type of return' : 'Type'}</span>
                        {leg.key === 'outbound' ? (
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
                        ) : (
                          <span className="revenue-streams-view__shipment-kg">{RETURN_LEG_TYPE_LABELS[route.return_type] ?? '—'}</span>
                        )}
                      </div>
                      {detail('Distance', metrics.distanceNm != null ? `${formatNumber(metrics.distanceNm)} nm` : '—')}
                      {detail('Flight time', metrics.flightTimeHours != null ? `${formatNumber(metrics.flightTimeHours)} h` : '—')}
                      {detail('Block hours', metrics.blockHours != null ? `${formatNumber(metrics.blockHours, 1)} h` : '—')}
                      {detail('Block hours cost', metrics.blockHoursCost != null ? formatCurrencyValue(metrics.blockHoursCost, 'USD') : '—')}
                      {route.return_type === 'full' ? (
                        detail('Leg cost %', `${legCostPct(leg)}%`, 'Full: the outbound leg assumes the whole flight')
                      ) : (
                        <div className="revenue-streams-view__shipment-card">
                          <span className="revenue-streams-view__shipment-name">Leg cost %</span>
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
                      {detail(
                        'Leg cost',
                        legCost(leg) != null ? formatCurrencyValue(legCost(leg), 'USD') : '—',
                        legCost(leg) != null
                          ? `${formatCurrencyValue(flightCost, 'USD')} flight cost (both legs) × ${formatNumber(legCostPct(leg), 1)}%`
                          : undefined,
                      )}
                      <div className="revenue-streams-view__shipment-card">
                        <span className="revenue-streams-view__shipment-name">Target Cargo %</span>
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
                      {detail(
                        'Available cargo',
                        legKg != null ? `${formatNumber(legKg, 0)} kg` : '—',
                        legKg != null ? `${formatNumber(route[leg.pctField], 1)}% × ${formatNumber(capacityKg, 0)} kg max payload` : undefined,
                      )}
                      {leg.key !== 'outbound' && route.return_type === 'full'
                        ? detail(
                            'Price x Kg',
                            route.return_price_per_kg != null ? formatCurrencyValue(route.return_price_per_kg, 'USD') : '—',
                            'Set with Add GSA terms in the Shipment builder',
                          )
                        : detail('Price x Kg', priceFor(leg).value != null ? formatCurrencyValue(priceFor(leg).value, 'USD') : '—', priceFor(leg).note)}
                    </div>
                  </div>
                )}
                {(leg.key === 'outbound' ? route.outbound_shipment : route.return_shipment) &&
                  shownShipments.has(`${route.id}:${leg.key}`) &&
                  (
                    <ShipmentPanel
                      shipment={leg.key === 'outbound' ? route.outbound_shipment : route.return_shipment}
                      legTitle={leg.title}
                      origin={leg.from}
                      destination={leg.to}
                      airfarePerKg={priceFor(leg).value}
                      airfareNote={priceFor(leg).note}
                      onSave={(next) => handleSaveShipment(route, leg.key, next)}
                    />
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

  // The air-cargo route form (and everything built on routes) is FRESH24's;
  // other companies get their own form once it's set up (companyRevenueForms.js).
  const hasRouteForm = revenueProductFormFor(companyId) === 'air-cargo-route'
  const openRouteForm = (stream) => hasRouteForm && setRouteModal({ stream, route: null })

  return (
    <div className="panel-surface revenue-streams-view">
      <h3>Revenue</h3>
      <p>
        {hasRouteForm
          ? 'Break revenue down by stream. Click a stream to add an origin and destination to it.'
          : "Break revenue down by stream. This company's product form hasn't been set up yet."}
      </p>
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
                  className={`revenue-streams-view__item ${hasRouteForm ? '' : 'is-static'}`}
                  role={hasRouteForm ? 'button' : undefined}
                  tabIndex={hasRouteForm ? 0 : undefined}
                  onClick={() => openRouteForm(stream)}
                  onKeyDown={(event) => {
                    if (hasRouteForm && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault()
                      openRouteForm(stream)
                    }
                  }}
                >
                  <span className="revenue-streams-view__item-type">{REVENUE_TYPE_LABELS[stream.revenue_type] ?? stream.revenue_type}</span>
                  <span className="revenue-streams-view__item-name">{stream.name}</span>
                  {hasRouteForm && (
                    <button type="button" className="revenue-streams-view__products-btn">
                      Add Products
                    </button>
                  )}
                </div>
                {hasRouteForm && streamRoutes.length > 0 && (
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
                        <th title="The suggested sale prices of every product of the route's built shipments">Shipment Revenue</th>
                        <th className="revenue-streams-view__money is-cos" title="What those products cost (DDP)">COS</th>
                        <th title="Revenue − COS, less the cost of the payload that flies empty">Profit</th>
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
                              <RouteFinanceCells
                                route={route}
                                origin={branchById.get(route.origin_branch_id)}
                                destination={branchById.get(route.destination_branch_id)}
                                returnBranch={route.return_branch_id ? branchById.get(route.return_branch_id) : null}
                                aircraft={aircraftById.get(route.aircraft_id)}
                                provider={providerById.get(route.charter_provider_id)}
                              />
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
                                <td colSpan={11}>{renderRouteDetails(route)}</td>
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
        <ShipmentBuilderModal
          origin={shipmentBuilder.origin}
          destination={shipmentBuilder.destination}
          capacityKg={shipmentBuilder.capacityKg}
          aircraftName={shipmentBuilder.aircraftName}
          airfarePerKg={shipmentBuilder.airfarePerKg}
          previous={shipmentBuilder.leg === 'return' ? shipmentBuilder.route.return_shipment : shipmentBuilder.route.outbound_shipment}
          onBuild={handleBuildShipment}
          onClose={() => setShipmentBuilder(null)}
        />
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
