import { useState } from 'react'

function AddOfficeModal({ onSave, onCancel }) {
  const [officeName, setOfficeName] = useState('')
  const [employeeName, setEmployeeName] = useState('')
  const [area, setArea] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()

    const trimmedOfficeName = officeName.trim()
    if (!trimmedOfficeName) {
      setError('Office name is required.')
      return
    }

    await onSave({
      officeName: trimmedOfficeName,
      employeeName: employeeName.trim(),
      area: area.trim(),
    })
  }

  return (
    <div className="org-chart-modal__overlay" onClick={onCancel}>
      <div className="org-chart-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Add office</h3>
        <form className="org-chart-modal__form" onSubmit={handleSubmit}>
          <label>
            Office name
            <input
              type="text"
              value={officeName}
              onChange={(event) => setOfficeName(event.target.value)}
              placeholder="Head of Finance"
            />
          </label>
          <label>
            Employee name (optional)
            <input
              type="text"
              value={employeeName}
              onChange={(event) => setEmployeeName(event.target.value)}
              placeholder="Maria Zuleta"
            />
          </label>
          <label>
            Area
            <input
              type="text"
              value={area}
              onChange={(event) => setArea(event.target.value)}
              placeholder="Finance"
            />
          </label>

          {error && <div className="org-chart-modal__error">{error}</div>}

          <div className="org-chart-modal__actions">
            <button type="button" className="org-chart-modal__cancel" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="org-chart-modal__save">
              Save office
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddOfficeModal
