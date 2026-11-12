"""Freezes what the ORIGINAL JavaScript financial statements (src/components/company/tabs/FinancialTab/Accounting/accountingReports.js) produce, so the Python port
(backend/accounting_reports/) can be held to exactly the same numbers.

    python -m backend.tests.js_parity.accounting_capture --refresh-inputs   # re-read the ledger of the real database (a COPY) and the synthetic cases, then capture
    python -m backend.tests.js_parity.accounting_capture                    # capture the JavaScript's answers for the frozen inputs
    python -m backend.tests.js_parity.accounting_capture --compare          # run the CURRENT JavaScript again and say whether it still matches the frozen answers

Inputs  -> backend/tests/fixtures/js_parity/accounting_inputs.json   { datasets: { name: { accounts, entries } }, scenarios }
Outputs -> backend/tests/fixtures/js_parity/accounting_outputs.json  { name: { trialBalance, generalLedgerSummary, incomeStatement: [...], balanceSheet: [...], cashFlow: [...] } }
Never delete those fixtures. Needs node (the JavaScript file has no imports)."""

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'backend' / 'tests' / 'fixtures' / 'js_parity'
INPUTS, OUTPUTS = FIXTURES / 'accounting_inputs.json', FIXTURES / 'accounting_outputs.json'
JS_FILE = ROOT / 'src' / 'components' / 'company' / 'tabs' / 'FinancialTab' / 'Accounting' / 'accountingReports.js'

# one real company (the biggest ledger) + hand-made edge cases
REAL_COMPANY = 'fresh24-1788630345959'

RUNNER = """
import fs from 'node:fs'
import { pathToFileURL } from 'node:url'
const reports = await import(pathToFileURL(process.argv[2]).href)
const { datasets, scenarios } = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'))
const out = {}
for (const [name, { accounts, entries }] of Object.entries(datasets)) {
  out[name] = {
    trialBalance: reports.buildTrialBalance(accounts, entries),
    generalLedgerSummary: reports.buildGeneralLedgerSummary(accounts, entries),
    incomeStatement: scenarios.ranges.map((range) => reports.buildIncomeStatement(accounts, entries, range)),
    cashFlow: scenarios.ranges.map((range) => reports.buildCashFlowStatement(accounts, entries, range)),
    balanceSheet: scenarios.asOf.map((asOfDate) => reports.buildBalanceSheet(accounts, entries, asOfDate === null ? {} : { asOfDate })),
  }
}
fs.writeFileSync(process.argv[4], JSON.stringify(out))
"""


def account(code, name, kind, normal, key=None):
    return {'id': key or f'a{code}', 'code': code, 'name': name, 'account_type': kind, 'normal_balance': normal}


def entry(key, date, memo, *lines):
    return {'id': key, 'entry_date': date, 'memo': memo, 'lines': [{'account_id': a, 'debit': d, 'credit': c} for a, d, c in lines]}


def synthetic() -> dict:
    accounts = [account('1000', 'Cash', 'asset', 'debit'), account('1100', 'Accounts Receivable', 'asset', 'debit'), account('1500', 'Equipment', 'asset', 'debit'),
                account('2000', 'Accounts Payable', 'liability', 'credit'), account('3000', "Owner's Capital", 'equity', 'credit'),
                account('4000', 'Revenue', 'revenue', 'credit'), account('4900', 'Discounts', 'contra_revenue', 'debit'),
                account('5000', 'Cost of Goods Sold', 'expense', 'debit'), account('5900', 'Direct production COGS', 'expense', 'debit'), account('6000', 'Fuel', 'expense', 'debit'), account('6100', 'Unused', 'expense', 'debit'),
                account('6200', 'Tiny expense', 'expense', 'debit'), account('6300', 'Edge expense', 'expense', 'debit'), account('6400', 'Small expense', 'expense', 'debit')]
    entries = [
        entry('e1', '0001-01-01', "Owner's capital", ('a1000', 10000.0, 0.0), ('a3000', 0.0, 10000.0)),
        entry('e2', '0001-02-10', 'Sale', ('a1100', 2500.55, 0.0), ('a4000', 0.0, 2500.55)),
        entry('e3', '0001-02-20', 'Early payment discount', ('a4900', 100.25, 0.0), ('a1100', 0.0, 100.25)),
        entry('e4', '0001-03-05', 'Aircraft part', ('a1500', 4000.0, 0.0), ('a1000', 0.0, 4000.0)),
        entry('e5', '0001-03-15', 'Fuel', ('a6000', 3200.1, 0.0), ('a1000', 0.0, 3200.1)),
        entry('e6', '0001-04-01', 'Inventory sold', ('a5000', 1800.0, 0.0), ('a2000', 0.0, 1800.0)),
        entry('e7', '0001-04-02', '', ('a1000', 0.0, 9000.0), ('a2000', 9000.0, 0.0)),  # cash goes negative, no memo
        entry('e8', '0002-01-01', 'Cash line only', ('a1000', 0.001, 0.0), ('a4000', 0.0, 0.001)),  # below the 0.004 threshold
        entry('e9', '0002-06-30', 'Collected', ('a1000', 2400.3, 0.0), ('a1100', 0.0, 2400.3)),
        entry('e10', '0002-07-01', 'Direct production', ('a5900', 750.0, 0.0), ('a2000', 0.0, 750.0)),
        entry('e11', '0002-07-02', 'Small cash movement', ('a1000', 0.1, 0.0), ('a4000', 0.0, 0.1)),
        entry('e12', '0002-07-03', 'Cash just over the threshold', ('a1000', 0.005, 0.0), ('a4000', 0.0, 0.005)),
        entry('e13', '0002-07-04', 'Below threshold expense', ('a6200', 0.003, 0.0), ('a2000', 0.0, 0.003)),
        entry('e14', '0002-07-05', 'Right at the threshold', ('a6300', 0.0040000005, 0.0), ('a2000', 0.0, 0.0040000005)),
        entry('e15', '0002-07-06', 'Just above the threshold', ('a6400', 0.0042, 0.0), ('a2000', 0.0, 0.0042)),
    ]
    no_cash = {'accounts': [a for a in accounts if a['code'] != '1000'], 'entries': [{**e, 'lines': [line for line in e['lines'] if line['account_id'] != 'a1000'] or e['lines']} for e in entries]}
    return {'synthetic': {'accounts': accounts, 'entries': entries}, 'synthetic_no_cash_account': no_cash, 'synthetic_empty': {'accounts': accounts, 'entries': []}}


def real_ledger() -> dict:
    work = Path(tempfile.mkdtemp(prefix='acct_'))
    shutil.copy(ROOT / 'majestic_plt.db', work / 'c.db')
    con = sqlite3.connect(work / 'c.db')
    accounts = [dict(zip(('id', 'code', 'name', 'account_type', 'normal_balance'), row)) for row in con.execute(
        'select id, code, name, account_type, normal_balance from general_ledger_accounts where company_id=? order by code', (REAL_COMPANY,))]
    entries = []
    for entry_id, date, memo in con.execute('select id, entry_date, memo from journal_entries where company_id=? order by entry_date, id', (REAL_COMPANY,)):
        lines = [{'account_id': a, 'debit': d, 'credit': c} for a, d, c in con.execute('select account_id, debit, credit from journal_lines where journal_entry_id=?', (entry_id,))]
        entries.append({'id': entry_id, 'entry_date': date, 'memo': memo, 'lines': lines})
    con.close()
    shutil.rmtree(work, ignore_errors=True)
    return {'real_company': {'accounts': accounts, 'entries': entries}}


SCENARIOS = {
    'ranges': [{}, {'startDate': '0001-03-01'}, {'endDate': '0002-12-30'}, {'startDate': '0001-03-01', 'endDate': '0001-04-01'}, {'startDate': '0099-01-01', 'endDate': '0099-12-30'}],
    'asOf': [None, '0001-03-10', '0002-01-01', '0099-01-01'],
}


def run_javascript() -> dict:
    work = Path(tempfile.mkdtemp(prefix='acct_js_'))
    (work / 'run.mjs').write_text(RUNNER, encoding='utf-8')
    subprocess.run(['node', str(work / 'run.mjs'), str(JS_FILE), str(INPUTS), str(work / 'out.json')], check=True, cwd=work)
    result = json.loads((work / 'out.json').read_text(encoding='utf-8'))
    shutil.rmtree(work, ignore_errors=True)
    return result


def main() -> None:
    args = sys.argv[1:]
    if '--refresh-inputs' in args or not INPUTS.exists():
        INPUTS.write_text(json.dumps({'datasets': {**real_ledger(), **synthetic()}, 'scenarios': SCENARIOS}), encoding='utf-8')
        print('inputs written:', INPUTS.name)
    outputs = run_javascript()
    if '--compare' in args:
        same = json.loads(OUTPUTS.read_text(encoding='utf-8')) == outputs
        print('the current JavaScript', 'STILL MATCHES the frozen answers' if same else 'DIFFERS from the frozen answers')
        sys.exit(0 if same else 1)
    OUTPUTS.write_text(json.dumps(outputs), encoding='utf-8')
    print('outputs written:', OUTPUTS.name, {name: len(data['incomeStatement']) for name, data in outputs.items()})


if __name__ == '__main__':
    main()
