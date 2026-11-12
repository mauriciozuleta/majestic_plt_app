"""The accounting treatments exist twice: the Commercial Operations form offers them (src/.../CommercialOperationsView/accountingTreatments.js) and the accounting auditor accepts
them (backend/accounting_auditor.py VALID_TREATMENTS). A key added to one and not the other would let the form save an entry the auditor flags as invalid (or the reverse):
this test keeps the two lists equal."""

import re
import unittest
from pathlib import Path

from backend.accounting_auditor import VALID_TREATMENTS

JS_FILE = Path(__file__).resolve().parents[2] / 'src' / 'components' / 'company' / 'tabs' / 'OperationsTab' / 'CommercialOperationsView' / 'accountingTreatments.js'
JS_LISTS = {'revenue': 'REVENUE_TREATMENTS', 'cos': 'COS_TREATMENTS', 'expenses': 'EXPENSE_TREATMENTS'}


def keys_in(source: str, name: str) -> set[str]:
    block = re.search(rf'export const {name} = \[(.*?)\n\]', source, re.S).group(1)
    return set(re.findall(r"^\s{4}key: '([a-z_]+)'", block, re.M))


class TreatmentsInSyncTests(unittest.TestCase):
    def test_the_form_and_the_auditor_know_the_same_treatments(self):
        source = JS_FILE.read_text(encoding='utf-8')
        for category, name in JS_LISTS.items():
            self.assertEqual(keys_in(source, name), set(VALID_TREATMENTS[category]), category)


if __name__ == '__main__':
    unittest.main()
