# DIAN WebArancel — Phase 2 reconnaissance findings (2026-10-07)

Throwaway scripts (not in the repo) drove the real site with Playwright (Python, headless Chromium, one session at a time, ~0.7 s pause between
lookups, no CAPTCHA or challenge ever appeared). Sanitized HTML snapshots are in `fixtures/` (JSF `com.sun.faces.VIEW` tokens and `jsessionid` removed).
A sweep of the first line of 96 chapters (02–97, all but 77 which doesn't exist) found no errors.

## Workflow (what the UI really does)
1. `DefMenuConsultas.faces` — a JSF page; the seven consultations are `<a onclick="…form.submit()">` links (no hrefs): General, Por medidas,
   **Por código de nomenclatura**, Estructura, Índice alfabético, Reglas generales, Por texto. Locate them by visible text.
2. **General** → `DefConsultaGeneralNomenclaturas.faces`: one text input `…:codNomenclatura` ("Ingrese mínimo un capítulo") + an image button
   `…:btConsultarNomenclatura`. Result page (`DefResultadoConsNomenclaturas`/same form) = "Perfil de la mercancía": code (`0702.00.00.00`), description,
   unit, and a MEASURES table (`tblconsParametrosMedidas`), one row per measure with three image buttons **Importaciones / Exportaciones / Tránsito**
   (`…:{n}:btBImpo`, `btBExpo`, `btCxtr`; disabled when the measure doesn't apply). Row order for every sampled line: 0 Gravamen, 1 IVA, 2 Otras tarifas
   generales, 3 Gravámenes por acuerdos internacionales, … — **find rows by their visible name, not by index**.
3. Clicking `btBImpo` of Gravamen / IVA opens a **real popup window** (a new page): `DefGravamenPopUp.faces` / `DefIvaPopUp.faces?nomenclatura=<internal id>&codNomenclatura=<10 digits>&componente=3|4&regimen=1&fechaConsulta=YYYYMMDD&modoPresentacionSeleccionBO=dialogo`.
   The URL is built by the page's own JS from hidden fields — the provider must click, never build it. `ctx.expect_page()` works; each popup closes with `page.close()`.
4. Popup = one data table `class="consulta"` (`<thead><th>…`, `<tbody><tr><td><span>…`): Gravamen columns `Concepto | Tarifa - Fórmula | Desde | Hasta | Leg`;
   IVA columns `Tarifa - Fórmula | Desde | Hasta | Leg` (simple) or `Nombre del producto | Tarifa - Fórmula | …` (conditional). `Hasta` = `...` means open-ended.
   `Leg` holds a legal-basis icon with a tooltip (decree text) — presence only, not followed.
5. Pages are ISO-8859-1 (mojibake if decoded as UTF-8 by tools); Playwright decodes correctly.

## Consultation date
There is **no date input**. The profile page has a hidden `strFechaConsulta` set by the server to today (`20261007`), and the popup URL carries it. A calendar JS
widget is loaded but not bound to any control. → historical lookup is unsupported; results are as of today. (The prompt's "warn that the date isn't supported" case applies.)

## Partial codes (4/6/8 digits) — IMPORTANT, differs from the spec's assumption
- **General** with a prefix does NOT show a list: it silently returns the **first** tariff line under it (`0901`→0901.11.10.00, `090121`→0901.21.10.00, `07`→0701.10.00.00).
  Using it for a prefix would return a wrong product with no warning.
- A 10-digit code must be an existing line, otherwise the same page shows "ERROR Consulta General — No existen nomenclaturas." (e.g. `9999999999`, `0901210000`).
- **Por código de nomenclatura** (`DefConsultaNomenclaturaPorCodigo.faces`, same input/button pattern) lists **all lines under the prefix** with descriptions
  (`0901` → 0901.11.10.00, 0901.11.90.00, 0901.12.00.00, 0901.21.10.00, 0901.21.20.00, 0901.22.00.00, 0901.90.00.00). Each row is an `<a onclick="mostrarPerfil(<id>)">`;
  clicking it opens the same Perfil page. → proposed flow: always resolve through this page; 0 lines → HS_CODE_NOT_FOUND, 1 line → click it, >1 → `selection_required`.

## Gravamen
- Plain: `GRAVAMEN ARANCELARIO | 15% | 01-ene-2017 | ...` (0702); 40 % since 08-ene-2023 (6109); 0 % (8517).
- Rate text varies: `15%`, `40 %`, `5.0 %`, `0.0 %` → normalize whitespace and the optional decimal.
- **Extra rows exist**: lard 1501.10 and sugar 1701.12 also show `ARANCEL VARIABLE | 0 % / 34 % | 01-oct-2026 | 15-oct-2026` — a second concept with a short validity window.
  How it combines with the base rate (replaces/adds) is customs law, not shown by DIAN → the parser must return both rows and let the calculator refuse to guess when more than
  one concept is valid on the consultation date.
- No percentage-formula variants (specific, mixed, per-kg) appeared in 24 sampled chapters including textiles 50–64; none found, so those formats are still unseen.
  (Unknown `unit` values must therefore fail closed: `rate: null` + `formulaRaw`.)

## IVA — how "no IVA" is really displayed (the spec's assumption is wrong for Colombia)
- IVA is **never missing**: in all 96 sampled lines the IVA button was enabled and the popup had rows. Missing/disabled icon, empty popup and "no rows" cases were NOT observed.
- Exclusion is an explicit row: `0 % - EXCLUIDO` (fresh vegetables 0702, cocoa 18, cereals 10, water 22, coal 27…), exemption `0 % - EXENTO` (chapter 19, 3001…).
  Other rates seen: `19%`, `19 %`, `5 %`, `5%`, `0.0 % - EXCLUIDO/EXENTO`.
- **Conditional IVA**: some lines (8517.13 smartphones, 4901.10, 9301.10) have several rows keyed by "Nombre del producto", e.g. `… cuyo valor no exceda de 22 UVT | 0.0 % - EXENTO`
  and `Excepto: … | 19.0 %`. The rate depends on the product → cannot be computed from the code alone → `needs_input` with the rows kept.
- Consequence for the contract: `ivaStatus: "not_listed"` would only ever be produced if DIAN changes; keep it (fail-closed) but the normal outcomes are
  `rate: 0` with `rawText: "0 % - EXCLUIDO"` / `EXENTO` (classification `excluded` | `exempt` as an informational tag, still not interpreted as law), `rate: 19`, or conditional rows.

## Other observations
- No CAPTCHA, no login, no rate-limit response at ~1 request per 20 s over ~100 lookups (each lookup = a search + 2 popups ≈ 5 requests).
- A lookup takes ~15–25 s end to end headless (the site is slow); caching is essential.
- Each browser context starts a fresh JSESSIONID automatically; nothing needs to be persisted.
- Entry URL in the spec still works (`DefMenuConsultas.faces`); the General form posts to `DefConsultaGeneralNomenclaturas.faces`.
