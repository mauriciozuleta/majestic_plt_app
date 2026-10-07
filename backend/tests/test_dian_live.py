"""LIVE test against the real DIAN site. Manual only: skipped unless DIAN_LIVE=1 (run it with `npm run test:dian-live`).
It is excluded from the default suite so no automated run ever calls DIAN."""

import os
import unittest

from backend.tax_calc.colombia_dian.dian_types import TaxLookupRequest
from backend.tax_calc.colombia_dian.service import service


@unittest.skipUnless(os.environ.get('DIAN_LIVE') == '1', 'live DIAN test: set DIAN_LIVE=1 (npm run test:dian-live)')
class LiveTests(unittest.TestCase):
    def test_fresh_tomatoes(self):
        events = []
        result = service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000', forceRefresh=True, onProgress=events.append))
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['query']['resolvedHsCode'], '0702000000')
        self.assertEqual(result['gravamen']['unit'], 'percent')
        self.assertIsNotNone(result['gravamen']['rate'])
        self.assertIsNotNone(result['gravamen']['validFrom'])
        self.assertEqual(result['ivaStatus'], 'listed')
        self.assertEqual([event.step for event in events], ['connecting', 'searching', 'resolving', 'gravamen', 'iva', 'complete'])
        print('\nLIVE 0702000000: Gravamen', result['gravamen']['formulaRaw'], '| IVA', result['iva']['formulaRaw'])


if __name__ == '__main__':
    unittest.main()
