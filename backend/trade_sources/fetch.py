"""Fetch dispatch for routers/comtrade.py's three data endpoints
(/api/trade/categories, /products, /subheadings) — branches on a country's
stored `trade_data_source` (CountryReferenceCatalog, set once by
discovery.py) so those endpoints can serve either UN Comtrade or a
fallback tier's data through the identical row shape
({hs_code, category_name|description, value}), with no special-casing
downstream. A country with no catalog row, or no trade_data_source
discovered yet (None), is treated exactly like 'comtrade' — this only
changes behavior for a country discovery has actually run for."""

from ..comtrade import client as comtrade_client
from . import fred_client

_FRED_CATEGORY_ROW = {
    'hs_code': 'TOTAL',
    'category_name': 'All commodities (US Census/FRED bilateral total)',
}


def _fred_categories(db, catalog_row, year: int, flow: str) -> list[dict]:
    series = fred_client.find_series_ids(catalog_row.country_code, catalog_row.name)
    if not series:
        return []
    value = fred_client.fetch_total(db, catalog_row.country_code, series[0], series[1], year, flow)
    if value is None:
        return []
    return [{**_FRED_CATEGORY_ROW, 'value': value}]


def fetch_categories(db, catalog_row, reporter_code: int, year: int, flow: str) -> list[dict]:
    source = catalog_row.trade_data_source if catalog_row else None
    if source in (None, 'comtrade'):
        return comtrade_client.fetch_categories(db, reporter_code, year, flow)
    if source == 'us_census_fred':
        return _fred_categories(db, catalog_row, year, flow)
    # 'none_found', or a registered-but-not-yet-integrated tier 1/2 source
    # (see trade_sources/registry.py) — nothing to serve.
    return []


def fetch_products(db, catalog_row, reporter_code: int, year: int, flow: str, chapter: str) -> list[dict]:
    source = catalog_row.trade_data_source if catalog_row else None
    if source in (None, 'comtrade'):
        return comtrade_client.fetch_products(db, reporter_code, year, flow, chapter)
    # Every fallback tier built so far offers only an aggregate total, no
    # HS product-level breakdown (see fred_client.py's module docstring).
    return []


def fetch_subheadings(db, catalog_row, reporter_code: int, year: int, flow: str, heading: str) -> list[dict]:
    source = catalog_row.trade_data_source if catalog_row else None
    if source in (None, 'comtrade'):
        return comtrade_client.fetch_subheadings(db, reporter_code, year, flow, heading)
    return []
