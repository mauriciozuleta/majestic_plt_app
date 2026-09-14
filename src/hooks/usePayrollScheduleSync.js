import { useEffect, useRef } from 'react'
import { subscribeToCompanyDataChange } from '../services/companyDataSync'
import { runPayrollScheduleSync } from '../components/company/tabs/ManagementTab/PayrollView/payrollScheduleSync'

const DEBOUNCE_MS = 800

// Mounted once per company (in CompanyWorkspace, which wraps every tab for
// that company) so Settings > Payroll Schedule's "Automatic schedule" stays
// in sync with whatever payroll data currently says, no matter which tab
// the change actually happened in — this app has no other write path into
// payroll data, so a frontend-mounted listener covers every real case
// despite there being no backend job runner.
export function usePayrollScheduleSync(companyId) {
  const timeoutRef = useRef(null)

  useEffect(() => {
    if (!companyId) return undefined

    const runSync = () => {
      runPayrollScheduleSync(companyId).catch(() => undefined)
    }

    const scheduleSync = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(runSync, DEBOUNCE_MS)
    }

    scheduleSync()
    const unsubscribe = subscribeToCompanyDataChange(companyId, scheduleSync)

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      unsubscribe()
    }
  }, [companyId])
}
