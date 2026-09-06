import { useParams } from 'react-router-dom'
import RevenueStreamsView from './RevenueStreamsView'
import ExpensesView from './ExpensesView'
import ReportsView from './ReportsView'

function FinancialTab() {
  const { sub } = useParams()

  switch (sub) {
    case 'expenses':
      return <ExpensesView />
    case 'reports':
      return <ReportsView />
    case 'revenue-streams':
    default:
      return <RevenueStreamsView />
  }
}

export default FinancialTab
