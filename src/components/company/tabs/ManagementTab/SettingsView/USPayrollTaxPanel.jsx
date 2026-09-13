import { useEffect, useMemo, useState } from 'react'
import {
  EMPLOYER_BASE_RATE,
  EMPLOYER_TAX_RATES,
  FEDERAL_TAX_BRACKETS_2025_SINGLE,
  US_STATES,
} from '../../../../../services/usPayrollTax'
import { computeFullEmployeeWithholding, computeFullEmployerCost } from '../../../../../services/usBenefits'
import { fetchPayrollLevels } from '../../../../../services/payrollLevels'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import './USPayrollTaxPanel.css'

function formatPct(rate, digits = 2) {
  return `${(rate * 100).toFixed(digits)}%`
}

function formatMoney(value) {
  return formatCurrencyValue(value, 'USD')
}

// Matches the format used in the Payroll Matrix's level picker.
function formatLevelOption(option) {
  return `${option.level} > ${formatCurrencyValue(option.yearly, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

// The US payroll tax structure, wired up: Employer cost (also what drives
// the "Payroll Tax Expense" row in Financial > Expenses) and Employee
// withholding (Social Security, Medicare, federal bracket tax, and a
// per-state rate). Whatever's enabled in the "Benefits" pill is folded in
// here too — see services/usBenefits.js for exactly how. This is a
// deliberately simplified model overall — see services/usPayrollTax.js
// for what's simplified and why.
function USPayrollTaxPanel({ enabledBenefitKeys = [] }) {
  const [selectedState, setSelectedState] = useState('')
  const [selectedLevel, setSelectedLevel] = useState('')
  const [testSalary, setTestSalary] = useState('')
  const [paychecksPerYear, setPaychecksPerYear] = useState(24)
  const [payrollLevels, setPayrollLevels] = useState([])
  const [payrollLevelsStatus, setPayrollLevelsStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false
    fetchPayrollLevels()
      .then((levels) => {
        if (cancelled) return
        setPayrollLevels(levels)
        setPayrollLevelsStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setPayrollLevelsStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const parsedSalary = Number(testSalary)
  const hasValidSalary = Number.isFinite(parsedSalary) && parsedSalary > 0

  const employerResult = useMemo(
    () => (hasValidSalary ? computeFullEmployerCost(parsedSalary, enabledBenefitKeys) : null),
    [hasValidSalary, parsedSalary, enabledBenefitKeys],
  )
  const employeeResult = useMemo(
    () =>
      hasValidSalary ? computeFullEmployeeWithholding(parsedSalary, selectedState || null, paychecksPerYear, enabledBenefitKeys) : null,
    [hasValidSalary, parsedSalary, selectedState, paychecksPerYear, enabledBenefitKeys],
  )

  return (
    <div className="us-payroll-tax">
      <div className="us-payroll-tax__columns">
        <section className="us-payroll-tax__section">
          <h5>Employer</h5>
          <p className="us-payroll-tax__hint">
            Paid by the company on top of salary — this, plus any enabled Benefits, is what drives the "Payroll Tax Expense" row in
            Financial → Expenses.
          </p>
          <ul className="us-payroll-tax__rate-list">
            <li>
              <span>Social Security</span>
              <span>{formatPct(EMPLOYER_TAX_RATES.socialSecurity)}</span>
            </li>
            <li>
              <span>Medicare</span>
              <span>{formatPct(EMPLOYER_TAX_RATES.medicare)}</span>
            </li>
            <li>
              <span>Medicare — salary over {formatCurrencyValue(EMPLOYER_TAX_RATES.additionalMedicareThreshold, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</span>
              <span>+{formatPct(EMPLOYER_TAX_RATES.additionalMedicareRate)}</span>
            </li>
            <li>
              <span>FUTA</span>
              <span>{formatPct(EMPLOYER_TAX_RATES.futa)}</span>
            </li>
            <li>
              <span>SUTA</span>
              <span>{formatPct(EMPLOYER_TAX_RATES.suta)}</span>
            </li>
            <li className="us-payroll-tax__rate-total">
              <span>Base total</span>
              <span>{formatPct(EMPLOYER_BASE_RATE)}</span>
            </li>
          </ul>
        </section>

        <section className="us-payroll-tax__section">
          <h5>Employee</h5>
          <p className="us-payroll-tax__hint">Withheld from the employee's pay.</p>
          <ul className="us-payroll-tax__rate-list">
            <li>
              <span>Social Security</span>
              <span>6.20%</span>
            </li>
            <li>
              <span>Medicare</span>
              <span>1.45%</span>
            </li>
            <li>
              <span>Federal tax</span>
              <span>2025 IRS brackets</span>
            </li>
          </ul>

          <label className="us-payroll-tax__state-select">
            State
            <select value={selectedState} onChange={(event) => setSelectedState(event.target.value)}>
              <option value="">— Select a state —</option>
              {US_STATES.map((state) => (
                <option key={state} value={state}>
                  {state}
                </option>
              ))}
            </select>
            {selectedState && employeeResult && <span className="us-payroll-tax__state-rate">{formatPct(employeeResult.stateRate)}</span>}
          </label>

          <details className="us-payroll-tax__brackets">
            <summary>Federal bracket chart (2025, single filer)</summary>
            <ul className="us-payroll-tax__bracket-list">
              {FEDERAL_TAX_BRACKETS_2025_SINGLE.map((bracket, index, all) => (
                <li key={bracket.upTo}>
                  <span>
                    {index === 0
                      ? formatCurrencyValue(0, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
                      : formatCurrencyValue(all[index - 1].upTo, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}{' '}
                    –{' '}
                    {bracket.upTo === Infinity
                      ? '+'
                      : formatCurrencyValue(bracket.upTo, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </span>
                  <span>{formatPct(bracket.rate, 0)}</span>
                </li>
              ))}
            </ul>
          </details>
        </section>
      </div>

      <section className="us-payroll-tax__calculator">
        <h5>Salary Calculator</h5>
        <div className="us-payroll-tax__calculator-inputs">
          <label>
            Annual salary
            {payrollLevelsStatus === 'ready' && payrollLevels.length > 0 ? (
              <select
                value={selectedLevel}
                onChange={(event) => {
                  const level = event.target.value
                  setSelectedLevel(level)
                  const matched = payrollLevels.find((option) => option.level === level)
                  if (matched) setTestSalary(String(matched.yearly))
                }}
              >
                <option value="">— Select a level —</option>
                {payrollLevels.map((option) => (
                  <option key={option.id} value={option.level}>
                    {formatLevelOption(option)}
                  </option>
                ))}
              </select>
            ) : (
              <span className="us-payroll-tax__hint">
                {payrollLevelsStatus === 'loading' ? 'Loading payroll levels…' : 'No payroll levels configured yet.'}
              </span>
            )}
          </label>
          <label>
            Paychecks/year
            <select value={paychecksPerYear} onChange={(event) => setPaychecksPerYear(Number(event.target.value))}>
              <option value={12}>12 (monthly)</option>
              <option value={24}>24 (semi-monthly)</option>
              <option value={26}>26 (bi-weekly)</option>
              <option value={52}>52 (weekly)</option>
            </select>
          </label>
        </div>

        {enabledBenefitKeys.length > 0 && (
          <p className="us-payroll-tax__hint">
            Includes {enabledBenefitKeys.length} enabled benefit{enabledBenefitKeys.length === 1 ? '' : 's'} — see the "Benefits" pill to
            change these.
          </p>
        )}

        {hasValidSalary && employerResult && employeeResult ? (
          <div className="us-payroll-tax__results">
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employer cost (on top of salary)</div>
              <div className="us-payroll-tax__result-value">{formatMoney(employerResult.total)}/yr</div>
              <div className="us-payroll-tax__result-sub">
                {formatMoney(employerResult.payrollTax.total)} payroll tax + {formatMoney(employerResult.benefitsEmployerCost)} benefits
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee Social Security &amp; Medicare</div>
              <div className="us-payroll-tax__result-value">{formatMoney(employeeResult.socialSecurity + employeeResult.medicare)}/yr</div>
              <div className="us-payroll-tax__result-sub">
                {formatMoney(employeeResult.socialSecurity)} SS + {formatMoney(employeeResult.medicare)} Medicare
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee federal tax</div>
              <div className="us-payroll-tax__result-value">{formatMoney(employeeResult.federalTax)}/yr</div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee state tax</div>
              <div className="us-payroll-tax__result-value">{formatMoney(employeeResult.stateTax)}/yr</div>
              <div className="us-payroll-tax__result-sub">{selectedState || 'No state selected'}</div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee net pay</div>
              <div className="us-payroll-tax__result-value">
                {formatMoney(employeeResult.perCheck)}/check ({paychecksPerYear})
              </div>
              <div className="us-payroll-tax__result-sub">{formatMoney(employeeResult.netAnnual)}/yr after taxes and benefits</div>
            </div>
          </div>
        ) : (
          <div className="us-payroll-tax__hint">Select a payroll level above to see the breakdown.</div>
        )}
      </section>
    </div>
  )
}

export default USPayrollTaxPanel
