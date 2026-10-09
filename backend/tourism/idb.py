"""Inter-American Development Bank (data.iadb.org, a CKAN portal) — configurable dataset connector.

Only the documented CKAN action API is used:
  datastore_search  (resource_id, limit, offset)  -> {"success": true, "result": {"records": [...], "total": n, "fields": [...]}}
  resource_show     (id)                          -> dataset/resource metadata
Which IDB dataset holds which indicator is NOT assumed: it is declared in `idb_registry.json` next to this file (empty by default):
  {"datasets": [{"indicator": "TOURISM_RECEIPTS", "resource_id": "<uuid>", "country_field": "iso3", "country_kind": "iso3|iso2|name",
                 "year_field": "year", "value_field": "value", "unit": "USD", "definition_matches": true, "dataset_name": "...", "edition": "..."}]}
`definition_matches` must be set to true by a person who has checked that the dataset's definition equals the module's indicator definition;
otherwise the dataset is ignored. IDB coverage is mainly Latin America and the Caribbean; other countries are simply not found.
"""

import json
from pathlib import Path

from . import http
from .constants import INDICATORS

BASE_URL = 'https://data.iadb.org/api/action'
REGISTRY_FILE = Path(__file__).resolve().parent / 'idb_registry.json'
PAGE = 1000
REQUIRED = {'indicator', 'resource_id', 'country_field', 'country_kind', 'year_field', 'value_field', 'unit'}


def load_registry() -> list[dict]:
    if not REGISTRY_FILE.exists():
        return []
    try:
        datasets = json.loads(REGISTRY_FILE.read_text(encoding='utf-8')).get('datasets', [])
    except (OSError, ValueError):
        return []
    return [d for d in datasets if REQUIRED <= set(d) and d['indicator'] in INDICATORS and d.get('definition_matches') is True and d['country_kind'] in ('iso2', 'iso3', 'name')]


def resource_metadata(resource_id: str) -> dict:
    data = http.get_json(f'{BASE_URL}/resource_show', {'id': resource_id}, ttl_hours=24 * 7)
    if not isinstance(data, dict) or not data.get('success'):
        raise http.ProviderError('IDB resource_show failed.')
    return data['result']


def fetch_records(resource_id: str) -> list[dict]:
    """Every record of a datastore resource, following the offset pagination."""
    records: list[dict] = []
    offset = 0
    while True:
        data = http.get_json(f'{BASE_URL}/datastore_search', {'resource_id': resource_id, 'limit': PAGE, 'offset': offset})
        if not isinstance(data, dict) or not data.get('success'):
            raise http.ProviderError('IDB datastore_search failed.')
        result = data['result']
        batch = result.get('records', [])
        records.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(result.get('total', 0)):
            break
    return records


def normalize(dataset: dict, records: list[dict]) -> list[dict]:
    """Rows {key, kind, year, value_text} using only the fields the registry names; rows with a missing/non-numeric year or value are dropped."""
    rows = []
    for record in records:
        key, year, value = record.get(dataset['country_field']), record.get(dataset['year_field']), record.get(dataset['value_field'])
        try:
            year = int(str(year)[:4])
        except (TypeError, ValueError):
            continue
        if key in (None, '') or value in (None, ''):
            continue
        rows.append({'key': str(key).strip(), 'kind': dataset['country_kind'], 'year': year, 'value_text': str(value)})
    return rows
