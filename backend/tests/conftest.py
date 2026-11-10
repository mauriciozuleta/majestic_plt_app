"""Test-wide setup: the data history writes to its own SQLite file; tests must never touch the real `majestic_history.db` of the project."""

import tempfile
from pathlib import Path

from backend.data_history import store

_TEST_HISTORY = tempfile.TemporaryDirectory(prefix='majestic_history_tests_')
store.use_database(Path(_TEST_HISTORY.name) / 'history.db')
