import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchCommercialOperationEntries } from '../../services/commercialOperations'
import { fetchSimParameters } from '../../services/simParameters'
import { CATEGORIES } from '../company/tabs/OperationsTab/CommercialOperationsView/categories'
import './SimParametersView.css'

function SimParametersView() {
  const { companyId } = useParams()
  const [entries, setEntries] = useState([])
  const [simParameters, setSimParameters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [enabled, setEnabled] = useState({})

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    setError('')
    Promise.all([fetchCommercialOperationEntries(companyId), fetchSimParameters(companyId)])
      .then(([nextEntries, nextSimParameters]) => {
        setEntries(nextEntries)
        setSimParameters(nextSimParameters)
        setEnabled(Object.fromEntries(nextSimParameters.map((item) => [item.entry_id, true])))
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [companyId])

  const flaggedEntries = useMemo(() => {
    const flaggedIds = new Set(simParameters.map((item) => item.entry_id))
    return entries
      .filter((entry) => flaggedIds.has(entry.id))
      .sort((a, b) => a.entry_date.localeCompare(b.entry_date))
  }, [entries, simParameters])

  const toggleEnabled = (entryId) => {
    setEnabled((previous) => ({ ...previous, [entryId]: !previous[entryId] }))
  }

  if (loading) return <div className="sim-parameters__status">Loading sim parameters...</div>
  if (error) return <div className="sim-parameters__status sim-parameters__status--error">{error}</div>

  return (
    <div className="sim-parameters">
      <div className="sim-parameters__intro">
        <p>
          Values flagged as <strong>Sim Parameter</strong> from Commercial Operations show up here. Checked parameters
          will be the ones the simulation agent can adjust — wiring that up comes later.
        </p>
      </div>

      {flaggedEntries.length === 0 ? (
        <div className="sim-parameters__empty">
          No sim parameters yet. Check "Sim Parameter" when adding a revenue, COS, or expense entry in Commercial
          Operations to see it here.
        </div>
      ) : (
        <table className="sim-parameters__table">
          <thead>
            <tr>
              <th></th>
              <th>Date</th>
              <th>Category</th>
              <th>Description</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {flaggedEntries.map((entry) => {
              const categoryMeta = CATEGORIES.find((item) => item.key === entry.category)
              const label = entry.description || entry.entry_type || entry.client || '—'
              return (
                <tr key={entry.id}>
                  <td>
                    <input type="checkbox" checked={Boolean(enabled[entry.id])} onChange={() => toggleEnabled(entry.id)} />
                  </td>
                  <td>{entry.entry_date}</td>
                  <td>
                    <span className="sim-parameters__category" style={{ color: categoryMeta?.color }}>
                      {categoryMeta?.label ?? entry.category}
                    </span>
                  </td>
                  <td>{label}</td>
                  <td className="num">${entry.amount.toLocaleString()}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default SimParametersView
