import { useParams } from 'react-router-dom'
import RevenueStreamsView from './RevenueStreamsView'
import ExpensesView from './ExpensesView'
import AccountingView from './AccountingView'
import FinancialModelingView from './FinancialModelingView'
import StartupInvestmentView from './StartupInvestmentView'

function FinancialTab() {
  const { sub } = useParams()

  switch (sub) {
    case 'expenses':
      return <ExpensesView />
    case 'accounting':
      return <AccountingView />
    case 'financial-modeling':
      return <FinancialModelingView />
    case 'startup-investment':
      return <StartupInvestmentView />
    case 'revenue-streams':
    default:
      return <RevenueStreamsView />
  }
}

export default FinancialTab
