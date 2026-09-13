import { useEffect, useState } from 'react'
import { fetchSettings, updatePayrollSchedule } from '../../../../../services/settings'
import './PayrollSchedulePanel.css'

const DAYS_1_TO_30 = Array.from({ length: 30 }, (_, index) => index + 1)

const TAX_OBLIGATIONS_OPTIONS = [
  { value: 'next_business_day', label: 'Next Business Day' },
  { value: '2', label: '2 days after' },
  { value: '3', label: '3 days after' },
  { value: '4', label: '4 days after' },
  { value: '5', label: '5 days after' },
  { value: '6', label: '6 days after' },
  { value: '7', label: '7 days after' },
  { value: 'end_of_month', label: 'End of the month' },
]

// When positions get paid — monthly (12 checks/year) or biweekly (24) — and
// when tax/other obligations get remitted. This is portfolio-wide, not
// specific to United States tax rates, which is why it's split out from
// "Payroll taxes/charges" into its own pill; the Payroll Statement view
// reads `payroll_schedule_type` to decide how many pay-period columns to
// show.
function PayrollSchedulePanel({ calendarMode = 'real' }) {
  const [scheduleType, setScheduleType] = useState('')
  const [monthlyDay, setMonthlyDay] = useState(1)
  const [biweeklyDay1, setBiweeklyDay1] = useState(1)
  const [biweeklyDay2, setBiweeklyDay2] = useState(15)
  const [taxObligationsSchedule, setTaxObligationsSchedule] = useState('')
  const [scheduleStatus, setScheduleStatus] = useState('loading')
  const [scheduleMessage, setScheduleMessage] = useState('')
  const [scheduleDirty, setScheduleDirty] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setScheduleType(settings.payroll_schedule_type || '')
        setMonthlyDay(settings.payroll_schedule_monthly_day || 1)
        setBiweeklyDay1(settings.payroll_schedule_biweekly_day1 || 1)
        setBiweeklyDay2(settings.payroll_schedule_biweekly_day2 || 15)
        setTaxObligationsSchedule(settings.tax_obligations_schedule || '')
        setScheduleStatus('idle')
      })
      .catch((error) => {
        if (!cancelled) {
          setScheduleStatus('error')
          setScheduleMessage(error.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const markDirty = (setter) => (value) => {
    setter(value)
    setScheduleDirty(true)
  }

  const handleSaveSchedule = async () => {
    setScheduleStatus('saving')
    setScheduleMessage('')
    try {
      await updatePayrollSchedule({
        payroll_schedule_type: scheduleType || null,
        payroll_schedule_monthly_day: scheduleType === 'monthly' ? monthlyDay : null,
        payroll_schedule_biweekly_day1: scheduleType === 'biweekly' ? biweeklyDay1 : null,
        payroll_schedule_biweekly_day2: scheduleType === 'biweekly' ? biweeklyDay2 : null,
        tax_obligations_schedule: taxObligationsSchedule || null,
      })
      setScheduleDirty(false)
      setScheduleStatus('idle')
      setScheduleMessage('Saved.')
    } catch (error) {
      setScheduleStatus('error')
      setScheduleMessage(error.message || 'Failed to save the schedule.')
    }
  }

  return (
    <div className="payroll-schedule-panel">
      <p className="payroll-schedule-panel__hint">
        Drives how many pay-period columns the Payroll &gt; Payroll Statement view shows (12 for monthly, 24 for biweekly).
      </p>

      <div className="payroll-schedule-panel__schedule-type">
        <label>
          <input
            type="radio"
            name="payroll-schedule-type"
            value="monthly"
            checked={scheduleType === 'monthly'}
            onChange={() => markDirty(setScheduleType)('monthly')}
          />
          Monthly
        </label>
        <label>
          <input
            type="radio"
            name="payroll-schedule-type"
            value="biweekly"
            checked={scheduleType === 'biweekly'}
            onChange={() => markDirty(setScheduleType)('biweekly')}
          />
          Biweekly
        </label>
      </div>

      {scheduleType === 'monthly' &&
        (calendarMode === 'simulation' ? (
          <label className="payroll-schedule-panel__schedule-day">
            Day of month for pay
            <select value={monthlyDay} onChange={(event) => markDirty(setMonthlyDay)(Number(event.target.value))}>
              {DAYS_1_TO_30.map((day) => (
                <option key={day} value={day}>
                  {day}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="payroll-schedule-panel__hint">Day-of-month selection is available in Simulation calendar mode.</p>
        ))}

      {scheduleType === 'biweekly' &&
        (calendarMode === 'simulation' ? (
          <div className="payroll-schedule-panel__schedule-day-pair">
            <label className="payroll-schedule-panel__schedule-day">
              First payment day
              <select value={biweeklyDay1} onChange={(event) => markDirty(setBiweeklyDay1)(Number(event.target.value))}>
                {DAYS_1_TO_30.map((day) => (
                  <option key={day} value={day}>
                    {day}
                  </option>
                ))}
              </select>
            </label>
            <label className="payroll-schedule-panel__schedule-day">
              Second payment day
              <select value={biweeklyDay2} onChange={(event) => markDirty(setBiweeklyDay2)(Number(event.target.value))}>
                {DAYS_1_TO_30.map((day) => (
                  <option key={day} value={day}>
                    {day}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : (
          <p className="payroll-schedule-panel__hint">Day-of-month selection is available in Simulation calendar mode.</p>
        ))}

      <label className="payroll-schedule-panel__schedule-day">
        Taxes / other obligations payment
        <select value={taxObligationsSchedule} onChange={(event) => markDirty(setTaxObligationsSchedule)(event.target.value)}>
          <option value="">— Select —</option>
          {TAX_OBLIGATIONS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <div className="payroll-schedule-panel__actions">
        <button
          type="button"
          className="payroll-schedule-panel__save-btn"
          onClick={handleSaveSchedule}
          disabled={!scheduleDirty || scheduleStatus === 'saving'}
        >
          {scheduleStatus === 'saving' ? 'Saving…' : 'Save'}
        </button>
        {scheduleMessage && (
          <span className={`payroll-schedule-panel__message ${scheduleStatus === 'error' ? 'is-error' : ''}`}>{scheduleMessage}</span>
        )}
      </div>
    </div>
  )
}

export default PayrollSchedulePanel
