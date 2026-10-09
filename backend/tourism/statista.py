"""Statista REST API — optional, authenticated, server-side only (docs: docs.platform.statista.ai, access: statista.com/business/connect-rest-api).

No endpoint path is hardcoded here: which endpoints a Statista account may call depends on its subscription. The account's documented endpoints
are declared in `statista_registry.json` next to this file (not committed; empty by default):
  {"base_url": "<from the account docs>", "auth_header": "Authorization", "auth_prefix": "Bearer ",
   "datasets": [{"indicator": "TOURISM_GDP_TOTAL_PCT", "path": "<documented path>", "params": {...}, "records_path": "data",
                 "country_field": "...", "country_kind": "iso2|iso3|name", "year_field": "...", "value_field": "...", "unit": "%",
                 "definition_matches": true, "dataset_name": "...", "edition": "...", "attribution": "Source: Statista ..."}]}
The key is read from the environment (STATISTA_API_KEY) and never sent to the browser. Without key or registry the connector is disabled.
Statista's licence/attribution text is stored with each observation (methodology_note) and shown wherever the value is shown.
"""

import json
import os
from pathlib import Path

from . import http
from .constants import INDICATORS

REGISTRY_FILE = Path(__file__).resolve().parent / 'statista_registry.json'
REQUIRED = {'indicator', 'path', 'records_path', 'country_field', 'country_kind', 'year_field', 'value_field', 'unit'}


def api_key() -> str | None:
    return os.environ.get('STATISTA_API_KEY') or None


def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {'base_url': '', 'datasets': []}
    try:
        registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'base_url': '', 'datasets': []}
    registry['datasets'] = [d for d in registry.get('datasets', []) if REQUIRED <= set(d) and d['indicator'] in INDICATORS and d.get('definition_matches') is True]
    return registry


def status() -> tuple[str, str]:
    """(connection_status, detail) without calling Statista."""
    if not api_key():
        return 'disabled', 'No STATISTA_API_KEY in the server environment (.env). The connector is off.'
    registry = load_registry()
    if not registry.get('base_url') or not registry['datasets']:
        return 'not_configured', 'Key present, but statista_registry.json declares no documented endpoint for this account.'
    return 'configured', f"{len(registry['datasets'])} dataset(s) registered."


def fetch(dataset: dict, registry: dict) -> list[dict]:
    """Rows {key, kind, year, value_text} of one registered dataset (one request; quotas and rate limits surface as ProviderError)."""
    key = api_key()
    if not key:
        raise http.ProviderError('Statista key missing.')
    headers = {registry.get('auth_header', 'Authorization'): f"{registry.get('auth_prefix', 'Bearer ')}{key}"}
    url = registry['base_url'].rstrip('/') + '/' + dataset['path'].lstrip('/')
    data = http.get_json(url, dataset.get('params') or {}, headers=headers, ttl_hours=24, retries=2)
    for step in [part for part in dataset['records_path'].split('.') if part]:
        data = data.get(step) if isinstance(data, dict) else None
    if not isinstance(data, list):
        raise http.ProviderError('Statista answer did not contain the registered records_path.')
    rows = []
    for record in data:
        try:
            year = int(str(record.get(dataset['year_field']))[:4])
        except (TypeError, ValueError):
            continue
        value = record.get(dataset['value_field'])
        country = record.get(dataset['country_field'])
        if value in (None, '') or country in (None, ''):
            continue
        rows.append({'key': str(country).strip(), 'kind': dataset['country_kind'], 'year': year, 'value_text': str(value)})
    return rows
