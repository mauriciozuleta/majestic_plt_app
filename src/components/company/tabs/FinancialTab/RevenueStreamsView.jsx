import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createRevenueStream,
  createRevenueStreamRoute,
  fetchRevenueStreamRoutes,
  fetchRevenueStreams,
} from '../../../../services/revenueStreams'
import { fetchCommercialBranches } from '../../../../services/commercialStructure'
import { useAppStore } from '../../../../store/useAppStore'
import AddRevenueStreamModal from './AddRevenueStreamModal'
import AddRouteModal from './AddRouteModal'
import { branchLabel } from './branchLabel'
import './RevenueStreamsView.css'

const REVENUE_TYPE_LABELS = { main: 'Main', secondary: 'Secondary' }

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
  const [routeStream, setRouteStream] = useState(null)

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

  const branchById = useMemo(() => new Map(branches.map((branch) => [branch.id, branch])), [branches])

  const handleSave = async (payload) => {
    await createRevenueStream(companyId, payload)
    setModalOpen(false)
    await reload()
  }

  const handleSaveRoute = async (payload) => {
    const route = await createRevenueStreamRoute(companyId, routeStream.id, payload)
    setRoutes((prev) => [...prev, route])
    setRouteStream(null)
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
                  onClick={() => setRouteStream(stream)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setRouteStream(stream)
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
                        <th>#</th>
                        <th>Origin</th>
                        <th>Destination</th>
                      </tr>
                    </thead>
                    <tbody>
                      {streamRoutes.map((route, index) => (
                        <tr key={route.id}>
                          <td>{index + 1}</td>
                          <td>{describeBranch(route.origin_branch_id)}</td>
                          <td>{describeBranch(route.destination_branch_id)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {modalOpen && <AddRevenueStreamModal onSave={handleSave} onCancel={() => setModalOpen(false)} />}
      {routeStream && (
        <AddRouteModal streamName={routeStream.name} branches={branches} onSave={handleSaveRoute} onCancel={() => setRouteStream(null)} />
      )}
    </div>
  )
}

export default RevenueStreamsView
