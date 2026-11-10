"""A throwaway backend over a database built from the frozen parity inputs (run by capture.py; never touches the real database or the real history file).
Usage: python -m backend.tests.js_parity.serve <db file> <history file> <port>"""

import os
import sys
from pathlib import Path

db_file, history_file, port = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
os.environ['MAJESTIC_HISTORY_DB'] = history_file

from sqlalchemy import create_engine  # noqa: E402

import backend.database as database  # noqa: E402

database.engine = create_engine(f'sqlite:///{db_file.as_posix()}', connect_args={'check_same_thread': False})
database.SessionLocal.configure(bind=database.engine)

import uvicorn  # noqa: E402

from backend.main import app  # noqa: E402

uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
