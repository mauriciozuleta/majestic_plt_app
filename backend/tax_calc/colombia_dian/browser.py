"""Playwright lifecycle for the DIAN provider.

Playwright's sync API is bound to the thread that starts it, so every lookup runs entirely inside ONE worker thread of a small pool
(`DIAN_MAX_SESSIONS`, default 1, at most 2): that pool is also the global limit on concurrent browser sessions. A lookup launches its own
browser, uses one context, and closes page, context and browser in `finally`. Cookies, session ids and view-state tokens are never logged or kept.
"""

import asyncio
import logging
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager

from .dian_types import DianError

log = logging.getLogger('dian')

MAX_SESSIONS_CEILING = 2


def _ensure_subprocess_capable_loop() -> None:
    """Playwright launches Chromium as a subprocess, which on Windows needs the Proactor event loop. uvicorn (in --reload mode) installs the
    Selector policy, whose loops raise NotImplementedError on subprocess creation — so switch the policy before Playwright creates its loop.
    Proactor is Python's own default on Windows, so this only restores it."""
    if sys.platform != 'win32':
        return
    if not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def max_sessions() -> int:
    try:
        value = int(os.environ.get('DIAN_MAX_SESSIONS', '1'))
    except ValueError:
        value = 1
    return max(1, min(MAX_SESSIONS_CEILING, value))


_pool: ThreadPoolExecutor | None = None


def run_in_browser_thread(fn, *args, **kwargs) -> Future:
    """Queues `fn` on the browser pool; the caller waits on the Future."""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=max_sessions(), thread_name_prefix='dian-browser')
    return _pool.submit(fn, *args, **kwargs)


def translate_playwright_error(error: Exception) -> DianError:
    """Maps what Playwright raises onto the contract's error codes."""
    name = type(error).__name__
    text = str(error)
    if 'Executable doesn' in text or 'playwright install' in text:
        return DianError('BROWSER_NOT_INSTALLED', "Playwright's Chromium is not installed on this machine. Run: playwright install chromium")
    if name == 'TimeoutError' or 'Timeout' in name:
        return DianError('DIAN_TIMEOUT', 'DIAN did not answer in time. Try again later.')
    if 'net::ERR' in text or 'ERR_' in text or 'Target closed' in text or 'Connection' in name:
        return DianError('DIAN_UNAVAILABLE', 'DIAN could not be reached. Try again later.')
    return DianError('DIAN_UNAVAILABLE', f'The browser session failed: {text.splitlines()[0][:200] if text else name}')


@contextmanager
def browser_session(headless: bool = True):
    """Yields (context, page) of a fresh browser; everything is closed on exit, whatever happens."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    playwright = None
    browser = None
    context = None
    try:
        _ensure_subprocess_capable_loop()
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=headless)
        except PlaywrightError as error:
            raise translate_playwright_error(error) from error
        context = browser.new_context(viewport={'width': 1400, 'height': 1000}, locale='es-CO')
        page = context.new_page()
        # a stray alert/confirm must never block the run
        page.on('dialog', lambda dialog: dialog.dismiss())
        yield context, page
    finally:
        for closer in (context, browser):
            try:
                if closer is not None:
                    closer.close()
            except Exception:  # noqa: BLE001 — closing must not mask the real error
                log.debug('[DIAN] close failed', exc_info=True)
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:  # noqa: BLE001
            log.debug('[DIAN] playwright stop failed', exc_info=True)
