import { US_BENEFITS } from '../../../../../services/usBenefits'
import './USBenefitsPanel.css'

function formatPct(rate) {
  return `${(rate * 100).toFixed(2).replace(/\.00$/, '')}%`
}

// Each enabled benefit's employer share is added into the "Payroll taxes/
// charges" employer cost (and, transitively, the "Payroll Tax Expense" row
// in Financial > Expenses); its employee share reduces take-home pay and,
// for pre-tax benefits, the wage base other taxes are computed against —
// see services/usBenefits.js for exactly which taxes each benefit affects.
function USBenefitsPanel({ enabledBenefitKeys, onToggleBenefit }) {
  const enabled = new Set(enabledBenefitKeys || [])

  return (
    <div className="us-benefits">
      <p className="us-benefits__hint">
        Check the benefits this company offers. Selected benefits are added to the employer cost calculated in "Payroll taxes/charges,"
        and any benefit that's pre-tax correctly reduces the wages federal, state, Social Security, and/or Medicare tax are computed
        against — hover a benefit's name for what it does.
      </p>
      <div className="us-benefits__table-wrap">
        <table className="us-benefits__table">
          <thead>
            <tr>
              <th />
              <th>Benefit</th>
              <th className="num">Salary %</th>
              <th className="num">Employer %</th>
              <th className="num">Employee %</th>
            </tr>
          </thead>
          <tbody>
            {US_BENEFITS.map((benefit) => {
              const isEnabled = enabled.has(benefit.key)
              const totalPct = benefit.employerPct + benefit.employeePct
              return (
                <tr key={benefit.key} className={isEnabled ? 'is-enabled' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={() => onToggleBenefit(benefit.key)}
                      aria-label={`Include ${benefit.label}`}
                    />
                  </td>
                  <td>
                    <span className="us-benefits__label" title={benefit.description}>
                      {benefit.label}
                    </span>
                  </td>
                  <td className="num">{formatPct(totalPct)}</td>
                  <td className="num">{formatPct(benefit.employerPct)}</td>
                  <td className="num">{formatPct(benefit.employeePct)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default USBenefitsPanel
