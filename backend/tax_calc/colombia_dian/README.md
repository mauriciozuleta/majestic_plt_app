# Colombia (DIAN) tax lookup

Reads exactly two values from DIAN's MUISCA **WebArancel** for an HS code — the import **Gravamen Arancelario** and the **IVA** — by driving the
real consultation with Playwright, and calculates the import taxes of a shipment from them. Part of the Tax Calculator (Tools ▸ Tax Calculator: choose Colombia
as the import country); it lives inside the existing `backend/tax_calc/` package, not as a separate app. Out of scope: every other MUISCA measure
(agreements, restrictions, safeguards, antidumping…), FX, freight/insurance, other fees. Reconnaissance notes: `RECON.md`.

## Architecture
```
UI (TaxCalculatorView + DianLookupPanel.jsx + useDianFlow.js)  →  /tax-calc/colombia/dian/*  (routers/tax_calculator.py)
        → service.py  (provider registry · cache · shared in-flight runs · batch · background jobs)
        → provider.py (DianProvider: the decisions)  → navigation.py (the user workflow)  → browser.py (Playwright, one dedicated thread)
        → parsers/  (HTML string → typed rows; run offline against fixtures)
        → import_taxes.py (PURE calculator, Decimal)      cache.py (SQLite tables dian_tariff_cache / dian_code_alias)
```
- **Browser pool** (`browser.py`): Playwright's sync API is thread-bound, so a lookup runs entirely in one worker thread. `DIAN_MAX_SESSIONS` (default 1, max 2)
  is also the global limit of concurrent browser sessions. Each lookup launches its own Chromium and closes page/context/browser in `finally`. Cookies,
  session ids and view-state tokens are never logged or stored (popup URLs are logged without `;jsessionid`).
- **Progress**: lookups are background jobs polled by the UI (`POST …/lookups` → `GET …/jobs/{id}`), the same pattern as the RAG Files queue.
  Steps: Connecting to DIAN → Searching nomenclature → Resolving tariff code → Reading Gravamen → Reading IVA → Complete (batch: `1/3 Processing 0702000000`).
- **Setup**: `pip install -r requirements.txt` then once `playwright install chromium`. A missing browser returns the error code `BROWSER_NOT_INSTALLED`.

## The workflow it reproduces (see RECON.md)
Menu → **Por código de nomenclatura** → type the code → the page lists every tariff line under it → one line: open its profile; none: `HS_CODE_NOT_FOUND`;
several: `selection_required` (the user picks a 10-digit line) → on the profile, click the **Importaciones** button of the *Gravamen* row and of the *IVA*
row (rows are found by visible name) → each opens a popup page with one table → parse → close. Popup URLs are never built by hand.

## Result contract (`dian_types.py`, camelCase, ISO dates)
`status: "ok" | "selection_required" | "error"`. An ok result has `query`, `product`, `gravamen`/`iva` (a `TaxValue`: `rate` only for a plain percentage; otherwise
`rate: null` with `unit` and `formulaRaw`), `ivaStatus`, `source`, `warnings`, `schemaVersion`, plus these additions: `gravamenRows`/`ivaRows` (every row DIAN
shows), `needsInput` (what the user must choose) and `calculable`. Error codes: `INVALID_HS_CODE, DIAN_UNAVAILABLE, DIAN_TIMEOUT, HS_CODE_NOT_FOUND,
PAGE_STRUCTURE_CHANGED, MEASURE_PARSE_FAILED, BROWSER_NOT_INSTALLED` (the last one is an addition to the original list).

### Several rows → the user chooses
A popup can list more than one row (e.g. `GRAVAMEN ARANCELARIO 15%` plus `ARANCEL VARIABLE 34%` valid 01-oct → 15-oct-2026). DIAN doesn't say how they combine, so
the provider returns **all** rows, counts those valid on the consultation date and, if more than one is valid, sets `gravamen: null` and
`needsInput: [{ tax: "gravamen", reason: "multiple_valid_rows", rowIndexes }]`. The UI lets the user pick the row, then calls the calculator with it.
The same applies to a **conditional IVA** (`Nombre del producto` column: several rows keyed by the product's description; reason `conditional`).

### How "no IVA" is detected
In practice DIAN never omits the IVA: excluded goods show an explicit row (`0 % - EXCLUIDO`), exempt goods `0 % - EXENTO`; both come back as `ivaStatus: "listed"`,
`rate: 0`, `classification: "excluded" | "exempt"`, with DIAN's wording in `formulaRaw`/`rawText` (not interpreted as law). `ivaStatus: "not_listed"` (iva null, **no
warning**) is produced only if ALL hold: the profile page was recognized, the Gravamen was found, and the IVA button is absent/disabled **or** its popup opened with a table
that has no rows. If the IVA popup does not open, times out, or has no recognizable table, the result is an **error** (`MEASURE_PARSE_FAILED` / `PAGE_STRUCTURE_CHANGED` /
`DIAN_TIMEOUT`) — a failure is never mapped to `not_listed`. (Tested: `test_dian_provider.CriticalIvaFailureTests`.)

## Consultation date
DIAN's consultation has **no date input** (the profile page carries a hidden `fechaConsulta` = today). Results are always as of today; a requested date that is not
today adds a warning and the result's `consultationDate` is the real one. Validity: a row applies when `validFrom <= date` and `validTo` is open or `>= date`; expired or
not-yet-valid rows add warnings.

## Calculator (`import_taxes.py`, pure, Decimal)
`calculate_import_taxes(customsValue, gravamen, iva, ivaStatus)`: `gravamenAmount = value × rate/100`; `ivaAmount = iva_base_for_imports(value, gravamenAmount) × rate/100`.
**IVA-base assumption**: on imports the IVA base is normally *customs value + Gravamen* — NOT verified here; confirm with a customs broker or DIAN. It is one function
(`iva_base_for_imports`) so it is easy to change. `not_listed` → IVA 0 with the note "No IVA listed by DIAN; calculated as 0. Verify the product's IVA treatment.".
A non-percent Gravamen/IVA → `status: "unsupported_formula"` with `formulaRaw`, nothing computed; no Gravamen → `not_calculable`. All intermediates and the rates'
validity dates are returned. Rounding: only at the end, ROUND_HALF_UP to 2 decimals.

## Cache
Key `DIAN:{resolvedHsCode}:{consultationDate}:v{schemaVersion}` plus an alias typed-code → resolved code, in the app's SQLite database. TTL `DIAN_CACHE_TTL_HOURS`
(default 24). Never cached: errors, `selection_required`, results with parse warnings. `forceRefresh` bypasses reads; identical concurrent lookups share one run.

## Batch
`POST /tax-calc/colombia/dian/batch` (`{ hsCodes, date?, concurrency = 1 (max 2), delayMs = 1500 }`): sequential by default with a pause between codes; a failure of one code
never aborts the batch. A lookup takes ~5–20 s (about five requests), so keep batches small.

## Debug mode
`debug: true` (request body of `…/lookups`): non-headless Chromium, screenshots and sanitized HTML snapshots of each stage (and of any error) under `debug/<timestamp>/`
(gitignored; nothing is written there otherwise). Logs use the `[DIAN]` prefix (`logging.getLogger('dian')`): start, search submitted, resolved code, Gravamen found, IVA found
or not listed, complete.

## Adding a country provider
Implement `lookup(req: TaxLookupRequest) -> (result_dict, parse_warning_count)` with a `countryCode`, using the same result contract, and register it in `service.py`
(`service.register(MyProvider())`). The UI talks to the service, not to a provider. A country whose data is a local file (Jamaica, USA) is a `tax_calc` *adapter* instead
(see `backend/tax_calc/base.py`).

## Tests
Offline: `python -m unittest backend.tests.test_dian_parsers backend.tests.test_dian_calculator backend.tests.test_dian_provider` (fixtures in `fixtures/`, sanitized: view-state and
session ids stripped; the `SYNTHETIC_*` files are derived from real ones for cases DIAN never produced: IVA icon disabled, IVA popup with no rows, unexpected popup).
Live (manual, calls the real site once): `npm run test:dian-live`.

## Known DIAN limitations
No date input; no official API or open dataset found; the site is slow (a few seconds per page); a partial code on the "General" page silently returns the first line (this module
uses the listing page instead); the `ARANCEL VARIABLE` row and conditional IVA need a human choice; no non-percentage (specific/mixed) Gravamen was seen in a sweep of 96 chapters,
so those formats are handled fail-closed but untested against the real site; DIAN's page markup is old JSF and could change (→ `PAGE_STRUCTURE_CHANGED`).
