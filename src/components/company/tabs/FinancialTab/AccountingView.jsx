import { Navigate, useParams } from 'react-router-dom'
import FinancialSubNav from './FinancialSubNav'
import StubSection from './StubSection'
import GeneralLedgerView from './Accounting/GeneralLedgerView'
import ChartOfAccountsView from './Accounting/ChartOfAccountsView'
import IncomeStatementView from './Accounting/IncomeStatementView'
import BalanceSheetView from './Accounting/BalanceSheetView'
import CashFlowStatementView from './Accounting/CashFlowStatementView'
import TrialBalanceView from './Accounting/TrialBalanceView'

const SECTIONS = [
  {
    slug: 'general-ledger',
    label: 'General Ledger',
    description: 'The full chronological record of every financial transaction, by account.',
  },
  {
    slug: 'income-statement',
    label: 'Income Statement',
    description: 'Revenue, expenses, and net income over a period.',
  },
  {
    slug: 'balance-sheet',
    label: 'Balance Sheet',
    description: 'Assets, liabilities, and equity at a point in time.',
  },
  {
    slug: 'cash-flow-statement',
    label: 'Cash Flow Statement',
    description: 'Cash generated and used across operating, investing, and financing activities.',
  },
  {
    slug: 'trial-balance',
    label: 'Trial Balance',
    description: 'Every ledger account balance side by side, used to confirm debits equal credits.',
  },
  {
    slug: 'chart-of-accounts',
    label: 'Chart of Accounts',
    description: 'The full list of accounts used to categorize every transaction.',
  },
]

function AccountingView() {
  const { companyId, section } = useParams()

  if (!section) {
    return <Navigate to={`/company/${companyId}/financial/accounting/${SECTIONS[0].slug}`} replace />
  }

  const activeSection = SECTIONS.find((item) => item.slug === section) ?? SECTIONS[0]

  const renderSection = () => {
    if (activeSection.slug === 'general-ledger') return <GeneralLedgerView />
    if (activeSection.slug === 'chart-of-accounts') return <ChartOfAccountsView />
    if (activeSection.slug === 'income-statement') return <IncomeStatementView />
    if (activeSection.slug === 'balance-sheet') return <BalanceSheetView />
    if (activeSection.slug === 'cash-flow-statement') return <CashFlowStatementView />
    if (activeSection.slug === 'trial-balance') return <TrialBalanceView />
    return <StubSection title={activeSection.label} description={activeSection.description} />
  }

  return (
    <div className="panel-surface">
      <h3>Accounting</h3>
      <p>Statements and ledgers derived from the company's recorded financial activity.</p>
      <FinancialSubNav basePath={`/company/${companyId}/financial/accounting`} items={SECTIONS} />
      {renderSection()}
    </div>
  )
}

export default AccountingView
