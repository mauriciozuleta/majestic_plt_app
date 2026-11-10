"""The small, frozen slice of the real data the JavaScript parity fixtures are captured on, and the way to load it into any database (the throwaway server of the
capture, or an in-memory database in a test). Read from the real database ONLY by `export_inputs` (read-only); nothing here writes to it."""

import json
import sqlite3
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'js_parity'
INPUTS_FILE = FIXTURES / 'inputs.json'

COUNTRIES = ('Colombia', 'United States', 'Jamaica')
SNAPSHOTS = ('la_mayorista', 'corabastos', 'usa_beef', 'usa_pork', 'usa_poultry', 'usa_eggs', 'usa_grains', 'usa_produce_fl', 'usa_produce_ca', 'usa_retail_produce')
# two small Jamaica sources (the smallest by product count) stand in for "a country added in Settings"
CUSTOM_SOURCES_PER_COUNTRY = {'Jamaica': 2}


def _rows(connection: sqlite3.Connection, query: str, args=()) -> list[dict]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, args).fetchall()]


def export_inputs(real_db: Path) -> dict:
    connection = sqlite3.connect(f'file:{Path(real_db).as_posix()}?mode=ro', uri=True)
    marks = ','.join('?' for _ in COUNTRIES)
    inputs = {'country_reference_catalog': _rows(connection, f'SELECT * FROM country_reference_catalog WHERE name IN ({marks})', COUNTRIES)}
    sources = []
    for country, count in CUSTOM_SOURCES_PER_COUNTRY.items():
        sources += _rows(connection, 'SELECT * FROM product_sources WHERE country_name = ? AND product_count > 0 ORDER BY product_count ASC LIMIT ?', (country, count))
    inputs['product_sources'] = sources
    keys = list(SNAPSHOTS) + [f"custom_{source['id']}" for source in sources]
    marks = ','.join('?' for _ in keys)
    inputs['price_comparison_snapshots'] = _rows(connection, f'SELECT * FROM price_comparison_snapshots WHERE source IN ({marks})', keys)
    inputs['product_translation_overrides'] = _rows(connection, 'SELECT * FROM product_translation_overrides')
    inputs['builtin_product_source_overrides'] = _rows(connection, 'SELECT * FROM built_in_source_overrides')
    connection.close()
    return inputs


def load_inputs(session, inputs: dict) -> None:
    """Inserts the frozen rows into the (empty) tables of `session`'s database."""
    from backend import models

    tables = {'country_reference_catalog': models.CountryReferenceCatalog, 'product_sources': models.ProductSource, 'price_comparison_snapshots': models.PriceComparisonSnapshot,
              'product_translation_overrides': models.ProductTranslationOverride, 'builtin_product_source_overrides': models.BuiltInProductSourceOverride}
    for name, model in tables.items():
        for row in inputs.get(name, []):
            session.add(model(**row))
    session.commit()


def read_inputs() -> dict:
    return json.loads(INPUTS_FILE.read_text(encoding='utf-8'))
