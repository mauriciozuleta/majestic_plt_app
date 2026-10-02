import { Fragment, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createRevenueStream,
  createRevenueStreamRoute,
  deleteRevenueStreamRoute,
  fetchRevenueStreamRoutes,
  fetchRevenueStreams,
  updateRevenueStreamRoute,
} from '../../../../services/revenueStreams'
import { fetchCommercialBranches } from '../../../../services/commercialStructure'
import { fetchAircraftCatalogue, fetchCharterProviders } from '../../../../services/airLogistics'
import { useAppStore } from '../../../../store/useAppStore'
import AddRevenueStreamModal from './AddRevenueStreamModal'
import AddRouteModal from './AddRouteModal'
import { RETURN_TYPES, aircraftLabel, branchCode, branchLabel } from './branchLabel'
import { computeRouteMetrics } from './routeMetrics'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import './RevenueStreamsView.css'

const REVENUE_TYPE_LABELS = { main: 'Main', secondary: 'Secondary' }

const formatNumber = (value, digits = 2) =>
  Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const formatHoursMinutes = (hours) => {
  const totalMinutes = Math.round(hours * 60)
  return `${Math.floor(totalMinutes / 60)} h ${String(totalMinutes % 60).padStart(2, '0')} min`
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
  // Routes module) and laid out as one row of cards; the columns line up
  // across both rows and scroll sideways when there isn't room.
  const renderRouteDetails = (route) => {
    const origin = branchById.get(route.origin_branch_id)
    const destination = branchById.get(route.destination_branch_id)
    const returnBranch = route.return_branch_id ? branchById.get(route.return_branch_id) : null
    const aircraft = aircraftById.get(route.aircraft_id)
    const provider = providerById.get(route.charter_provider_id)
    const returnLabel = RETURN_TYPES.find((item) => item.value === route.return_type)?.label ?? 'Not set'
    const code = (branch) => (branch ? branchCode(branch) : '—')
    const legs = [
      { key: 'outbound', title: 'Outbound', from: origin, to: destination, type: 'Outbound' },
      { key: 'return', title: 'Return', from: destination, to: returnBranch, type: returnLabel },
    ]
    const card = (label, value, note, tone) => (
      <div className="revenue-streams-view__metric">
        <span className="revenue-streams-view__metric-label">{label}</span>
        <span className="revenue-streams-view__metric-value">{value}</span>
        {note && <span className={`revenue-streams-view__metric-note ${tone === 'warn' ? 'is-warn' : ''}`}>{note}</span>}
      </div>
    )
    return (
      <div className="revenue-streams-view__details">
        <div className="revenue-streams-view__legs">
          {legs.map((leg) => {
            const metrics = computeRouteMetrics({ origin: leg.from, destination: leg.to, aircraft, provider })
            const missing =
              leg.key === 'return' && !route.return_branch_id
                ? 'Return airport not set — edit the route'
                : metrics.missing.length
                  ? `Missing ${metrics.missing.join(', ')}`
                  : null
            return (
              <Fragment key={leg.key}>
                {card(leg.title, `${code(leg.from)} → ${code(leg.to)}`, missing, 'warn')}
                {card(leg.key === 'return' ? 'Type of return' : 'Type', leg.type)}
                {card('Distance', metrics.distanceNm != null ? `${formatNumber(metrics.distanceNm)} nm` : '—', 'Great-circle (Haversine)')}
                {card(
                  'Flight time',
                  metrics.flightTimeHours != null ? `${formatNumber(metrics.flightTimeHours)} h` : '—',
                  metrics.flightTimeHours != null
                    ? `${formatHoursMinutes(metrics.flightTimeHours)} at ${formatNumber(metrics.cruiseSpeedKt, 0)} kt`
                    : null,
                )}
                {card(
                  'Block hours',
                  metrics.blockHours != null ? `${formatNumber(metrics.blockHours, 1)} h` : '—',
                  'Flight time rounded up to the next half hour',
                )}
                {card(
                  'Block hours cost',
                  metrics.blockHoursCost != null ? formatCurrencyValue(metrics.blockHoursCost, 'USD') : '—',
                  metrics.blockHoursCost != null
                    ? `${formatNumber(metrics.blockHours, 1)} h × ${formatCurrencyValue(metrics.blockHourCost, 'USD')}/h`
                    : null,
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
                                <td colSpan={7}>{renderRouteDetails(route)}</td>
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
