import { Navigate, useParams } from 'react-router-dom'
import FinancialSubNav from './FinancialSubNav'
import StubSection from './StubSection'

const SECTIONS = [
  {
    slug: 'noplat',
    label: 'NOPLAT',
    description: 'Net Operating Profit Less Adjusted Taxes — operating profitability independent of financing structure.',
  },
  {
    slug: 'ebitda',
    label: 'EBITDA',
    description: 'Earnings before interest, taxes, depreciation, and amortization.',
  },
  {
    slug: 'cap-table',
    label: 'Cap Table',
    description: 'Ownership breakdown across founders, investors, and the option pool, round by round.',
  },
  {
    slug: 'valuation-models',
    label: 'Valuation Models',
    description: 'DCF, comparable-company, and precedent-transaction valuations.',
  },
  {
    slug: 'comps',
    label: 'COMPS',
    description: 'Comparable company analysis — valuation multiples (EV/Revenue, EV/EBITDA) benchmarked against similar public and private companies.',
  },
  {
    slug: 'unit-economics',
    label: 'Unit Economics',
    description: 'Revenue and cost per unit — per customer, order, or contract.',
  },
  {
    slug: 'revenue-per-employee',
    label: 'Rev. per Employee',
    description: 'Revenue generated per employee — a common efficiency benchmark investors use to gauge operating leverage.',
  },
  {
    slug: 'financial-projections',
    label: 'Financial Projections',
    description: 'Forward-looking revenue, cost, and cash flow scenarios feeding every metric on this tab.',
  },
  // Additional metrics investors typically diligence beyond the ones requested above.
  {
    slug: 'growth-and-margins',
    label: 'Growth & Margins',
    description: 'Revenue growth rate (MoM/YoY) and gross margin trends over the projection.',
  },
  {
    slug: 'burn-and-runway',
    label: 'Burn Rate & Runway',
    description: 'Monthly net cash burn and the resulting months of runway at current spend.',
  },
  {
    slug: 'rule-of-40',
    label: 'Rule of 40',
    description: 'Growth rate plus profit margin — a quick health check investors use for SaaS-like businesses.',
  },
  {
    slug: 'recurring-revenue',
    label: 'ARR / MRR',
    description: 'Annual and monthly recurring revenue, plus net revenue retention.',
  },
  {
    slug: 'cac-ltv',
    label: 'CAC & LTV',
    description: 'Customer acquisition cost, lifetime value, and the LTV:CAC ratio.',
  },
  {
    slug: 'return-on-invested-capital',
    label: 'ROIC',
    description: 'Return on invested capital — how efficiently the business turns capital into profit.',
  },
]

function FinancialModelingView() {
  const { companyId, section } = useParams()

  if (!section) {
    return <Navigate to={`/company/${companyId}/financial/financial-modeling/${SECTIONS[0].slug}`} replace />
  }

  const activeSection = SECTIONS.find((item) => item.slug === section) ?? SECTIONS[0]

  return (
    <div className="panel-surface">
      <h3>Financial Modeling</h3>
      <p>Forward-looking models and the metrics an investor would use to evaluate this company.</p>
      <FinancialSubNav basePath={`/company/${companyId}/financial/financial-modeling`} items={SECTIONS} />
      <StubSection title={activeSection.label} description={activeSection.description} />
    </div>
  )
}

export default FinancialModelingView
