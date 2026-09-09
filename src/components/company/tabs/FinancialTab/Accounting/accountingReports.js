// Pure computation over the raw ledger data (accounts + journal entries) —
// the same data GeneralLedgerView reads — into the shape each statement
// view renders and exports. No fetching here, just derivation, so these
// stay trivially "live": whenever a Commercial Operations entry posts a new
// journal entry, the next fetch picks it up automatically.

const COGS_CODES = new Set(['5000', '5900'])

function filterByDateRange(journalEntries, startDate, endDate) {
  return journalEntries.filter((entry) => (!startDate || entry.entry_date >= startDate) && (!endDate || entry.entry_date <= endDate))
}

function netByAccount(journalEntries, sign) {
  // sign: +1 for debit-minus-credit, -1 for credit-minus-debit
  const totals = new Map()
  journalEntries.forEach((entry) => {
    entry.lines.forEach((line) => {
      const prev = totals.get(line.account_id) || 0
      const delta = sign * (line.debit - line.credit)
      totals.set(line.account_id, prev + delta)
    })
  })
  return totals
}

function rowsFor(accounts, totals, sign = 1) {
  return accounts
    .map((account) => ({ name: account.name, amount: sign * (totals.get(account.id) || 0) }))
    .filter((row) => Math.abs(row.amount) > 0.004)
}

export function buildTrialBalance(accounts, journalEntries) {
  const totals = new Map()
  journalEntries.forEach((entry) => {
    entry.lines.forEach((line) => {
      const bucket = totals.get(line.account_id) || { debit: 0, credit: 0 }
      bucket.debit += line.debit
      bucket.credit += line.credit
      totals.set(line.account_id, bucket)
    })
  })

  // Net debit-minus-credit decides which column an account lands in — an
  // account can land against its "normal" side (e.g. Cash gone negative)
  // and must still show up, on the other column, or the trial balance can't
  // do its one job: proving total debits equal total credits.
  const rows = accounts
    .filter((account) => totals.has(account.id))
    .map((account) => {
      const bucket = totals.get(account.id)
      const net = bucket.debit - bucket.credit
      return {
        name: account.name,
        debit: net > 0 ? net : 0,
        credit: net < 0 ? -net : 0,
      }
    })
    .filter((row) => row.debit > 0.004 || row.credit > 0.004)

  const totalDebit = rows.reduce((sum, row) => sum + row.debit, 0)
  const totalCredit = rows.reduce((sum, row) => sum + row.credit, 0)
  return { rows, totalDebit, totalCredit, balanced: Math.abs(totalDebit - totalCredit) < 0.01 }
}

export function buildIncomeStatement(accounts, journalEntries, { startDate, endDate } = {}) {
  const filtered = filterByDateRange(journalEntries, startDate, endDate)
  const totals = netByAccount(filtered, -1) // credit-minus-debit: positive for revenue, negative for contra-revenue/expense

  const revenueAccounts = accounts.filter((a) => a.account_type === 'revenue' || a.account_type === 'contra_revenue')
  const cogsAccounts = accounts.filter((a) => a.account_type === 'expense' && COGS_CODES.has(a.code))
  const opexAccounts = accounts.filter((a) => a.account_type === 'expense' && !COGS_CODES.has(a.code))

  const revenueRows = rowsFor(revenueAccounts, totals)
  const revenueTotal = revenueRows.reduce((sum, row) => sum + row.amount, 0)
  const cogsRows = rowsFor(cogsAccounts, totals, -1)
  const cogsTotal = cogsRows.reduce((sum, row) => sum + row.amount, 0)
  const opexRows = rowsFor(opexAccounts, totals, -1)
  const opexTotal = opexRows.reduce((sum, row) => sum + row.amount, 0)

  const grossProfit = revenueTotal - cogsTotal
  const netIncome = grossProfit - opexTotal

  return {
    title: 'Income Statement',
    sections: [
      { key: 'revenue', label: 'Revenue', color: '#35D399', rows: revenueRows, subtotal: revenueTotal },
      { key: 'cogs', label: 'Cost of Goods Sold', color: '#f59e0b', rows: cogsRows, subtotal: cogsTotal },
      { key: 'opex', label: 'Operating Expenses', color: '#f87171', rows: opexRows, subtotal: opexTotal },
    ].filter((section) => section.rows.length > 0),
    metrics: [
      { label: 'Gross Profit', amount: grossProfit },
      { label: 'Net Income', amount: netIncome, primary: true },
    ],
  }
}

export function buildBalanceSheet(accounts, journalEntries, { asOfDate } = {}) {
  const filtered = asOfDate ? journalEntries.filter((entry) => entry.entry_date <= asOfDate) : journalEntries
  const totals = netByAccount(filtered, 1) // debit-minus-credit: positive for assets, negative for liabilities

  const assetAccounts = accounts.filter((a) => a.account_type === 'asset')
  const liabilityAccounts = accounts.filter((a) => a.account_type === 'liability')
  const equityAccounts = accounts.filter((a) => a.account_type === 'equity')
  const earningsAccounts = accounts.filter((a) => ['revenue', 'contra_revenue', 'expense'].includes(a.account_type))

  const assetRows = rowsFor(assetAccounts, totals)
  const assetTotal = assetRows.reduce((sum, row) => sum + row.amount, 0)
  const liabilityRows = rowsFor(liabilityAccounts, totals, -1)
  const liabilityTotal = liabilityRows.reduce((sum, row) => sum + row.amount, 0)

  // Equity has two sources: real posted equity accounts (e.g. Owner's
  // Capital, credited when Start-up Working Capital becomes opening cash)
  // plus Retained Earnings, derived from cumulative net income since there's
  // no period-close step that actually posts it to an account.
  const equityAccountRows = rowsFor(equityAccounts, totals, -1)
  const retainedEarnings = -earningsAccounts.reduce((sum, account) => sum + (totals.get(account.id) || 0), 0)
  const equityRows = [
    ...equityAccountRows,
    ...(Math.abs(retainedEarnings) > 0.004 ? [{ name: 'Retained Earnings', amount: retainedEarnings }] : []),
  ]
  const equityTotal = equityAccountRows.reduce((sum, row) => sum + row.amount, 0) + retainedEarnings

  return {
    title: 'Balance Sheet',
    sections: [
      { key: 'assets', label: 'Assets', color: '#38bdf8', rows: assetRows, subtotal: assetTotal },
      { key: 'liabilities', label: 'Liabilities', color: '#f87171', rows: liabilityRows, subtotal: liabilityTotal },
      { key: 'equity', label: 'Equity', color: '#a78bfa', rows: equityRows, subtotal: equityTotal },
    ].filter((section) => section.rows.length > 0),
    metrics: [
      { label: 'Total Assets', amount: assetTotal },
      { label: 'Total Liabilities + Equity', amount: liabilityTotal + equityTotal },
    ],
    balanced: Math.abs(assetTotal - (liabilityTotal + equityTotal)) < 0.01,
  }
}

export function buildCashFlowStatement(accounts, journalEntries, { startDate, endDate } = {}) {
  const cashAccount = accounts.find((account) => account.code === '1000')
  if (!cashAccount) return { title: 'Cash Flow Statement', sections: [], metrics: [] }

  const filtered = filterByDateRange(journalEntries, startDate, endDate)
  const operating = []
  const investing = []

  filtered.forEach((entry) => {
    const cashLine = entry.lines.find((line) => line.account_id === cashAccount.id)
    if (!cashLine) return
    const netCash = cashLine.debit - cashLine.credit
    if (Math.abs(netCash) < 0.004) return

    const otherLine = entry.lines.find((line) => line.account_id !== cashAccount.id)
    const otherAccount = otherLine ? accounts.find((account) => account.id === otherLine.account_id) : null
    const row = { name: entry.memo || otherAccount?.name || 'Cash movement', amount: netCash }
    if (otherAccount?.code === '1500') investing.push(row)
    else operating.push(row)
  })

  const sum = (rows) => rows.reduce((total, row) => total + row.amount, 0)
  const operatingTotal = sum(operating)
  const investingTotal = sum(investing)
  const netChange = operatingTotal + investingTotal

  return {
    title: 'Cash Flow Statement',
    sections: [
      { key: 'operating', label: 'Operating Activities', color: '#35D399', rows: operating, subtotal: operatingTotal },
      { key: 'investing', label: 'Investing Activities', color: '#38bdf8', rows: investing, subtotal: investingTotal },
    ].filter((section) => section.rows.length > 0),
    metrics: [{ label: 'Net Change in Cash', amount: netChange, primary: true }],
  }
}

const ACCOUNT_TYPE_LABELS = {
  asset: 'Assets',
  liability: 'Liabilities',
  equity: 'Equity',
  revenue: 'Revenue',
  contra_revenue: 'Contra-Revenue',
  expense: 'Expenses',
}
const ACCOUNT_TYPE_ORDER = ['asset', 'liability', 'equity', 'revenue', 'contra_revenue', 'expense']

/** Ending balance per account, for a PDF-friendly "GL by account" summary —
 * the on-screen General Ledger view shows full posting-by-posting detail,
 * this is the condensed export version. */
export function buildGeneralLedgerSummary(accounts, journalEntries) {
  const totals = new Map()
  journalEntries.forEach((entry) => {
    entry.lines.forEach((line) => {
      const prev = totals.get(line.account_id) || 0
      totals.set(line.account_id, prev + (line.debit - line.credit))
    })
  })

  const sections = ACCOUNT_TYPE_ORDER.map((type) => {
    const rows = accounts
      .filter((account) => account.account_type === type && totals.has(account.id))
      .map((account) => {
        const net = totals.get(account.id) || 0
        const amount = account.normal_balance === 'debit' ? net : -net
        return { name: `${account.code} ${account.name}`, amount }
      })
      .filter((row) => Math.abs(row.amount) > 0.004)
    return { key: type, label: ACCOUNT_TYPE_LABELS[type], color: '#38bdf8', rows, subtotal: rows.reduce((sum, row) => sum + row.amount, 0) }
  }).filter((section) => section.rows.length > 0)

  return { title: 'General Ledger', sections, metrics: [] }
}

export function generalLedgerToCsvRows(accounts, journalEntries) {
  const accountsById = new Map(accounts.map((account) => [account.id, account]))
  const postings = []
  journalEntries.forEach((entry) => {
    entry.lines.forEach((line) => {
      const account = accountsById.get(line.account_id)
      postings.push({
        code: account?.code ?? '?',
        name: account?.name ?? 'Unknown account',
        date: entry.entry_date,
        memo: entry.memo || '',
        debit: line.debit,
        credit: line.credit,
      })
    })
  })
  postings.sort((a, b) => (a.code === b.code ? a.date.localeCompare(b.date) : a.code.localeCompare(b.code)))
  const rows = postings.map((p) => [p.code, p.name, p.date, p.memo, p.debit.toFixed(2), p.credit.toFixed(2)])
  return { headers: ['Account Code', 'Account Name', 'Date', 'Memo', 'Debit', 'Credit'], rows }
}

export function chartOfAccountsToCsvRows(accounts) {
  const rows = accounts.map((account) => [account.code, account.name, account.account_type, account.normal_balance])
  return { headers: ['Code', 'Name', 'Type', 'Normal Balance'], rows }
}

export function reportToPdfSpec(report, periodsCaption) {
  return {
    documentTitle: report.title,
    eyebrow: 'Accounting',
    periodsCaption,
    periodLabels: ['Amount'],
    summaryTiles: report.metrics.map((metric) => ({ label: metric.label, value: metric.amount, primary: Boolean(metric.primary) })),
    sections: report.sections.map((section) => ({
      key: section.key,
      label: section.label,
      color: section.color,
      records: section.rows.map((row) => ({ name: row.name, values: [row.amount], total: row.amount })),
      subtotal: { values: [section.subtotal], total: section.subtotal },
    })),
    totalsRow: null,
  }
}

export function reportToCsvRows(report) {
  const rows = []
  report.sections.forEach((section) => {
    section.rows.forEach((row) => rows.push([section.label, row.name, row.amount.toFixed(2)]))
    rows.push([section.label, 'Subtotal', section.subtotal.toFixed(2)])
  })
  report.metrics.forEach((metric) => rows.push(['', metric.label, metric.amount.toFixed(2)]))
  return { headers: ['Section', 'Line item', 'Amount'], rows }
}

export function trialBalanceToPdfSpec(trialBalance, periodsCaption) {
  return {
    documentTitle: 'Trial Balance',
    eyebrow: 'Accounting',
    periodsCaption,
    periodLabels: ['Debit', 'Credit'],
    summaryTiles: [
      { label: 'Total Debits', value: trialBalance.totalDebit },
      { label: 'Total Credits', value: trialBalance.totalCredit },
    ],
    sections: [
      {
        key: 'accounts',
        label: 'Accounts',
        color: '#38bdf8',
        records: trialBalance.rows.map((row) => ({
          name: row.name,
          values: [row.debit, row.credit],
          total: row.debit || row.credit,
        })),
        subtotal: { values: [trialBalance.totalDebit, trialBalance.totalCredit], total: trialBalance.totalDebit },
      },
    ],
    totalsRow: null,
  }
}

export function trialBalanceToCsvRows(trialBalance) {
  const rows = []
  trialBalance.rows.forEach((row) => rows.push([row.name, row.debit.toFixed(2), row.credit.toFixed(2)]))
  rows.push(['Total', trialBalance.totalDebit.toFixed(2), trialBalance.totalCredit.toFixed(2)])
  return { headers: ['Account', 'Debit', 'Credit'], rows }
}
