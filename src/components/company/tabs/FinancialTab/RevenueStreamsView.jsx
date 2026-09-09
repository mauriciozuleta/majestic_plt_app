import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { createRevenueStream, fetchRevenueStreams } from '../../../../services/revenueStreams'
import AddRevenueStreamModal from './AddRevenueStreamModal'
import './RevenueStreamsView.css'

const REVENUE_TYPE_LABELS = { main: 'Main', secondary: 'Secondary' }

function RevenueStreamsView() {
  const { companyId } = useParams()
  const [streams, setStreams] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      setStreams(await fetchRevenueStreams(companyId))
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

  const handleSave = async (payload) => {
    await createRevenueStream(companyId, payload)
    setModalOpen(false)
    await reload()
  }

  return (
    <div className="panel-surface revenue-streams-view">
      <h3>Revenue/COS</h3>
      <p>Break revenue down by stream.</p>
      <button type="button" className="revenue-streams-view__add-btn" onClick={() => setModalOpen(true)}>
        + Add New Revenue Stream
      </button>

      {error && <div className="revenue-streams-view__error">{error}</div>}

      {!loading && streams.length > 0 && (
        <ul className="revenue-streams-view__list">
          {streams.map((stream) => (
            <li key={stream.id} className="revenue-streams-view__item">
              <span className="revenue-streams-view__item-type">{REVENUE_TYPE_LABELS[stream.revenue_type] ?? stream.revenue_type}</span>
              <span className="revenue-streams-view__item-name">{stream.name}</span>
              <button type="button" className="revenue-streams-view__products-btn">
                Add Products
              </button>
            </li>
          ))}
        </ul>
      )}

      {modalOpen && <AddRevenueStreamModal onSave={handleSave} onCancel={() => setModalOpen(false)} />}
    </div>
  )
}

export default RevenueStreamsView
