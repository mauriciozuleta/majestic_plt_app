"""DianProvider: the Colombia (DIAN MUISCA WebArancel) provider — reproduces the normal user workflow with Playwright and returns the
Gravamen and the IVA of one HS code as a `TaxLookupResult` (see dian_types.py and README.md)."""

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from . import navigation, selectors
from .browser import browser_session, run_in_browser_thread, translate_playwright_error
from .dian_types import SCHEMA_VERSION, DianError, ProgressEvent, TaxLookupRequest, TaxValue
from .parsers import fold, is_valid_on, normalize_hs_code, parse_tax_table

log = logging.getLogger('dian')
DEBUG_DIR = Path(__file__).resolve().parent / 'debug'
SYSTEM = 'DIAN MUISCA WebArancel'


def today_local() -> str:
    """Today in the machine's own time zone (not UTC rounding)."""
    return date.today().isoformat()


class DianProvider:
    countryCode = 'CO'

    # ------------------------------------------------------------------ public

    def lookup(self, req: TaxLookupRequest) -> tuple[dict, int]:
        """-> (result dict, parse_warning_count). The count tells the cache whether the result is clean enough to keep."""
        try:
            code = normalize_hs_code(req.hsCode)
        except DianError as error:
            return error.to_result(), 0
        today = today_local()
        warnings: list[str] = []
        if req.date and req.date != today:
            warnings.append(
                f'DIAN’s tariff query has no date field, so a historical lookup ({req.date}) is not supported. The data below is what DIAN shows today ({today}).'
            )
        future = run_in_browser_thread(self._run, req, code, today, warnings)
        try:
            return future.result()
        except DianError as error:
            return error.to_result(), 0
        except Exception as error:  # noqa: BLE001 — anything unexpected still becomes a structured error
            log.exception('[DIAN] unexpected failure')
            translated = translate_playwright_error(error)
            return translated.to_result(), 0

    # ------------------------------------------------------------------ the run (inside the browser thread)

    def _run(self, req: TaxLookupRequest, code: str, today: str, warnings: list[str]) -> tuple[dict, int]:
        progress = _Progress(req.onProgress)
        parse_warnings = 0
        measure_urls: list[str] = []
        with browser_session(headless=not req.debug) as (context, page):
            debug = _Debug(page, req.debug)
            try:
                progress('connecting', 'Connecting to DIAN')
                log.info('[DIAN] lookup started for %s', code)
                navigation.open_dian(page)
                debug.snap('01-menu')

                progress('searching', 'Searching nomenclature')
                listing_html = navigation.submit_hs_code(page, code)
                log.info('[DIAN] search submitted for %s', code)
                debug.snap('02-listing')

                progress('resolving', 'Resolving tariff code')
                resolution = navigation.resolve_nomenclature(page, code, listing_html)
                if resolution.profile is None:
                    log.info('[DIAN] %s matches %d tariff lines: selection required', code, len(resolution.lines))
                    return {'status': 'selection_required', 'inputHsCode': code, 'matches': [{'hsCode': line.hsCode, 'description': line.description} for line in resolution.lines]}, 0
                profile = resolution.profile
                resolved = profile.hsCode
                log.info('[DIAN] resolved %s -> %s', code, resolved)
                debug.snap('03-profile')

                progress('gravamen', 'Reading Gravamen')
                gravamen_rows, gravamen_url, w = self._read_measure(context, page, profile, selectors.MEASURE_GRAVAMEN, debug, required=False)
                parse_warnings += w.parse
                warnings.extend(w.messages)
                if gravamen_url:
                    measure_urls.append(gravamen_url)
                log.info('[DIAN] Gravamen %s', 'found' if gravamen_rows else 'not found')

                progress('iva', 'Reading IVA')
                iva_table_rows, iva_url, w = self._read_measure(context, page, profile, selectors.MEASURE_IVA, debug, required=False, gravamen_found=bool(gravamen_rows))
                parse_warnings += w.parse
                warnings.extend(w.messages)
                if iva_url:
                    measure_urls.append(iva_url)
                log.info('[DIAN] IVA %s', 'found' if iva_table_rows.table.rows else 'not listed')

                result = self._build_result(code, resolved, profile, today, gravamen_rows, iva_table_rows, measure_urls, warnings)
                progress('complete', 'Complete')
                log.info('[DIAN] lookup complete for %s', resolved)
                return result, parse_warnings
            except DianError as error:
                debug.snap(f'error-{error.code}')
                raise

    # ------------------------------------------------------------------ measures

    def _read_measure(self, context, page, profile, measure: str, debug, required: bool, gravamen_found: bool = False):
        """Opens one measure's popup and parses its table. Returns (rows-or-table, popupUrl, _Warnings).
        Gravamen -> (list[TaxValue], url, w); IVA -> (_IvaRead, url, w)."""
        from .parsers.tax_table import TaxTable

        w = _Warnings()
        row = profile.measure(measure)
        is_iva = measure == selectors.MEASURE_IVA
        if row is None or not row.importAvailable:
            reason = 'row not found' if row is None else 'button disabled'
            if is_iva:
                # absent/disabled IVA icon: "not listed" only when the page was recognized AND the Gravamen was found
                if not gravamen_found:
                    raise DianError('MEASURE_PARSE_FAILED', 'The IVA is not available and the Gravamen could not be read either; the page may have changed.', measureName=measure, selectorAttempted=reason)
                return _IvaRead(TaxTable(found=True), explicit_absent=True), None, w
            w.messages.append('DIAN lists no Gravamen for this product, so the taxes cannot be calculated.')
            return [], None, w
        html, url = navigation.open_measure(context, page, row.buttonId, measure)
        debug.snap(f'popup-{measure.lower()}', html)
        table = parse_tax_table(html)
        if not table.found:
            summary = navigation.summarize_page(html)
            raise DianError('MEASURE_PARSE_FAILED', f'The {measure} popup does not contain the expected table.', measureName=measure, pageUrl=url, pageTitle=summary.get('title'), selectorAttempted='table with a "Tarifa - Fórmula" column')
        w.parse += len(table.warnings)
        w.messages.extend(table.warnings)
        if is_iva:
            return _IvaRead(table), url, w
        if not table.rows:
            w.messages.append('The Gravamen popup has no rows, so the taxes cannot be calculated.')
        return table.rows, url, w

    # ------------------------------------------------------------------ the result

    def _build_result(self, input_code, resolved, profile, today, gravamen_rows, iva_read, measure_urls, warnings) -> dict:
        warnings = list(warnings)
        needs_input: list[dict] = []
        reasons: list[str] = []

        # ----- Gravamen: the rows valid today decide
        grav_valid = [i for i, value in enumerate(gravamen_rows) if is_valid_on(value, today)]
        for value in gravamen_rows:
            warnings.extend(_validity_warnings(value, today, 'Gravamen'))
        gravamen = None
        if gravamen_rows and len(grav_valid) == 1:
            gravamen = gravamen_rows[grav_valid[0]]
        elif len(grav_valid) > 1:
            needs_input.append({'tax': 'gravamen', 'reason': 'multiple_valid_rows', 'rowIndexes': grav_valid})
            warnings.append('DIAN lists more than one Gravamen valid today; choose which applies.')
            reasons.append('Gravamen: more than one row is valid today')
        elif gravamen_rows:
            warnings.append('None of the Gravamen rows DIAN lists is valid on the consultation date.')
            reasons.append('Gravamen: no row valid today')
        else:
            reasons.append('Gravamen: not listed')

        # ----- IVA
        iva_rows = iva_read.table.rows
        iva = None
        iva_status = 'listed'
        if not iva_rows:
            iva_status = 'not_listed'
        else:
            for value in iva_rows:
                warnings.extend(_validity_warnings(value, today, 'IVA'))
            iva_valid = [i for i, value in enumerate(iva_rows) if is_valid_on(value, today)]
            conditional = iva_read.table.label_header is not None and fold(iva_read.table.label_header) == 'nombre del producto'
            if conditional:
                needs_input.append({'tax': 'iva', 'reason': 'conditional', 'rowIndexes': iva_valid or list(range(len(iva_rows)))})
                warnings.append('The IVA depends on the product’s own description (several rows); choose the one that applies.')
                reasons.append('IVA: depends on the product')
            elif len(iva_valid) == 1:
                iva = iva_rows[iva_valid[0]]
            elif len(iva_valid) > 1:
                needs_input.append({'tax': 'iva', 'reason': 'multiple_valid_rows', 'rowIndexes': iva_valid})
                warnings.append('DIAN lists more than one IVA valid today; choose which applies.')
                reasons.append('IVA: more than one row is valid today')
            else:
                warnings.append('None of the IVA rows DIAN lists is valid on the consultation date.')
                reasons.append('IVA: no row valid today')

        retrieved = datetime.now(timezone.utc).isoformat()
        return {
            'status': 'ok',
            'query': {'inputHsCode': input_code, 'resolvedHsCode': resolved, 'consultationDate': today},
            'product': {'hsCode': resolved, 'description': profile.description, 'chapter': resolved[:2], 'heading': resolved[:4]},
            'gravamen': gravamen.to_dict() if gravamen else None,
            'iva': iva.to_dict() if iva else None,
            'ivaStatus': iva_status,
            'gravamenRows': [value.to_dict() for value in gravamen_rows],
            'ivaRows': [value.to_dict() for value in iva_rows],
            'needsInput': needs_input,
            'calculable': gravamen is not None and not needs_input and (iva is not None or iva_status == 'not_listed'),
            'calculableReason': '; '.join(reasons) or None,
            'source': {
                'system': SYSTEM,
                'requestedHsCode': input_code,
                'resolvedHsCode': resolved,
                'consultationDate': today,
                'retrievedAt': retrieved,
                'mainPageUrl': selectors.MENU_URL,
                'measureUrls': measure_urls,
            },
            'warnings': warnings,
            'schemaVersion': SCHEMA_VERSION,
        }


# ---------------------------------------------------------------------- small helpers


class _Warnings:
    def __init__(self):
        self.messages: list[str] = []
        self.parse = 0  # warnings that come from parsing (they keep a result out of the cache)


class _IvaRead:
    def __init__(self, table, explicit_absent: bool = False):
        self.table = table
        self.explicit_absent = explicit_absent


def _validity_warnings(value: TaxValue, today: str, label: str) -> list[str]:
    out = []
    name = value.concept or label
    if value.validTo is not None and value.validTo < today:
        out.append(f'{name} ({value.formulaRaw}) expired on {value.validTo}, before the consultation date {today}.')
    if value.validFrom is not None and value.validFrom > today:
        out.append(f'{name} ({value.formulaRaw}) is valid only from {value.validFrom}, after the consultation date {today}.')
    return out


class _Progress:
    def __init__(self, callback):
        self._callback = callback

    def __call__(self, step: str, message: str):
        if self._callback:
            try:
                self._callback(ProgressEvent(step=step, message=message))
            except Exception:  # noqa: BLE001 — a broken listener must not break the lookup
                log.debug('[DIAN] progress listener failed', exc_info=True)


class _Debug:
    """Debug mode only: screenshots and sanitized HTML snapshots under colombia_dian/debug/ (gitignored). Never written otherwise."""

    def __init__(self, page, enabled: bool):
        self.page = page
        self.enabled = enabled
        self.folder = DEBUG_DIR / datetime.now().strftime('%Y%m%d-%H%M%S') if enabled else None
        if enabled:
            self.folder.mkdir(parents=True, exist_ok=True)

    def snap(self, name: str, html: str | None = None) -> None:
        if not self.enabled:
            return
        try:
            import re

            content = html if html is not None else self.page.content()
            content = re.sub(r'(?i)(jsessionid=)[0-9A-Za-z.]+', r'\1REDACTED', content)
            content = re.sub(r'(name="com\.sun\.faces\.VIEW"[^>]*value=")[^"]*(")', r'\1REDACTED\2', content)
            (self.folder / f'{name}.html').write_text(content, encoding='utf-8')
            if html is None:
                self.page.screenshot(path=str(self.folder / f'{name}.png'))
        except Exception:  # noqa: BLE001
            log.debug('[DIAN] debug snapshot failed', exc_info=True)
