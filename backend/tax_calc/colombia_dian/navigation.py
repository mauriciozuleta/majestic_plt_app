"""The steps of the real user workflow on WebArancel: open → search a code → resolve the line → open a measure popup → close it.

Every selector comes from selectors.py; links and rows are found by visible text. The popup URLs are NEVER built by hand: the page's own JS builds
them when the real button is clicked. No fixed sleeps: waits are on load states, popups and locators, with bounded retries for transient failures.
"""

import logging
import time
from dataclasses import dataclass

from . import selectors
from .browser import translate_playwright_error
from .dian_types import DianError
from .parsers import fold, is_not_found, page_summary, parse_listing, parse_profile
from .parsers.pages import ListedLine, Profile

log = logging.getLogger('dian')

RETRY_DELAYS_S = (1.0, 3.0)  # bounded retries (so up to 3 attempts) for transient failures only


def _retry(step, what: str):
    """Runs `step()`; a timeout or a network failure is retried with backoff, anything else is raised at once."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    attempt = 0
    while True:
        try:
            return step()
        except (PlaywrightTimeout, PlaywrightError) as error:
            text = str(error)
            transient = isinstance(error, PlaywrightTimeout) or 'net::ERR' in text
            if not transient or attempt >= len(RETRY_DELAYS_S):
                raise translate_playwright_error(error) from error
            log.info('[DIAN] %s failed (%s), retrying in %.0fs', what, type(error).__name__, RETRY_DELAYS_S[attempt])
            time.sleep(RETRY_DELAYS_S[attempt])  # documented backoff between attempts, not a wait for page state
            attempt += 1


def open_dian(page) -> None:
    """Opens the consultation menu and checks it is the page we expect."""

    def go():
        page.goto(selectors.MENU_URL, wait_until='domcontentloaded', timeout=selectors.NAVIGATION_TIMEOUT_MS)
        page.wait_for_load_state('networkidle', timeout=selectors.NAVIGATION_TIMEOUT_MS)

    _retry(go, 'opening WebArancel')
    if 'WebArancel' not in page.url:
        raise DianError('DIAN_UNAVAILABLE', 'DIAN did not open the tariff consultation.', pageUrl=_clean_url(page.url), pageTitle=page.title())
    if page.get_by_text(selectors.MENU_BY_CODE, exact=False).count() == 0:
        raise DianError('PAGE_STRUCTURE_CHANGED', 'The tariff menu no longer has the "Por código de nomenclatura" option.', pageUrl=_clean_url(page.url), pageTitle=page.title(), selectorAttempted=selectors.MENU_BY_CODE)


def submit_hs_code(page, code: str) -> str:
    """Opens "Por código de nomenclatura", types the code and searches. Returns the result page HTML."""

    def go():
        page.get_by_text(selectors.MENU_BY_CODE, exact=False).first.click()
        page.wait_for_load_state('networkidle', timeout=selectors.NAVIGATION_TIMEOUT_MS)
        page.locator(selectors.CODE_INPUT).first.wait_for(timeout=selectors.NAVIGATION_TIMEOUT_MS)
        page.fill(selectors.CODE_INPUT, code)
        page.click(selectors.SEARCH_BUTTON)
        page.wait_for_load_state('networkidle', timeout=selectors.NAVIGATION_TIMEOUT_MS)

    try:
        _retry(go, 'searching the code')
    except DianError as error:
        if error.code == 'DIAN_TIMEOUT' and page.locator(selectors.CODE_INPUT).count() == 0:
            raise DianError('PAGE_STRUCTURE_CHANGED', 'The search form was not found.', pageUrl=_clean_url(page.url), pageTitle=page.title(), selectorAttempted=selectors.CODE_INPUT) from error
        raise
    return page.content()


@dataclass
class Resolution:
    lines: list[ListedLine]
    profile_html: str | None = None  # set when exactly one line matched and its profile was opened
    profile: Profile | None = None


def resolve_nomenclature(page, code: str, listing_html: str) -> Resolution:
    """From the listing of every tariff line under `code`: none -> HS_CODE_NOT_FOUND; several -> the caller asks the user (selection_required);
    exactly one -> its profile is opened (a real click on its link) and parsed."""
    lines = [line for line in parse_listing(listing_html) if line.hsCode.startswith(code)]
    if not lines:
        if is_not_found(listing_html) or folded_contains(listing_html, 'designacion de mercancias'):
            raise DianError('HS_CODE_NOT_FOUND', f'DIAN has no tariff line for the code {code}.', pageUrl=_clean_url(page.url))
        raise DianError('PAGE_STRUCTURE_CHANGED', 'The code listing was not recognized.', pageUrl=_clean_url(page.url), pageTitle=page.title())
    if len(lines) > 1:
        return Resolution(lines=lines)
    line = lines[0]

    def go():
        page.locator('a', has_text=line.displayCode).first.click()
        page.wait_for_load_state('networkidle', timeout=selectors.NAVIGATION_TIMEOUT_MS)
        page.locator(f'table[id$="{selectors.MEASURES_TABLE_ID_SUFFIX}"]').first.wait_for(timeout=selectors.NAVIGATION_TIMEOUT_MS)

    try:
        _retry(go, 'opening the tariff profile')
    except DianError as error:
        if error.code == 'DIAN_TIMEOUT':
            raise DianError('PAGE_STRUCTURE_CHANGED', 'The tariff profile did not open from the listing.', pageUrl=_clean_url(page.url), pageTitle=page.title()) from error
        raise
    html = page.content()
    profile = parse_profile(html)
    if not profile.recognized:
        raise DianError('PAGE_STRUCTURE_CHANGED', 'The tariff profile page was not recognized.', pageUrl=_clean_url(page.url), pageTitle=page.title())
    return Resolution(lines=lines, profile_html=html, profile=profile)


def open_measure(context, page, button_id: str, measure_name: str) -> tuple[str, str]:
    """Clicks the real Importaciones button of a measure row and returns (popup HTML, popup URL without session ids).
    Handles a popup window (what WebArancel does); falls back to a same-page change. The main page is left as it was."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    before = page.url
    button = page.locator(f'input[id="{button_id}"]')
    try:
        with context.expect_page(timeout=selectors.POPUP_TIMEOUT_MS) as opened:
            button.click(timeout=selectors.NAVIGATION_TIMEOUT_MS)
        popup = opened.value
        try:
            popup.wait_for_load_state('networkidle', timeout=selectors.NAVIGATION_TIMEOUT_MS)
            return popup.content(), _clean_url(popup.url)
        finally:
            close_popup(popup)
    except PlaywrightTimeout:
        # no popup window: the page itself may have changed
        if page.url != before:
            html, url = page.content(), _clean_url(page.url)
            page.go_back(wait_until='networkidle', timeout=selectors.NAVIGATION_TIMEOUT_MS)
            return html, url
        raise DianError('MEASURE_PARSE_FAILED', f'The {measure_name} popup did not open.', measureName=measure_name, pageUrl=_clean_url(page.url), pageTitle=page.title()) from None
    except PlaywrightError as error:
        raise translate_playwright_error(error) from error


def close_popup(popup) -> None:
    try:
        popup.close()
    except Exception:  # noqa: BLE001 — a popup that is already gone is fine
        pass


def summarize_page(html: str) -> dict:
    return page_summary(html)


def _clean_url(url: str) -> str:
    """The URL without any session id (';jsessionid=…') — those are never logged or kept."""
    return url.split(';jsessionid=')[0].split(';')[0] if ';' in url else url


def folded_contains(html: str, needle: str) -> bool:
    return fold(needle) in fold(html)
