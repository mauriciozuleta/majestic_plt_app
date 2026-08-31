import { useCallback, useEffect, useState } from 'react'
import { deleteOrgChartNode } from '../../../../../services/orgChart'
import {
  addEmployee,
  clonePosition,
  createPosition,
  deleteEmployee,
  fetchPayroll,
  updateEmployee,
  updatePosition,
} from '../../../../../services/payroll'
import { fetchSettings } from '../../../../../services/settings'
import { broadcastCompanyDataChange, subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'

export function usePayrollData(companyId) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [projectionYears, setProjectionYears] = useState(5)
  const [selectedYear, setSelectedYear] = useState(0)

  const reload = useCallback(async () => {
    if (!companyId) {
      setRows([])
      setLoading(false)
      setError('No company selected')
      return
    }

    setLoading(true)
    try {
      const [nextRows, settings] = await Promise.all([fetchPayroll(companyId, selectedYear), fetchSettings()])
      const nextProjectionYears = Math.max(5, Math.min(10, Number(settings.projection_years ?? 5)))
      setProjectionYears(nextProjectionYears)
      setSelectedYear((previousYear) => Math.max(0, Math.min(Number(previousYear ?? 0), nextProjectionYears)))
      setRows(nextRows)
      setError(null)
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setLoading(false)
    }
  }, [companyId, selectedYear])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => subscribeToCompanyDataChange(companyId, reload), [companyId, reload])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const handleFocus = () => reload()
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        reload()
      }
    }

    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [reload])

  const addPosition = useCallback(
    async (position) => {
      const created = await createPosition(companyId, position, selectedYear)
      broadcastCompanyDataChange(companyId, 'payroll:add-position')
      await reload()
      return created
    },
    [companyId, reload, selectedYear],
  )

  const savePosition = useCallback(async (nodeId, updates) => {
    await updatePosition(nodeId, updates, selectedYear)
    broadcastCompanyDataChange(companyId, 'payroll:update-position')
    await reload()
  }, [companyId, reload, selectedYear])

  const cloneSelected = useCallback(
    async (nodeIds) => {
      await Promise.all(nodeIds.map((nodeId) => clonePosition(nodeId)))
      broadcastCompanyDataChange(companyId, 'payroll:clone-position')
      await reload()
    },
    [companyId, reload],
  )

  const deleteSelected = useCallback(
    async (nodeIds) => {
      await Promise.all(nodeIds.map((nodeId) => deleteOrgChartNode(nodeId)))
      broadcastCompanyDataChange(companyId, 'payroll:delete-position')
      await reload()
    },
    [companyId, reload],
  )

  const addRosterEmployee = useCallback(
    async (nodeId, employee) => {
      await addEmployee(nodeId, employee, selectedYear)
      broadcastCompanyDataChange(companyId, 'payroll:add-employee')
      await reload()
    },
    [companyId, reload, selectedYear],
  )

  const saveRosterEmployee = useCallback(
    async (employeeId, updates) => {
      await updateEmployee(employeeId, updates, selectedYear)
      broadcastCompanyDataChange(companyId, 'payroll:update-employee')
      await reload()
    },
    [companyId, reload, selectedYear],
  )

  const removeRosterEmployee = useCallback(
    async (employeeId) => {
      await deleteEmployee(employeeId)
      broadcastCompanyDataChange(companyId, 'payroll:remove-employee')
      await reload()
    },
    [companyId, reload],
  )

  return {
    rows,
    loading,
    error,
    projectionYears,
    selectedYear,
    setSelectedYear,
    addPosition,
    savePosition,
    cloneSelected,
    deleteSelected,
    addRosterEmployee,
    saveRosterEmployee,
    removeRosterEmployee,
    reload,
  }
}