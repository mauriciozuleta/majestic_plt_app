"""The financial statements endpoint: the ledger is read from the database and each statement comes back for the whole ledger or a period. Numbers worked out by hand."""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import Base, get_db
from backend.routers import accounting_reports, general_ledger

COMPANY = 'c1'


class AccountingReportsApiTests(unittest.TestCase):
    def setUp(self):
        database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(database)
        self.db = sessionmaker(bind=database)()
        self.addCleanup(self.db.close)
        app = FastAPI()
        app.include_router(general_ledger.router)
        app.include_router(accounting_reports.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        # the default chart of accounts is created the first time the accounts are listed
        self.ids = {account['code']: account['id'] for account in self.client.get(f'/companies/{COMPANY}/gl/accounts').json()}

    def post(self, key, date, memo, *lines):
        self.db.add(models.JournalEntry(id=key, company_id=COMPANY, entry_date=date, memo=memo))
        for index, (code, debit, credit) in enumerate(lines):
            self.db.add(models.JournalLine(id=f'{key}-{index}', journal_entry_id=key, account_id=self.ids[code], debit=debit, credit=credit))
        self.db.commit()

    def report(self, kind, **params):
        response = self.client.get(f'/companies/{COMPANY}/gl/reports/{kind}', params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_statements_of_a_small_ledger(self):
        self.assertIn('1000', self.ids)
        revenue_code = next(code for code in self.ids if code.startswith('4'))
        # 10,000 of capital into cash; a 2,000 sale for cash in February
        capital_code = next(code for code in self.ids if code.startswith('3'))
        self.post('e1', '0001-01-01', 'Capital', ('1000', 10000.0, 0.0), (capital_code, 0.0, 10000.0))
        self.post('e2', '0001-02-10', 'Sale', ('1000', 2000.0, 0.0), (revenue_code, 0.0, 2000.0))
        trial = self.report('trial-balance')
        self.assertTrue(trial['balanced'])
        self.assertEqual((trial['totalDebit'], trial['totalCredit']), (12000.0, 12000.0))
        income = self.report('income-statement')
        self.assertEqual(income['metrics'][1], {'label': 'Net Income', 'amount': 2000.0, 'primary': True})
        # a period without the sale has no revenue
        self.assertEqual(self.report('income-statement', end_date='0001-01-31')['sections'], [])
        sheet = self.report('balance-sheet', as_of_date='0001-01-31')
        self.assertEqual(sheet['metrics'][0]['amount'], 10000.0)
        self.assertTrue(sheet['balanced'])
        # the sale is an operating cash inflow of 2,000, the capital 10,000 (no investing activity)
        cash = self.report('cash-flow')
        self.assertEqual([section['key'] for section in cash['sections']], ['operating'])
        self.assertEqual(cash['metrics'][0]['amount'], 12000.0)
        summary = self.report('general-ledger-summary')
        self.assertEqual({section['key'] for section in summary['sections']}, {'asset', 'equity', 'revenue'})

    def test_an_empty_ledger_and_an_unknown_statement(self):
        self.assertEqual(self.report('trial-balance')['rows'], [])
        self.assertEqual(self.client.get(f'/companies/{COMPANY}/gl/reports/nonsense').status_code, 404)


if __name__ == '__main__':
    unittest.main()
