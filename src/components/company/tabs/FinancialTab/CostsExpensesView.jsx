import { Navigate, useParams } from 'react-router-dom'
import FinancialSubNav from './FinancialSubNav'
import ExpensesView from './ExpensesView'
import StubSection from './StubSection'
import ProvidersView from './ProvidersView'
import CostOfSalesView from './CostOfSalesView'

const SECTIONS = [
  { slug: 'cost-of-sales', label: 'Cost of Sales', description: 'The direct costs of delivering each revenue stream.' },
  { slug: 'expenses', label: 'Expenses' },
  { slug: 'providers', label: 'Providers', description: 'The suppliers and service providers behind these costs.' },
]

function CostsExpensesView() {
  const { companyId, section } = useParams()

  if (!section) {
    return <Navigate to={`/company/${companyId}/financial/expenses/${SECTIONS[0].slug}`} replace />
  }

  const activeSection = SECTIONS.find((item) => item.slug === section) ?? SECTIONS[0]

  return (
    <div className="panel-surface">
      <h3>COS/Expenses</h3>
      <FinancialSubNav basePath={`/company/${companyId}/financial/expenses`} items={SECTIONS} />
      {activeSection.slug === 'cost-of-sales' ? (
        <CostOfSalesView />
      ) : activeSection.slug === 'expenses' ? (
        <ExpensesView />
      ) : activeSection.slug === 'providers' ? (
        <ProvidersView />
      ) : (
        <StubSection title={activeSection.label} description={activeSection.description} />
      )}
    </div>
  )
}

export default CostsExpensesView
