import { IconArrowRight } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
import {
  ARL_DEFAULT_CLASS_KEY,
  ARL_RISK_CLASSES,
  COP_PER_USD_FALLBACK,
  EMPLOYEE_RATES,
  EMPLOYER_RATES,
  EXONERACION_THRESHOLD_SMMLV,
  FSP_BRACKETS,
  IBC_CEILING_SMMLV,
  RENTA_EXENTA_ANNUAL_CAP_UVT,
  RENTA_EXENTA_RATE,
  SMMLV_COP_DEFAULT,
  UVT_COP_DEFAULT,
  WITHHOLDING_BRACKETS_UVT,
  computeEmployeeWithholding,
  computeEmployerPayrollTax,
} from '../../../../../services/colombiaPayrollTax'
import { fetchExchangeRate } from '../../../../../services/exchangeRate'
import { fetchPayrollLevels } from '../../../../../services/payrollLevels'
import { fetchSettings, updateColombiaExchangeRate, updateColombiaReferenceFigures } from '../../../../../services/settings'
import { formatCurrencyValue, formatDualCurrency } from '../../../../../utils/currencyFormat'
import './USPayrollTaxPanel.css'

function formatPct(rate, digits = 2) {
  return `${(rate * 100).toFixed(digits)}%`
}

function formatCop(value) {
  return formatCurrencyValue(value, 'COP')
}

function formatLevelOption(option) {
  return `${option.level} > ${formatCurrencyValue(option.yearly, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

// Colombia's payroll tax structure: mandatory social security (pensión,
// salud, ARL), parafiscales (Caja/ICBF/SENA), prestaciones sociales
// (cesantías, intereses, prima), the FSP surcharge for higher earners, and
// the monthly retención en la fuente withholding table. See
// services/colombiaPayrollTax.js for exact sources, formulas, and
// simplifications.
function ColombiaPayrollTaxPanel() {
  const [selectedLevel, setSelectedLevel] = useState('')
  const [testSalary, setTestSalary] = useState('')
  const [arlClassKey, setArlClassKey] = useState(ARL_DEFAULT_CLASS_KEY)
  const [payrollLevels, setPayrollLevels] = useState([])
  const [payrollLevelsStatus, setPayrollLevelsStatus] = useState('loading')
  const [liveCopPerUsd, setLiveCopPerUsd] = useState(COP_PER_USD_FALLBACK)
  const [liveRateStatus, setLiveRateStatus] = useState('loading')
  const [projectedRateInput, setProjectedRateInput] = useState('')
  const [savedProjectedRate, setSavedProjectedRate] = useState(null)
  const [projectedRateStatus, setProjectedRateStatus] = useState('loading')
  const [projectedRateMessage, setProjectedRateMessage] = useState('')
  const [smmlvInput, setSmmlvInput] = useState(String(SMMLV_COP_DEFAULT))
  const [uvtInput, setUvtInput] = useState(String(UVT_COP_DEFAULT))
  const [savedSmmlv, setSavedSmmlv] = useState(null)
  const [savedUvt, setSavedUvt] = useState(null)
  const [referenceFiguresStatus, setReferenceFiguresStatus] = useState('idle')
  const [referenceFiguresMessage, setReferenceFiguresMessage] = useState('')

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
    fetchExchangeRate('COP', 'USD')
      .then((result) => {
        if (cancelled) return
        if (result?.rate > 0) setLiveCopPerUsd(1 / result.rate)
        setLiveRateStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setLiveRateStatus('fallback')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        const saved = settings.colombia_projected_cop_per_usd
        if (saved) {
          setSavedProjectedRate(saved)
          setProjectedRateInput(String(saved))
        }
        if (settings.colombia_smmlv_cop) {
          setSavedSmmlv(settings.colombia_smmlv_cop)
          setSmmlvInput(String(settings.colombia_smmlv_cop))
        }
        if (settings.colombia_uvt_cop) {
          setSavedUvt(settings.colombia_uvt_cop)
          setUvtInput(String(settings.colombia_uvt_cop))
        }
        setProjectedRateStatus('idle')
      })
      .catch(() => {
        if (!cancelled) setProjectedRateStatus('idle')
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Once the live rate arrives, seed the projected-rate field with it if
  // nothing has been saved yet — so the calculator always has a stable
  // number to work with instead of sitting blank.
  useEffect(() => {
    if (liveRateStatus === 'ready' && savedProjectedRate === null && !projectedRateInput) {
      setProjectedRateInput(String(Math.round(liveCopPerUsd)))
    }
  }, [liveRateStatus, liveCopPerUsd, savedProjectedRate, projectedRateInput])

  const projectedRateDirty = Number(projectedRateInput) !== savedProjectedRate

  const handleUseLiveRate = () => {
    setProjectedRateInput(String(Math.round(liveCopPerUsd)))
  }

  const handleSaveProjectedRate = async () => {
    const value = Number(projectedRateInput)
    if (!Number.isFinite(value) || value <= 0) {
      setProjectedRateMessage('Enter a valid positive rate first.')
      return
    }
    setProjectedRateStatus('saving')
    setProjectedRateMessage('')
    try {
      const result = await updateColombiaExchangeRate(value)
      setSavedProjectedRate(result.colombia_projected_cop_per_usd)
      setProjectedRateStatus('idle')
      setProjectedRateMessage('Saved.')
    } catch (error) {
      setProjectedRateStatus('error')
      setProjectedRateMessage(error.message || 'Failed to save the projected rate.')
    }
  }

  const copPerUsd = Number(projectedRateInput) > 0 ? Number(projectedRateInput) : COP_PER_USD_FALLBACK
  const smmlvCop = Number(smmlvInput) > 0 ? Number(smmlvInput) : SMMLV_COP_DEFAULT
  const uvtCop = Number(uvtInput) > 0 ? Number(uvtInput) : UVT_COP_DEFAULT

  const referenceFiguresDirty = Number(smmlvInput) !== savedSmmlv || Number(uvtInput) !== savedUvt

  const handleSaveReferenceFigures = async () => {
    const smmlvValue = Number(smmlvInput)
    const uvtValue = Number(uvtInput)
    if (!Number.isFinite(smmlvValue) || smmlvValue <= 0 || !Number.isFinite(uvtValue) || uvtValue <= 0) {
      setReferenceFiguresMessage('Enter valid positive values for both first.')
      return
    }
    setReferenceFiguresStatus('saving')
    setReferenceFiguresMessage('')
    try {
      const result = await updateColombiaReferenceFigures(smmlvValue, uvtValue)
      setSavedSmmlv(result.colombia_smmlv_cop)
      setSavedUvt(result.colombia_uvt_cop)
      setReferenceFiguresStatus('idle')
      setReferenceFiguresMessage('Saved.')
    } catch (error) {
      setReferenceFiguresStatus('error')
      setReferenceFiguresMessage(error.message || 'Failed to save the reference figures.')
    }
  }

  const arlRate = ARL_RISK_CLASSES.find((option) => option.key === arlClassKey)?.rate ?? ARL_RISK_CLASSES[0].rate

  const parsedSalary = Number(testSalary)
  const hasValidSalary = Number.isFinite(parsedSalary) && parsedSalary > 0
  const annualSalaryCop = hasValidSalary ? parsedSalary * copPerUsd : 0
  const monthlySalaryCop = annualSalaryCop / 12

  const employerResult = useMemo(
    () => (hasValidSalary ? computeEmployerPayrollTax(parsedSalary, copPerUsd, arlRate, smmlvCop) : null),
    [hasValidSalary, parsedSalary, copPerUsd, arlRate, smmlvCop],
  )
  const employeeResult = useMemo(
    () => (hasValidSalary ? computeEmployeeWithholding(parsedSalary, copPerUsd, smmlvCop, uvtCop) : null),
    [hasValidSalary, parsedSalary, copPerUsd, smmlvCop, uvtCop],
  )

  return (
    <div className="us-payroll-tax">
      <div className="us-payroll-tax__fx-row">
        <label className="us-payroll-tax__fx-projected">
          SMMLV (minimum wage, COP/month)
          <input
            type="number"
            min="0"
            step="1"
            value={smmlvInput}
            onChange={(event) => setSmmlvInput(event.target.value)}
          />
        </label>
        <label className="us-payroll-tax__fx-projected">
          UVT (COP)
          <input type="number" min="0" step="1" value={uvtInput} onChange={(event) => setUvtInput(event.target.value)} />
        </label>
        <button
          type="button"
          className="us-payroll-tax__save-btn"
          onClick={handleSaveReferenceFigures}
          disabled={!referenceFiguresDirty || referenceFiguresStatus === 'saving'}
        >
          {referenceFiguresStatus === 'saving' ? 'Saving…' : 'Save'}
        </button>
        {referenceFiguresMessage && (
          <span className={`us-payroll-tax__schedule-message ${referenceFiguresStatus === 'error' ? 'is-error' : ''}`}>
            {referenceFiguresMessage}
          </span>
        )}
      </div>
      <p className="us-payroll-tax__hint">
        These are indexed annually by DIAN/Mintrabajo — update them here each year rather than waiting on a code
        change.
      </p>

      <div className="us-payroll-tax__columns">
        <section className="us-payroll-tax__section">
          <h5>Employer</h5>
          <p className="us-payroll-tax__hint">
            Paid by the company on top of salary. Salud, SENA, and ICBF are waived for employees earning under{' '}
            {EXONERACION_THRESHOLD_SMMLV} SMMLV/month (Ley 1607 de 2012 / Ley 1819 de 2016 exoneración de aportes).
            All rates apply to the IBC, capped at {IBC_CEILING_SMMLV} SMMLV/month.
          </p>
          <ul className="us-payroll-tax__rate-list">
            <li>
              <span>Pensión</span>
              <span>{formatPct(EMPLOYER_RATES.pension)}</span>
            </li>
            <li>
              <span>Salud</span>
              <span>{formatPct(EMPLOYER_RATES.salud)}</span>
            </li>
            <li>
              <span>ARL ({arlClassKey})</span>
              <span>{formatPct(arlRate, 3)}</span>
            </li>
            <li>
              <span>Caja de Compensación Familiar</span>
              <span>{formatPct(EMPLOYER_RATES.caja)}</span>
            </li>
            <li>
              <span>ICBF</span>
              <span>{formatPct(EMPLOYER_RATES.icbf)}</span>
            </li>
            <li>
              <span>SENA</span>
              <span>{formatPct(EMPLOYER_RATES.sena)}</span>
            </li>
            <li>
              <span>Cesantías</span>
              <span>{formatPct(EMPLOYER_RATES.cesantias)}</span>
            </li>
            <li>
              <span>Intereses sobre cesantías</span>
              <span>{formatPct(EMPLOYER_RATES.interesesCesantias)}</span>
            </li>
            <li>
              <span>Prima de servicios</span>
              <span>{formatPct(EMPLOYER_RATES.prima)}</span>
            </li>
            <li className="us-payroll-tax__rate-total">
              <span>Base total (excl. ARL, before exoneración)</span>
              <span>
                {formatPct(
                  EMPLOYER_RATES.pension +
                    EMPLOYER_RATES.salud +
                    EMPLOYER_RATES.caja +
                    EMPLOYER_RATES.icbf +
                    EMPLOYER_RATES.sena +
                    EMPLOYER_RATES.cesantias +
                    EMPLOYER_RATES.interesesCesantias +
                    EMPLOYER_RATES.prima,
                )}
              </span>
            </li>
          </ul>

          <label className="us-payroll-tax__state-select">
            ARL risk class
            <select value={arlClassKey} onChange={(event) => setArlClassKey(event.target.value)}>
              {ARL_RISK_CLASSES.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label} — {formatPct(option.rate, 3)}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className="us-payroll-tax__section">
          <h5>Employee (withheld)</h5>
          <p className="us-payroll-tax__hint">Withheld from the employee's pay.</p>
          <ul className="us-payroll-tax__rate-list">
            <li>
              <span>Pensión</span>
              <span>{formatPct(EMPLOYEE_RATES.pension)}</span>
            </li>
            <li>
              <span>Salud</span>
              <span>{formatPct(EMPLOYEE_RATES.salud)}</span>
            </li>
            <li>
              <span>FSP (Fondo de Solidaridad Pensional)</span>
              <span>{employeeResult ? formatPct(employeeResult.fspRate) : '0%–2%'}</span>
            </li>
            <li className="us-payroll-tax__rate-total">
              <span>Base total (excl. FSP, excl. withholding)</span>
              <span>{formatPct(EMPLOYEE_RATES.pension + EMPLOYEE_RATES.salud)}</span>
            </li>
          </ul>

          <details className="us-payroll-tax__brackets">
            <summary>FSP brackets (by multiple of SMMLV)</summary>
            <ul className="us-payroll-tax__bracket-list">
              {FSP_BRACKETS.map((bracket) => (
                <li key={bracket.minSmmlv}>
                  <span>
                    {bracket.minSmmlv} – {bracket.maxSmmlv === Infinity ? '+' : bracket.maxSmmlv} SMMLV
                  </span>
                  <span>+{formatPct(bracket.rate, 1)}</span>
                </li>
              ))}
            </ul>
          </details>

          <details className="us-payroll-tax__brackets">
            <summary>Retención en la fuente (monthly, in UVT)</summary>
            <p className="us-payroll-tax__hint">
              Base = salary − employee social security − 25% renta exenta (capped at{' '}
              {RENTA_EXENTA_ANNUAL_CAP_UVT} UVT/year, i.e. {(RENTA_EXENTA_ANNUAL_CAP_UVT / 12).toFixed(2)} UVT/month).
              Renta exenta rate: {formatPct(RENTA_EXENTA_RATE, 0)}.
            </p>
            <ul className="us-payroll-tax__bracket-list">
              {WITHHOLDING_BRACKETS_UVT.map((bracket) => (
                <li key={bracket.from}>
                  <span>
                    {bracket.from} UVT – {bracket.to === Infinity ? '+' : `${bracket.to} UVT`}
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

        <div className="us-payroll-tax__fx-row">
          <span className="us-payroll-tax__fx-live">
            {liveRateStatus === 'ready'
              ? `Live rate: USD $1.00 ≈ ${formatCurrencyValue(liveCopPerUsd, 'COP', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
              : `Live rate unavailable (fallback ${formatCurrencyValue(liveCopPerUsd, 'COP', { minimumFractionDigits: 0, maximumFractionDigits: 0 })})`}
          </span>
          <button
            type="button"
            className="us-payroll-tax__fx-copy"
            onClick={handleUseLiveRate}
            disabled={liveRateStatus !== 'ready'}
            title="Copy the live rate into the projected rate"
            aria-label="Copy the live rate into the projected rate"
          >
            <IconArrowRight size={14} stroke={2} />
          </button>
          <label className="us-payroll-tax__fx-projected">
            Projected rate (locked for calculations)
            <input
              type="number"
              min="0"
              step="1"
              value={projectedRateInput}
              onChange={(event) => setProjectedRateInput(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="us-payroll-tax__save-btn"
            onClick={handleSaveProjectedRate}
            disabled={!projectedRateDirty || projectedRateStatus === 'saving'}
          >
            {projectedRateStatus === 'saving' ? 'Saving…' : 'Save'}
          </button>
          {projectedRateMessage && (
            <span className={`us-payroll-tax__schedule-message ${projectedRateStatus === 'error' ? 'is-error' : ''}`}>
              {projectedRateMessage}
            </span>
          )}
        </div>
        <p className="us-payroll-tax__hint">
          Colombia's monthly calculations (IBC, FSP, withholding) are based on the projected rate above, not the live
          rate — so results stay stable until you deliberately update it.
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

          <label>
            Annual salary (COP)
            <span className="us-payroll-tax__derived-value">{hasValidSalary ? formatCop(annualSalaryCop) : '—'}</span>
          </label>

          <label>
            Monthly payment (COP)
            <span className="us-payroll-tax__derived-value">
              {hasValidSalary ? formatCop(monthlySalaryCop) : '—'}
            </span>
          </label>
        </div>

        {hasValidSalary && employerResult && employeeResult ? (
          <div className="us-payroll-tax__results">
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employer cost (on top of salary)</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employerResult.total * copPerUsd, 'COP', employerResult.total)}/yr
              </div>
              <div className="us-payroll-tax__result-sub">
                {formatPct(employerResult.total / parsedSalary)} effective rate
                {employerResult.exonerado ? ' — exoneración applied' : ''}
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee social security (pensión + FSP + salud)</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employeeResult.socialSecurity * copPerUsd, 'COP', employeeResult.socialSecurity)}/yr
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee retención en la fuente</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employeeResult.withholding * copPerUsd, 'COP', employeeResult.withholding)}/yr
              </div>
            </div>
            <div className="us-payroll-tax__result-card">
              <div className="us-payroll-tax__result-label">Employee net pay</div>
              <div className="us-payroll-tax__result-value">
                {formatDualCurrency(employeeResult.netAnnual * copPerUsd, 'COP', employeeResult.netAnnual)}/yr
              </div>
              <div className="us-payroll-tax__result-sub">
                {formatDualCurrency(employeeResult.totalWithheld * copPerUsd, 'COP', employeeResult.totalWithheld)}/yr withheld total
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

export default ColombiaPayrollTaxPanel
