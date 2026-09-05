import { useState } from 'react'
import { addEmployee, updateEmployee } from '../../../../../services/payroll'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'
import { simDateToIsoDate } from '../../../../shared/SimulationCalendar/simulationCalendarMath'
import { reconcileHeadcount } from './reconcileHeadcount'

/**
 * Owns the "edit the 12-month headcount curve, then Save" workflow for the
 * Matrix view: staged per-position drafts, and turning a saved draft into
 * concrete employee add/end operations via reconcileHeadcount.
 */
export function useHeadcountDrafts({ companyId, rows, selectedYear, calendarMode, reload }) {
  const [headcountDrafts, setHeadcountDrafts] = useState(() => new Map())
  const [savingHeadcount, setSavingHeadcount] = useState(false)

  const dateForMonth = (month) => {
    if (month <= 0) month = 1
    if (calendarMode === 'simulation') {
      return simDateToIsoDate({ year: selectedYear, month, day: 1 })
    }
    const realYear = new Date().getFullYear()
    return `${realYear}-${String(month).padStart(2, '0')}-01`
  }

  const handleDraftMonthChange = (nodeId, monthIndex, value, currentMonths) => {
    setHeadcountDrafts((prev) => {
      const next = new Map(prev)
      const base = next.get(nodeId) || [...currentMonths]
      next.set(nodeId, base.map((existing, index) => (index >= monthIndex ? value : existing)))
      return next
    })
  }

  const handleDiscardHeadcountDrafts = () => setHeadcountDrafts(new Map())

  const handleSaveHeadcountDrafts = async () => {
    setSavingHeadcount(true)
    try {
      for (const [nodeId, targetMonths] of headcountDrafts.entries()) {
        const row = rows.find((candidate) => candidate.node_id === nodeId)
        if (!row) continue

        const plan = reconcileHeadcount(row.employees, targetMonths, selectedYear, calendarMode)
        const knownIds = new Set((row.employees || []).map((employee) => employee.id))

        for (const end of plan.ends) {
          if (end.endMonth === 0) {
            // eslint-disable-next-line no-await-in-loop
            await updateEmployee(end.employeeId, { end_projection_year: selectedYear - 1 }, selectedYear)
          } else {
            // eslint-disable-next-line no-await-in-loop
            await updateEmployee(
              end.employeeId,
              { end_date: dateForMonth(end.endMonth), end_projection_year: selectedYear },
              selectedYear,
            )
          }
        }

        for (const add of plan.adds) {
          // eslint-disable-next-line no-await-in-loop
          const created = await addEmployee(
            nodeId,
            { employee_name: null, start_date: dateForMonth(add.startMonth) },
            selectedYear,
          )
          const newEmployee = (created.employees || []).find((employee) => !knownIds.has(employee.id))
          if (newEmployee) {
            knownIds.add(newEmployee.id)
            if (add.endMonth != null) {
              // eslint-disable-next-line no-await-in-loop
              await updateEmployee(
                newEmployee.id,
                { end_date: dateForMonth(add.endMonth), end_projection_year: selectedYear },
                selectedYear,
              )
            }
          }
        }
      }

      broadcastCompanyDataChange(companyId, 'payroll:reconcile-headcount')
      await reload()
      setHeadcountDrafts(new Map())
    } finally {
      setSavingHeadcount(false)
    }
  }

  return {
    headcountDrafts,
    savingHeadcount,
    handleDraftMonthChange,
    handleDiscardHeadcountDrafts,
    handleSaveHeadcountDrafts,
  }
}
