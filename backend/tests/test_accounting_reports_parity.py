"""The Python financial statements give exactly what the original JavaScript (accountingReports.js) gave, on a real company's ledger (1,273 entries) and on hand-made edge cases
(an account against its normal side, a missing cash account, an investing entry, retained earnings, amounts under the 0.004 threshold, empty ledgers)."""

import json
import unittest
from pathlib import Path

from backend.accounting_reports import reports

FIXTURES = Path(__file__).parent / 'fixtures' / 'js_parity'
INPUTS = json.loads((FIXTURES / 'accounting_inputs.json').read_text(encoding='utf-8'))
OUTPUTS = json.loads((FIXTURES / 'accounting_outputs.json').read_text(encoding='utf-8'))


def same(case, python, javascript, path='') -> None:
    """Deep equality; 0 == -0. Floats must be identical, not just close: the sums run in the same order as the JavaScript."""
    case.assertEqual(type(python) is dict, type(javascript) is dict, path)
    if isinstance(javascript, dict):
        case.assertEqual(set(python), set(javascript), path)
        for key in javascript:
            same(case, python[key], javascript[key], f'{path}.{key}')
    elif isinstance(javascript, list):
        case.assertEqual(len(python), len(javascript), path)
        for index, (a, b) in enumerate(zip(python, javascript)):
            same(case, a, b, f'{path}[{index}]')
    else:
        case.assertEqual(python, javascript, path)


class AccountingReportsParityTests(unittest.TestCase):
    def test_every_statement_matches_the_javascript_on_every_ledger_and_period(self):
        compared = 0
        for name, ledger in INPUTS['datasets'].items():
            accounts, entries, expected = ledger['accounts'], ledger['entries'], OUTPUTS[name]
            same(self, reports.build_trial_balance(accounts, entries), expected['trialBalance'], f'{name}.trialBalance')
            same(self, reports.build_general_ledger_summary(accounts, entries), expected['generalLedgerSummary'], f'{name}.generalLedgerSummary')
            for index, period in enumerate(INPUTS['scenarios']['ranges']):
                start, end = period.get('startDate'), period.get('endDate')
                same(self, reports.build_income_statement(accounts, entries, start, end), expected['incomeStatement'][index], f'{name}.incomeStatement[{index}]')
                same(self, reports.build_cash_flow_statement(accounts, entries, start, end), expected['cashFlow'][index], f'{name}.cashFlow[{index}]')
                compared += 2
            for index, as_of in enumerate(INPUTS['scenarios']['asOf']):
                same(self, reports.build_balance_sheet(accounts, entries, as_of), expected['balanceSheet'][index], f'{name}.balanceSheet[{index}]')
                compared += 1
        self.assertGreater(compared, 50)

    def test_the_real_ledger_balances(self):
        ledger = INPUTS['datasets']['real_company']
        self.assertTrue(reports.build_trial_balance(ledger['accounts'], ledger['entries'])['balanced'])
        self.assertTrue(reports.build_balance_sheet(ledger['accounts'], ledger['entries'])['balanced'])

    def test_the_hand_made_ledger_by_hand(self):
        ledger = INPUTS['datasets']['synthetic']
        income = reports.build_income_statement(ledger['accounts'], ledger['entries'])
        # revenue 2,500.55 + 0.001 + 0.1 + 0.005 on the Revenue account, less the 100.25 discount; Direct production COGS (5900) 750 is cost of goods sold; the expense
        # accounts of 0.003 (dropped), 0.0040000005 and 0.0042 (kept) sit around the 0.004 threshold
        self.assertAlmostEqual(income['sections'][0]['subtotal'], 2500.55 + 0.001 + 0.1 + 0.005 - 100.25, places=6)
        self.assertAlmostEqual(income['sections'][1]['subtotal'], 1800.0 + 750.0, places=6)
        self.assertEqual([section['key'] for section in income['sections']], ['revenue', 'cogs', 'opex'])
        self.assertEqual(sorted(row['name'] for row in income['sections'][2]['rows']), ['Edge expense', 'Fuel', 'Small expense'])
        cash = reports.build_cash_flow_statement(ledger['accounts'], ledger['entries'])
        self.assertEqual([section['key'] for section in cash['sections']], ['operating', 'investing'])
        self.assertAlmostEqual(cash['sections'][1]['subtotal'], -4000.0)  # the equipment purchase


if __name__ == '__main__':
    unittest.main()
