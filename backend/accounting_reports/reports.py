"""Pure derivation over a ledger — `accounts` [{id, code, name, account_type, normal_balance}] and `entries` [{entry_date, memo, lines: [{account_id, debit, credit}]}] — into the
shape each statement view renders. A line for line port of accountingReports.js (the sums run in the same order, so the floats are identical); its output on the frozen
ledgers is the parity fixture (backend/tests/fixtures/js_parity/accounting_outputs.json)."""

COGS_CODES = {'5000', '5900'}
EPSILON = 0.004


def _in_range(entries, start_date, end_date):
    return [entry for entry in entries if (not start_date or entry['entry_date'] >= start_date) and (not end_date or entry['entry_date'] <= end_date)]


def _net_by_account(entries, sign) -> dict:
    """sign +1: debit minus credit; -1: credit minus debit."""
    totals: dict = {}
    for entry in entries:
        for line in entry['lines']:
            totals[line['account_id']] = (totals.get(line['account_id']) or 0) + sign * (line['debit'] - line['credit'])
    return totals


def _rows_for(accounts, totals, sign=1) -> list[dict]:
    rows = [{'name': account['name'], 'amount': sign * (totals.get(account['id']) or 0)} for account in accounts]
    return [row for row in rows if abs(row['amount']) > EPSILON]


def _sum(rows, key='amount'):
    total = 0
    for row in rows:
        total += row[key]
    return total


def build_trial_balance(accounts, entries) -> dict:
    totals: dict = {}
    for entry in entries:
        for line in entry['lines']:
            bucket = totals.setdefault(line['account_id'], {'debit': 0, 'credit': 0})
            bucket['debit'] += line['debit']
            bucket['credit'] += line['credit']
    # the net debit-minus-credit decides the column: an account against its normal side must still show up, or the trial balance cannot prove debits equal credits
    rows = []
    for account in accounts:
        if account['id'] not in totals:
            continue
        net = totals[account['id']]['debit'] - totals[account['id']]['credit']
        row = {'name': account['name'], 'debit': net if net > 0 else 0, 'credit': -net if net < 0 else 0}
        if row['debit'] > EPSILON or row['credit'] > EPSILON:
            rows.append(row)
    total_debit, total_credit = _sum(rows, 'debit'), _sum(rows, 'credit')
    return {'rows': rows, 'totalDebit': total_debit, 'totalCredit': total_credit, 'balanced': abs(total_debit - total_credit) < 0.01}


def build_income_statement(accounts, entries, start_date=None, end_date=None) -> dict:
    totals = _net_by_account(_in_range(entries, start_date, end_date), -1)  # credit minus debit: positive for revenue
    revenue_rows = _rows_for([a for a in accounts if a['account_type'] in ('revenue', 'contra_revenue')], totals)
    cogs_rows = _rows_for([a for a in accounts if a['account_type'] == 'expense' and a['code'] in COGS_CODES], totals, -1)
    opex_rows = _rows_for([a for a in accounts if a['account_type'] == 'expense' and a['code'] not in COGS_CODES], totals, -1)
    revenue_total, cogs_total, opex_total = _sum(revenue_rows), _sum(cogs_rows), _sum(opex_rows)
    gross_profit = revenue_total - cogs_total
    net_income = gross_profit - opex_total
    sections = [{'key': 'revenue', 'label': 'Revenue', 'color': '#35D399', 'rows': revenue_rows, 'subtotal': revenue_total},
                {'key': 'cogs', 'label': 'Cost of Goods Sold', 'color': '#f59e0b', 'rows': cogs_rows, 'subtotal': cogs_total},
                {'key': 'opex', 'label': 'Operating Expenses', 'color': '#f87171', 'rows': opex_rows, 'subtotal': opex_total}]
    return {'title': 'Income Statement', 'sections': [section for section in sections if section['rows']],
            'metrics': [{'label': 'Gross Profit', 'amount': gross_profit}, {'label': 'Net Income', 'amount': net_income, 'primary': True}]}


def build_balance_sheet(accounts, entries, as_of_date=None) -> dict:
    filtered = [entry for entry in entries if entry['entry_date'] <= as_of_date] if as_of_date else entries
    totals = _net_by_account(filtered, 1)  # debit minus credit: positive for assets, negative for liabilities
    asset_rows = _rows_for([a for a in accounts if a['account_type'] == 'asset'], totals)
    asset_total = _sum(asset_rows)
    liability_rows = _rows_for([a for a in accounts if a['account_type'] == 'liability'], totals, -1)
    liability_total = _sum(liability_rows)
    # Equity: the posted equity accounts plus Retained Earnings, derived from the cumulative net income (nothing posts it: there is no period close)
    equity_account_rows = _rows_for([a for a in accounts if a['account_type'] == 'equity'], totals, -1)
    earnings = 0
    for account in accounts:
        if account['account_type'] in ('revenue', 'contra_revenue', 'expense'):
            earnings += totals.get(account['id']) or 0
    retained_earnings = -earnings
    equity_rows = [*equity_account_rows, *([{'name': 'Retained Earnings', 'amount': retained_earnings}] if abs(retained_earnings) > EPSILON else [])]
    equity_total = _sum(equity_account_rows) + retained_earnings
    sections = [{'key': 'assets', 'label': 'Assets', 'color': '#38bdf8', 'rows': asset_rows, 'subtotal': asset_total},
                {'key': 'liabilities', 'label': 'Liabilities', 'color': '#f87171', 'rows': liability_rows, 'subtotal': liability_total},
                {'key': 'equity', 'label': 'Equity', 'color': '#a78bfa', 'rows': equity_rows, 'subtotal': equity_total}]
    return {'title': 'Balance Sheet', 'sections': [section for section in sections if section['rows']],
            'metrics': [{'label': 'Total Assets', 'amount': asset_total}, {'label': 'Total Liabilities + Equity', 'amount': liability_total + equity_total}],
            'balanced': abs(asset_total - (liability_total + equity_total)) < 0.01}


def build_cash_flow_statement(accounts, entries, start_date=None, end_date=None) -> dict:
    cash = next((account for account in accounts if account['code'] == '1000'), None)
    if cash is None:
        return {'title': 'Cash Flow Statement', 'sections': [], 'metrics': []}
    accounts_by_id: dict = {}
    for account in accounts:
        accounts_by_id.setdefault(account['id'], account)  # the first one wins, as `find` does
    operating, investing = [], []
    for entry in _in_range(entries, start_date, end_date):
        cash_line = next((line for line in entry['lines'] if line['account_id'] == cash['id']), None)
        if cash_line is None:
            continue
        net_cash = cash_line['debit'] - cash_line['credit']
        if abs(net_cash) < EPSILON:
            continue
        other_line = next((line for line in entry['lines'] if line['account_id'] != cash['id']), None)
        other = accounts_by_id.get(other_line['account_id']) if other_line else None
        row = {'name': entry.get('memo') or (other['name'] if other else None) or 'Cash movement', 'amount': net_cash}
        (investing if other and other['code'] == '1500' else operating).append(row)
    operating_total, investing_total = _sum(operating), _sum(investing)
    sections = [{'key': 'operating', 'label': 'Operating Activities', 'color': '#35D399', 'rows': operating, 'subtotal': operating_total},
                {'key': 'investing', 'label': 'Investing Activities', 'color': '#38bdf8', 'rows': investing, 'subtotal': investing_total}]
    return {'title': 'Cash Flow Statement', 'sections': [section for section in sections if section['rows']],
            'metrics': [{'label': 'Net Change in Cash', 'amount': operating_total + investing_total, 'primary': True}]}


ACCOUNT_TYPE_LABELS = {'asset': 'Assets', 'liability': 'Liabilities', 'equity': 'Equity', 'revenue': 'Revenue', 'contra_revenue': 'Contra-Revenue', 'expense': 'Expenses'}
ACCOUNT_TYPE_ORDER = ['asset', 'liability', 'equity', 'revenue', 'contra_revenue', 'expense']


def build_general_ledger_summary(accounts, entries) -> dict:
    """The ending balance per account, grouped by account type."""
    totals: dict = {}
    for entry in entries:
        for line in entry['lines']:
            totals[line['account_id']] = (totals.get(line['account_id']) or 0) + (line['debit'] - line['credit'])
    sections = []
    for kind in ACCOUNT_TYPE_ORDER:
        rows = []
        for account in accounts:
            if account['account_type'] != kind or account['id'] not in totals:
                continue
            net = totals[account['id']] or 0
            amount = net if account['normal_balance'] == 'debit' else -net
            if abs(amount) > EPSILON:
                rows.append({'name': f"{account['code']} {account['name']}", 'amount': amount})
        if rows:
            sections.append({'key': kind, 'label': ACCOUNT_TYPE_LABELS[kind], 'color': '#38bdf8', 'rows': rows, 'subtotal': _sum(rows)})
    return {'title': 'General Ledger', 'sections': sections, 'metrics': []}
