import { useParams } from 'react-router-dom'
import RevenueView from './RevenueView'
import CostOfSalesView from './CostOfSalesView'
import ExpensesView from './ExpensesView'
import ReportsView from './ReportsView'

function FinancialTab() {
  const { sub } = useParams()

  switch (sub) {
    case 'cost-of-sales':
      return <CostOfSalesView />
    case 'expenses':
      return <ExpensesView />
    case 'reports':
      return <ReportsView />
    case 'revenue':
    default:
      return <RevenueView />
  }
}

export default FinancialTab
