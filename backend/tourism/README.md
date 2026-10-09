# Global Tourism & Economic Dependency — technical notes

Backend package `backend/tourism/`, API `routers/tourism.py` (prefix `/tourism`), UI = Tools ▸ **Tourism & Economic Dependency** plus the
**Tourism & Economy** column group in Market Analysis ▸ Country Information. Tests: `python -m unittest backend.tests.test_tourism` (mocked, no network).

## The indicators (six displayed, one supporting field)
| Code | Meaning | Unit | Allowed sources, in priority order |
|---|---|---|---|
| `TOURISM_GDP_TOTAL_PCT` | WTTC *total* contribution of travel & tourism to GDP (direct + indirect + induced) | % of GDP | WTTC file → Statista |
| `TOURISM_GDP_DIRECT_PCT` | tourism *direct* GDP as a proportion of total GDP — UN SDG 8.9.1, series `ST_GDP_ZS` | % of GDP | UN SDG API only |
| `TOURISM_EMPLOYMENT` | total contribution to employment | % of employment | WTTC file → Statista |
| `TOURISM_RECEIPTS` | international tourism receipts (`ST.INT.RCPT.CD`) | USD | World Bank → IDB → Statista |
| `TOURISM_DEPENDENCY` | receipts / GDP × 100, **same country and year** | % | Calculated |
| `POPULATION` | `SP.POP.TOTL` | persons | World Bank → IDB → Statista |
| `GDP_USD` (supporting) | `NY.GDP.MKTP.CD` | USD | World Bank → IDB → Statista |

`TOURISM_GDP_TOTAL_PCT`, `TOURISM_GDP_DIRECT_PCT` and `TOURISM_DEPENDENCY` (receipts ÷ GDP) are three different measures, stored, picked and exported separately. The direct share is never shown in the total column or the other way round (a stored row under the wrong source is ignored). Rows stored under the old code `TOURISM_GDP` (always WTTC total) are renamed automatically.
A source outside an indicator's list is never used for it; visitor arrivals, direct-only contributions and job counts are rejected at import.

## Providers (`backend/tourism/*.py`)
* **World Bank** (`worldbank.py`): `https://api.worldbank.org/v2/`, no key. Requests by alpha-3 code (`JAM;BRB;…`, 25 per request), `date=1990:<year>`, pagination
  by `pages`, disk cache 24 h (`cache/`), 3 attempts with exponential backoff (0.5 s, 1 s). Null values are dropped. Edition = the API's `lastupdated`.
* **UN Statistics Division — SDG API** (`unsd.py`): `https://unstats.un.org/SDGAPI/v1/sdg/`, no key. Series `ST_GDP_ZS` (SDG 8.9.1) feeds `TOURISM_GDP_DIRECT_PCT`. One bulk request (`Series/Data?seriesCode=ST_GDP_ZS&pageSize=2000&page=N`, paginated by `totalPages`) covers every country; it is repeated at most every 24 h (provider `last_sync`). Verified against the live API (2026-10): 1,669 records, 149 areas of which 128 map to registry countries/territories (the rest are regions and other aggregates), years 2008–2024, all `PERCENT`, `Reporting Type` G. An area without data answers 200 with empty `dimensions` (→ N/A), an unknown area code answers 500, a bad series code answers 200 with no rows (→ provider error). The area list (`GeoArea/List`) has no ISO codes, so **ISO ↔ UN M49** is made by matching area names to registry names (`registry.assign_m49`, alias table in `constants.py`), stored in `tourism_countries.un_m49`; areas whose name is shared by a sub-area/region (United Kingdom 826, Iraq 368, Tanzania 834, Micronesia 583) use `M49_OVERRIDES`. The reporting agency, nature of the data, footnotes ("TDGVA used as proxy", "Estimate" → flagged Estimated), the per-area DataSlice URL and the retrieval time are kept on every observation.
* **IDB** (`idb.py`): CKAN `datastore_search` / `resource_show` on `data.iadb.org`. Nothing is assumed: `idb_registry.json` must list each dataset (resource id, field
  names, unit) with `definition_matches: true` after a person checked the definition. Empty by default → "not configured". Sync: `POST /tourism/providers/IDB/sync`.
* **WTTC** (`wttc.py`): no verified public API, no scraping. An administrator uploads a licensed CSV/XLSX (`POST /tourism/import`, base64) in the Providers panel. Long
  (`country, year, indicator, value`) or wide (one column per total contribution share) layouts; country by name (alias table) or ISO code; `unit` = `percent` or
  `fraction`; the dataset edition is recorded; every rejected row is listed in the import job's `validation_report`. `WttcApiAdapter` is the hook for a future API.
* **Statista** (`statista.py`): optional, server-side only. Key in `.env` as `STATISTA_API_KEY`; the account's documented endpoints go in `statista_registry.json`
  (git-ignored; no path is hardcoded). Disabled without key/registry. Attribution text is stored with the observation.

## Registry (`registry.py`)
Seeded from the World Bank country list (aggregates removed) + the app's reference catalog; the alpha-3 code exists only if the World Bank supplied it, so a code is never
invented and a territory the World Bank does not list is never requested from it. `TERRITORIES` (constants.py) marks dependent territories and their parent; `REGION_BY_ISO2`
holds the app's own grouping (Caribbean, Central/South/North America, Europe, Africa, Middle East, Asia, Oceania). Manual additions: `POST /tourism/countries`.
Only registry members can reach a provider (ISO codes in `countries=` are validated and looked up, never concatenated into a URL as free text).

## Data model (`models.py`)
`tourism_countries`, `tourism_observations` (unique on country, indicator, year, source, edition → sources and editions never overwrite each other),
`tourism_providers`, `tourism_import_jobs`. Values are kept as exact decimal text (`value_text`) and as a float for sorting.

## Quality labels (`quality.py`)
Verified (passed the checks: known country, expected unit, plausible value/year; **not** an independent proof of the provider's estimate) · Calculated · Estimated (WTTC years
not yet fully reported) · Historical (older than 5 years) · Missing · Requires Review (negative population, share outside 0–100, wrong unit, unknown country, zero GDP…).

## API
`GET /tourism/countries?q=&region=&status=` (rows carry `un_m49`) · `POST /tourism/countries` · `GET /tourism/countries/{code}?year=` (row + all observations + warnings) ·
`GET /tourism/compare?countries=JM,BB&year=latest|2019&refresh=` · `GET /tourism/history?country=&from=&to=` · `GET /tourism/providers/status?check=` ·
`PUT /tourism/providers/{id}` · `POST /tourism/providers/{id}/sync` (IDB, STATISTA, UNSD) · `POST /tourism/import` · `GET /tourism/imports` ·
`GET /tourism/export?countries=&year=&format=csv|xlsx|json&layout=wide|long`. Errors: `{"detail": {"code": "...", "message": "..."}}`.

## Known limitations (2026-10)
* The World Bank's `ST.INT.RCPT.CD` series is incomplete: many countries stop years ago (Spain 1998, Jamaica 2011, Barbados 2016 at the time of writing). The module shows
  the real year of each value and never substitutes another year. For current receipts an IDB/Statista dataset or a file import is needed.
* `TOURISM_GDP_TOTAL_PCT` / `TOURISM_EMPLOYMENT` stay "N/A" until a licensed WTTC file (or a registered Statista dataset) is imported.
* `TOURISM_GDP_DIRECT_PCT` exists only for the countries that report to the UN (128 of the ~250 registry entries; e.g. Barbados, Grenada, Saint Martin and most dependent territories have none) and each country's latest year differs (Jamaica 2019, Bahamas 2012, Saint Lucia 2008).
* IDB and Statista need their registry files filled from the dataset documentation of the account.
* No authentication layer exists in this application's routers, so none is added here; the import endpoint accepts files up to 15 MB.
