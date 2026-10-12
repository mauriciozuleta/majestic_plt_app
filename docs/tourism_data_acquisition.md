# How the tourism and economy data is obtained

This document explains, step by step, where every number in the **Tourism & Economy** columns (Market Analysis ▸ Country Information) and in
**Tools ▸ Tourism & Economic Dependency** comes from, how the application retrieves it, and how you can reproduce or check any value by hand.
The code is in `backend/tourism/` (technical notes: `backend/tourism/README.md`).

## 1. The indicators and where each one comes from

| Column | Indicator code | Meaning | Source | Automatic? |
|---|---|---|---|---|
| Tourism GDP % (total) | `TOURISM_GDP_TOTAL_PCT` | Total contribution of travel & tourism to GDP (direct + indirect + induced) | WTTC (licensed file), Statista as second choice | No — needs a licensed file |
| Tourism GDP % (direct) | `TOURISM_GDP_DIRECT_PCT` | Tourism direct GDP as a proportion of total GDP (SDG 8.9.1) | UN Statistics Division SDG API, series `ST_GDP_ZS` | Yes |
| Tourism Employment % | `TOURISM_EMPLOYMENT` | Total contribution of travel & tourism to employment | WTTC (licensed file), Statista as second choice | No — needs a licensed file |
| Tourism Receipts USD | `TOURISM_RECEIPTS` | International tourism receipts, current US$ | World Bank `ST.INT.RCPT.CD` | Yes |
| Tourism Dependency % | `TOURISM_DEPENDENCY` | Receipts ÷ GDP × 100, same country and year | Calculated from World Bank receipts and GDP | Yes |
| Population | `POPULATION` | Total population | World Bank `SP.POP.TOTL` | Yes |
| (supporting) GDP USD | `GDP_USD` | GDP, current US$ — the denominator of the dependency | World Bank `NY.GDP.MKTP.CD` | Yes |

Three of these look alike and are **never substituted for each other**:

* *total* tourism GDP (WTTC) ≠ *direct* tourism GDP (UN) — the total includes indirect and induced effects, so it is always larger;
* neither is the *dependency*, which divides tourism **receipts** by GDP and measures something else again (it can exceed the GDP shares because receipts are a gross inflow);
* visitor arrivals are not receipts, and a job count is not an employment percentage.

If a compatible observation does not exist, the cell shows **N/A** and its tooltip gives the reason. Nothing is estimated and no other year is borrowed.

## 2. Step 0 — which country is which (the registry)

Every provider names countries differently, so the application keeps one registry (`tourism_countries`):

1. The base list is the **World Bank country list** (`https://api.worldbank.org/v2/country?format=json&per_page=400`), aggregates removed. It supplies the ISO alpha-2 and alpha-3 code and a World Bank region. The alpha-3 code exists only if the World Bank supplied it — codes are never invented, and a territory the World Bank does not list is never requested from it.
2. Countries of the application's reference catalog that the World Bank does not list (for example Anguilla) are added with their alpha-2 code only.
3. The region (Caribbean, Central America, …) is the application's own grouping; dependent territories are marked with their parent state.
4. The **UN M49 code** used by the UN API is attached later, during the UN sync (section 4).

## 3. World Bank — receipts, GDP, population

**What is called** (no key needed; documentation: `datahelpdesk.worldbank.org/knowledgebase/articles/889392`):

```
https://api.worldbank.org/v2/country/JAM;BRB;BHS/indicator/ST.INT.RCPT.CD?format=json&per_page=1000&page=1&date=1990:2026
https://api.worldbank.org/v2/country/JAM;BRB;BHS/indicator/NY.GDP.MKTP.CD?format=json&per_page=1000&page=1&date=1990:2026
https://api.worldbank.org/v2/country/JAM;BRB;BHS/indicator/SP.POP.TOTL?format=json&per_page=1000&page=1&date=1990:2026
```

**How the application does it** (`backend/tourism/worldbank.py`):

1. Countries are requested by alpha-3 code, 25 per request, for the three indicators.
2. The answer is `[metadata, rows]`; the metadata gives `pages` (followed until the last page) and `lastupdated` (kept as the dataset edition).
3. Rows with a `null` value are dropped; every other row is stored as one observation with its source URL (`https://data.worldbank.org/indicator/<id>?locations=<ISO2>`), year, edition and retrieval time.
4. Answers are cached on disk for 24 hours; network errors, HTTP 429 and 5xx are retried three times with waits of 0.5 s and 1 s.

**Reproduce one value by hand**

```
curl "https://api.worldbank.org/v2/country/JAM/indicator/ST.INT.RCPT.CD?format=json&per_page=100&date=2005:2025"
```

Look for the newest row whose `value` is not `null`. For Jamaica that is **2011: US$ 2,060,000,000**.

**Known limitation — the receipts series is stale.** The World Bank stopped updating `ST.INT.RCPT.CD` for many countries. At the time of writing the latest non-null year is Spain 1998, Jamaica 2011, Barbados 2016, Saint Lucia 2018, Trinidad and Tobago 2020, United States 2020. The table shows each value with its own year (for example `USD $2.06B 2011`) and never replaces it with another year. Current receipts would have to come from an IDB or Statista dataset or an imported file.

## 4. United Nations SDG API — direct tourism GDP

SDG indicator **8.9.1**, series **`ST_GDP_ZS`** — "Tourism direct GDP as a proportion of total GDP (%)". Documentation: `https://unstats.un.org/SDGAPI/swagger/`. No key needed.

**What is called**

```
# every country and year in one request (paginated: page, pageSize)
https://unstats.un.org/SDGAPI/v1/sdg/Series/Data?seriesCode=ST_GDP_ZS&pageSize=2000&page=1

# the list of UN areas (code + name; no ISO codes)
https://unstats.un.org/SDGAPI/v1/sdg/GeoArea/List

# one area, as a check or a source link
https://unstats.un.org/SDGAPI/v1/sdg/Series/ST_GDP_ZS/GeoArea/388/DataSlice
```

**What was verified against the live API before the pipeline was written**

| Question | Finding |
|---|---|
| Response shape | `{size, totalElements, totalPages, pageNumber, data:[…]}`; each record has `geoAreaCode` (M49, text), `geoAreaName`, `timePeriodStart` (a float such as `2019.0`), `value` (text), `source` (reporting agency), `footnotes`, `attributes {Nature, Units}`, `dimensions {Reporting Type}` |
| Size | 1,669 records, 149 areas, years 2008–2024, all `Units = PERCENT`, all `Reporting Type = G` |
| Page size | `pageSize=2000` returns everything in one page; the code still follows `totalPages` |
| Area with no data | HTTP 200 with `dimensions: []` → shown as N/A |
| Unknown area code | HTTP 500 → provider error, retried then reported |
| Unknown series code | HTTP 200 with no rows → treated as an error, not as "no data" |
| Aggregates | World, regions, LDCs, SIDS, … are in the data and are ignored |
| Footnotes seen | "TDGVA used as proxy", "Estimate", "Revised data" |

**ISO ↔ UN M49 mapping.** The UN area list carries no ISO codes, so the link is made by name (`registry.assign_m49`): each UN area name is normalised and matched to a registry name (with an alias table for official UN names such as "United States of America", "Republic of Moldova", "State of Palestine", "China, Hong Kong Special Administrative Region"). The UN area code is then stored on the country row (`un_m49`). Four countries share their name with a sub-area or a region in the UN list (United Kingdom 826, Iraq 368, Tanzania 834, Micronesia 583) and use explicit codes. Result: 247 of 252 registry countries have a code, with no conflicts; the other UN areas are aggregates.

**How the application does it** (`backend/tourism/unsd.py`, `service.sync_unsd`):

1. Download the area list and the whole series (all pages).
2. Map each record's `geoAreaCode` to a registry country; skip aggregates.
3. Reject a record whose unit is not PERCENT; if two records exist for one area and year, keep the Reporting Type `G` one — nothing is averaged.
4. Store `TOURISM_GDP_DIRECT_PCT` with: the value, the year, the DataSlice URL of that area, the reporting agency, the nature of the data, the footnotes, the methodology note ("direct contribution only — not the total contribution published by WTTC") and the retrieval time. A footnote of "Estimate" marks the observation *Estimated*.
5. The download repeats at most every 24 hours (the provider's `last_sync`); **Providers ▸ UN Statistics Division ▸ Sync now** forces it.

**Coverage (2026-10):** 1,312 stored observations for 128 countries and territories. Examples: Jamaica 9.8 % (2019), Bahamas 15.17 % (2012, estimate), Trinidad and Tobago 7.7 % (2024), Colombia 2.16 % (2024), United States 3.03 % (2023). Barbados, Grenada, Saint Martin and most dependent territories report nothing and show N/A with the reason. Each country's latest year differs (Saint Lucia's is 2008).

## 5. The calculated dependency

```
Tourism Dependency (%) = International tourism receipts (US$) ÷ GDP (current US$) × 100
```

Rules (`backend/tourism/calc.py`, `service.compute_dependency`):

* receipts and GDP must be for the **same country and the same year** — if one is missing, no ratio is stored; a neighbouring year's GDP is never used;
* the arithmetic uses exact decimals, rounded to four places; a zero or negative GDP, or negative receipts, gives no ratio;
* the result is stored as its own observation (source `CALCULATED`) whose note names both inputs, for example Jamaica 2011: 2,060,000,000 ÷ GDP 2011 × 100 = **14.26 %**;
* "latest" means the latest year in which both inputs exist, which can be earlier than the latest receipts or GDP year.

## 6. WTTC — total GDP and employment (licensed data)

WTTC publishes the *total* contribution of travel & tourism to GDP and to employment, but **has no verified public API** and its research portal is a subscription service. The application therefore does not call or scrape it. The process is:

1. Obtain the data **under a WTTC licence** (for example an export from the WTTC Research Hub) as CSV or XLSX.
2. Open **Tools ▸ Tourism & Economic Dependency ▸ 5 · Providers ▸ Import licensed WTTC data**, choose the file, type the dataset edition (for example "2025 Economic Impact Research"), and say whether the values are percent (12.5) or fractions (0.125).
3. The importer (`backend/tourism/wttc.py`) accepts two layouts:
   * *long*: `Country, Year, Indicator, Value`
   * *wide*: `Country, Year, <total contribution to GDP column>, <total contribution to employment column>`

   Countries may be given by name (matched through the registry and an alias table) or by an ISO code column.
4. **Only total-contribution shares are accepted.** A column or indicator that says "direct" (without "total"), a job count, or any other measure is rejected, so the direct contribution can never be stored as the total.
5. Every row is validated: country found, year valid, value numeric and between 0 and 100 (a file in fractions imported as percent triggers a warning), no conflicting duplicate. Rejected rows are listed in the import report and kept in the import history with the file name, edition, row counts and date.
6. Imported values appear in the **Tourism GDP % (total)** and **Tourism Employment %** columns, marked with source `WTTC` and the edition. Years that are not yet fully reported are flagged *Estimated*.

Until a file is imported these two columns show **N/A** — deliberately.

## 7. Optional providers: IDB and Statista

Both are off until configured, because their dataset identifiers and endpoints depend on the account and the dataset and must not be guessed.

* **IDB** (`data.iadb.org`, a CKAN portal): list each dataset in `backend/tourism/idb_registry.json` — resource id, the field names that hold country, year and value, the unit — and set `definition_matches: true` only after checking that the dataset's definition equals the indicator's. The connector then uses the documented `datastore_search` (paginated) and `resource_show` actions. **Providers ▸ IDB ▸ Sync** loads it.
* **Statista**: put `STATISTA_API_KEY` in the server `.env` and describe the endpoints your subscription allows in `backend/tourism/statista_registry.json` (git-ignored). The key stays on the server and is never sent to the browser; Statista's attribution text is stored with each value.

## 8. What the user sees

* **Latest available** shows each value with its own year (for example Jamaica: receipts 2011, direct GDP 2019, population 2025). A specific year shows only that year, otherwise N/A with the years that do exist.
* Each value carries a **status**: *Verified* (it passed the validation checks — known country, expected unit, plausible value and year; this is not an independent proof of the provider's estimate), *Calculated*, *Estimated*, *Historical* (older than five years), *Missing*, *Requires Review*.
* Hovering over a cell in Market Analysis, or opening a country in the tool, shows the source, dataset, edition, status, methodology note and, in the tool, every stored observation with its retrieval date.
* **Export** (CSV, XLSX, JSON; one row per country or one row per country-year-indicator) includes units, years, sources, editions, retrieval dates and quality flags.

### Where the Market Analysis table gets its values
The Tourism & Economy columns of Market Analysis ▸ Country Information (Tourism GDP % direct, Receipts USD, Dependency %, Population) are read **from the database only** — opening the page calls no provider and takes milliseconds. A line above the table shows when the stored values were last updated. The **Update tourism data** button calls the providers once for the countries in the table (World Bank in parallel, the UN SDG API), stores the new values and redraws the table; it can take from a few seconds to about a minute when the World Bank is slow. The WTTC-based *total GDP* and *employment* columns are not shown there (they have no data until a licensed file is imported); they remain in Tools ▸ Tourism & Economic Dependency.

## 9. Checking and refreshing

| To… | Do |
|---|---|
| See whether a provider works | Providers panel ▸ *Test connection* (World Bank and UN) |
| Force a refresh of one country | Tool ▸ *Refresh* (calls the providers again and ignores the 24-hour cache) |
| Reload the whole UN series | Providers ▸ UN Statistics Division ▸ *Sync now* |
| Verify a value independently | Use the `curl` lines above, or the source link in the country's detail table |
| Run the automated checks | `.venv/Scripts/python.exe -m unittest backend.tests.test_tourism` (mocked, no network) |

If a provider is unreachable, the table still shows the stored data and a warning names the provider; the provider's status in the panel turns to *error* with the message.
