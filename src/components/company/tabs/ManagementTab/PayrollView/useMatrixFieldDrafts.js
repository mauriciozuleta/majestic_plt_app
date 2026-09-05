import { useState } from 'react'
import { updateEmployee, updatePosition } from '../../../../../services/payroll'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'

/**
 * Owns "edit Reports To / Area / Yearly Comp in the Matrix grid, then Save"
 * — every field edit is staged locally (so the org chart isn't rebuilt from
 * a half-typed value) and only reaches the backend once, in a batch, when
 * the user clicks Save.
 */
export function useMatrixFieldDrafts({ companyId, selectedYear, reload }) {
  const [positionDrafts, setPositionDrafts] = useState(() => new Map())
  const [employeeDrafts, setEmployeeDrafts] = useState(() => new Map())
  const [saving, setSaving] = useState(false)

  const draftCount = positionDrafts.size + employeeDrafts.size

  const draftPositionField = (nodeId, field, value) => {
    setPositionDrafts((prev) => {
      const next = new Map(prev)
      next.set(nodeId, { ...next.get(nodeId), [field]: value })
      return next
    })
  }

  const draftEmployeeField = (employeeId, field, value) => {
    setEmployeeDrafts((prev) => {
      const next = new Map(prev)
      next.set(employeeId, { ...next.get(employeeId), [field]: value })
      return next
    })
  }

  const discardFieldDrafts = () => {
    setPositionDrafts(new Map())
    setEmployeeDrafts(new Map())
  }

  const saveFieldDrafts = async () => {
    setSaving(true)
    try {
      for (const [nodeId, updates] of positionDrafts.entries()) {
        // eslint-disable-next-line no-await-in-loop
        await updatePosition(nodeId, updates, selectedYear)
      }
      for (const [employeeId, updates] of employeeDrafts.entries()) {
        // eslint-disable-next-line no-await-in-loop
        await updateEmployee(employeeId, updates, selectedYear)
      }
      broadcastCompanyDataChange(companyId, 'payroll:save-matrix-fields')
      await reload()
      discardFieldDrafts()
    } finally {
      setSaving(false)
    }
  }

  return {
    positionDrafts,
    employeeDrafts,
    draftCount,
    savingFieldDrafts: saving,
    draftPositionField,
    draftEmployeeField,
    discardFieldDrafts,
    saveFieldDrafts,
  }
}
