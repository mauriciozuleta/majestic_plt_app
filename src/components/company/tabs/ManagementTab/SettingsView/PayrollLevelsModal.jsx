import { useEffect, useState } from 'react'
import { fetchPayrollLevels, savePayrollLevels } from '../../../../../services/payrollLevels'
import './PayrollLevelsModal.css'

function blankRow() {
  return { level: '', yearly: '', percentage: '', monthly: '' }
}

function PayrollLevelsModal({ onClose }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('info')

  useEffect(() => {
    let cancelled = false
    fetchPayrollLevels()
      .then((levels) => {
        if (cancelled) return
        setRows(
          levels.map((level) => ({
            level: level.level,
            yearly: level.yearly,
            percentage: level.percentage ?? '',
            monthly: level.monthly ?? '',
          })),
        )
      })
      .catch((error) => {
        if (!cancelled) {
          setMessage(error.message)
          setMessageType('error')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const updateRow = (index, field, value) => {
    setRows((prev) => prev.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)))
  }

  const addRow = () => setRows((prev) => [...prev, blankRow()])

  const removeRow = (index) => setRows((prev) => prev.filter((_, rowIndex) => rowIndex !== index))

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    try {
      const cleaned = rows.filter((row) => row.level.trim() !== '')
      const saved = await savePayrollLevels(cleaned)
      setRows(
        saved.map((level) => ({
          level: level.level,
          yearly: level.yearly,
          percentage: level.percentage ?? '',
          monthly: level.monthly ?? '',
        })),
      )
      setMessage('Saved.')
      setMessageType('success')
    } catch (error) {
      setMessage(error.message || 'Failed to save payroll levels.')
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="payroll-levels-modal__overlay" onClick={onClose}>
      <div className="payroll-levels-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Edit payroll settings</h3>
        <p className="payroll-levels-modal__hint">
          These levels drive the "Level" dropdown in the Payroll Matrix — picking one there sets that position's yearly
          comp to the amount recorded here.
        </p>

        {loading ? (
          <div className="payroll-levels-modal__status">Loading...</div>
        ) : (
          <>
            <div className="payroll-levels-modal__table-scroll">
              <table className="payroll-levels-modal__table">
                <thead>
                  <tr>
                    <th>Level</th>
                    <th>Yearly</th>
                    <th>Percentage</th>
                    <th>Monthly</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index}>
                      <td>
                        <input
                          type="text"
                          value={row.level}
                          onChange={(event) => updateRow(index, 'level', event.target.value)}
                          placeholder="C1"
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          value={row.yearly}
                          onChange={(event) => updateRow(index, 'yearly', event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          value={row.percentage}
                          onChange={(event) => updateRow(index, 'percentage', event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          value={row.monthly}
                          onChange={(event) => updateRow(index, 'monthly', event.target.value)}
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="payroll-levels-modal__remove"
                          title="Remove this level"
                          onClick={() => removeRow(index)}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button type="button" className="payroll-levels-modal__add" onClick={addRow}>
              + Add level
            </button>
          </>
        )}

        {message && (
          <div className={`payroll-levels-modal__message payroll-levels-modal__message--${messageType}`}>{message}</div>
        )}

        <div className="payroll-levels-modal__actions">
          <button type="button" className="payroll-levels-modal__cancel" onClick={onClose}>
            Close
          </button>
          <button type="button" className="payroll-levels-modal__save" onClick={handleSave} disabled={saving || loading}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default PayrollLevelsModal
