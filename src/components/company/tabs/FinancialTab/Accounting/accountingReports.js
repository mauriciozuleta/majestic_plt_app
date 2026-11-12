// What is left of the client-side ledger code. The statements themselves (trial balance, income statement, balance sheet, cash flow) are worked out on the SERVER now
// (backend/accounting_reports/, src/services/accountingReports.js); the JavaScript that did it is in git history (see the diary's commit log), and its frozen answers are
// the parity fixture backend/tests/fixtures/js_parity/accounting_outputs.json. What stays here: the export formats (CSV rows, PDF specs) and the condensed general-ledger
// summary of the entries the General Ledger screen has FILTERED on screen (the server has the same summary for the whole ledger: GET .../gl/reports/general-ledger-summary).

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
