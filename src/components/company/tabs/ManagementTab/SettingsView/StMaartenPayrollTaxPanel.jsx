import { useEffect, useMemo, useState } from 'react'
import {
  EMPLOYEE_BASE_RATE,
  EMPLOYER_BASE_RATE,
  OV_RATE_DEFAULT,
  OV_RATE_MAX,
  OV_RATE_MIN,
  SZV_EMPLOYEE_RATES,
  SZV_EMPLOYER_RATES,
  WAGE_TAX_BRACKETS_ANG,
  WAGE_TAX_EXEMPTION_ANG,
  ANG_PER_USD_FALLBACK,
  computeEmployeeWithholding,
  computeEmployerPayrollTax,
} from '../../../../../services/stMaartenPayrollTax'
import { fetchExchangeRate } from '../../../../../services/exchangeRate'
import { fetchPayrollLevels } from '../../../../../services/payrollLevels'
import { formatCurrencyValue, formatDualCurrency } from '../../../../../utils/currencyFormat'
import './USPayrollTaxPanel.css'

function formatPct(rate, digits = 2) {
  return `${(rate * 100).toFixed(digits)}%`
}

function formatAng(value, options) {
  return formatCurrencyValue(value, 'ANG', options)
}

function formatLevelOption(option) {
  return `${option.level} > ${formatCurrencyValue(option.yearly, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

// Sint Maarten's SZV social-insurance premiums (AOV/AWW/BVZ/AVBZ/ZV/OV) plus
// progressive wage tax — see services/stMaartenPayrollTax.js for exact
// sources, rates, and the simplifications/uncertainties in this model
// (there's no worked example to validate against here, unlike the US one).
function StMaartenPayrollTaxPanel() {
  const [selectedLevel, setSelectedLevel] = useState('')
  const [testSalary, setTestSalary] = useState('')
  const [ovRate, setOvRate] = useState(OV_RATE_DEFAULT)
  const [payrollLevels, setPayrollLevels] = useState([])
  const [payrollLevelsStatus, setPayrollLevelsStatus] = useState('loading')
  const [angPerUsd, setAngPerUsd] = useState(ANG_PER_USD_FALLBACK)
  const [rateStatus, setRateStatus] = useState('loading')

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

  useEffect(() => {
    let cancelled = false
    fetchExchangeRate('ANG', 'USD')
      .then((result) => {
        if (cancelled) return
        if (result?.rate > 0) setAngPerUsd(1 / result.rate)
        setRateStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setRateStatus('fallback')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const parsedSalary = Number(testSalary)
  const hasValidSalary = Number.isFinite(parsedSalary) && parsedSalary > 0

  const employerResult = useMemo(
    () => (hasValidSalary ? computeEmployerPayrollTax(parsedSalary, angPerUsd, ovRate) : null),
    [hasValidSalary, parsedSalary, angPerUsd, ovRate],
  )
  const employeeResult = useMemo(
    () => (hasValidSalary ? computeEmployeeWithholding(parsedSalary, angPerUsd) : null),
    [hasValidSalary, parsedSalary, angPerUsd],
  )

  return (
    <div className="us-payroll-tax">
      <p className="us-payroll-tax__hint">
        Sourced from published SZV/tax-office rates — there's no worked example to validate this against yet (unlike
        the US structure), and the wage-tax bracket boundaries are the last confirmed (2023) figures since the exact
        2025 boundaries weren't available. Treat this as a first pass; correct it if you have a real payslip to check
        against.
      </p>

      <div className="us-payroll-tax__columns">
        <section className="us-payroll-tax__section">
          <h5>Employer (SZV premiums)</h5>
          <p className="us-payroll-tax__hint">
            Paid by the company on top of salary — drives the "Payroll Tax Expense" row in Financial → Expenses for
            St Marteen positions.
          </p>
          <ul className="us-payroll-tax__rate-list">
            <li>
              <span>AOV (old age pension)</span>
              <span>{formatPct(SZV_EMPLOYER_RATES.aov)}</span>
            </li>
            <li>
              <span>AWW (widows &amp; orphans)</span>
              <span>{formatPct(SZV_EMPLOYER_RATES.aww)}</span>
            </li>
            <li>
              <span>BVZ (health insurance)</span>
              <span>{formatPct(SZV_EMPLOYER_RATES.bvz)}</span>
            </li>
            <li>
              <span>AVBZ (exceptional medical expenses)</span>
              <span>{formatPct(SZV_EMPLOYER_RATES.avbz)}</span>
            </li>
            <li>
              <span>ZV (sick-pay insurance)</span>
              <span>{formatPct(SZV_EMPLOYER_RATES.zv)}</span>
            </li>
            <li className="us-payroll-tax__rate-total">
              <span>Base total (excl. OV)</span>
              <span>{formatPct(EMPLOYER_BASE_RATE)}</span>
            </li>
          </ul>

          <label className="us-payroll-tax__state-select">
            OV (accident insurance) — {formatPct(ovRate)}
            <input
              type="range"
              min={OV_RATE_MIN}
              max={OV_RATE_MAX}
              step={0.001}
              value={ovRate}
              onChange={(event) => setOvRate(Number(event.target.value))}
            />
          </label>
          <p className="us-payroll-tax__hint">
            SZV assigns this 0.5%–5% per employer based on accident risk class — no single published default, so
            adjust to match your actual SZV classification.
          </p>
        </section>

        <section className="us-payroll-tax__section">
          <h5>Employee (withheld)</h5>
          <p className="us-payroll-tax__hint">Withheld from the employee's pay.</p>
          <ul className="us-payroll-tax__rate-list">
            <li>
              <span>AOV</span>
              <span>{formatPct(SZV_EMPLOYEE_RATES.aov)}</span>
            </li>
            <li>
              <span>AWW</span>
              <span>{formatPct(SZV_EMPLOYEE_RATES.aww)}</span>
            </li>
            <li>
              <span>BVZ</span>
              <span>{formatPct(SZV_EMPLOYEE_RATES.bvz)}</span>
            </li>
            <li>
              <span>AVBZ</span>
              <span>{formatPct(SZV_EMPLOYEE_RATES.avbz)}</span>
            </li>
            <li className="us-payroll-tax__rate-total">
              <span>Base total</span>
              <span>{formatPct(EMPLOYEE_BASE_RATE)}</span>
            </li>
          </ul>

          <details className="us-payroll-tax__brackets">
            <summary>Wage tax brackets (2023 boundaries, surtax included)</summary>
            <p className="us-payroll-tax__hint">
              Exemption: {formatAng(WAGE_TAX_EXEMPTION_ANG, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/year before
              these brackets apply.
            </p>
            <ul className="us-payroll-tax__bracket-list">
              {WAGE_TAX_BRACKETS_ANG.map((bracket, index, all) => (
                <li key={bracket.upTo}>
                  <span>
                    {index === 0
                      ? formatAng(0, { minimumFractionDigits: 0, maximumFractionDigits: 0 })
                      : formatAng(all[index - 1].upTo, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}{' '}
                    –{' '}
                    {bracket.upTo === Infinity ? '+' : formatAng(bracket.upTo, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </span>
                  <span>{formatPct(bracket.rate, 2)}</span>
                </li>
              ))}
            </ul>
          </details>
        </section>
      </div>

      <section className="us-payroll-tax__calculator">
        <h5>Salary Calculator</h5>
        <p className="us-payroll-tax__hint">
          {rateStatus === 'ready'
            ? `Using live rate: USD $1.00 ≈ ${formatAng(angPerUsd, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}.`
            : `Using fallback fixed peg: USD $1.00 ≈ ${formatAng(angPerUsd)} (live rate unavailable).`}
        </p>
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
        </div>

        {hasValidSalary && employerResult && employeeResult ? (
          <div className="us-payroll-tax__results">
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employer cost (on top of salary)</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employerResult.total * angPerUsd, 'ANG', employerResult.total)}/yr
              </div>
              <div className="us-payroll-tax__result-sub">{formatPct(employerResult.total / parsedSalary)} effective rate</div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee social premiums (AOV/AWW/BVZ/AVBZ)</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employeeResult.socialPremiums * angPerUsd, 'ANG', employeeResult.socialPremiums)}/yr
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee wage tax</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employeeResult.wageTax * angPerUsd, 'ANG', employeeResult.wageTax)}/yr
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee net pay</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employeeResult.netAnnual * angPerUsd, 'ANG', employeeResult.netAnnual)}/yr
              </div>
              <div className="us-payroll-tax__result-sub">
                {formatDualCurrency(employeeResult.totalWithheld * angPerUsd, 'ANG', employeeResult.totalWithheld)}/yr withheld total
              </div>
            </div>
          </div>
        ) : (
          <div className="us-payroll-tax__hint">Select a payroll level above to see the breakdown.</div>
        )}
      </section>
    </div>
  )
}

export default StMaartenPayrollTaxPanel
