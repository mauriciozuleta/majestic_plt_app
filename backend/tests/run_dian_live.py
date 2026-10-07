"""`npm run test:dian-live`: runs the live DIAN test (manual; calls the real site once)."""

import os
import sys
import unittest
from pathlib import Path

os.environ['DIAN_LIVE'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

suite = unittest.defaultTestLoader.loadTestsFromName('backend.tests.test_dian_live')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
