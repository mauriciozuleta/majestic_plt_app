"""USDA AMS My Market News API ("MARS", https://marsapi.ams.usda.gov): the structured source behind the mnreports PDFs, with a stable JSON schema, history and the
volumes/store counts the PDFs do not carry. The key is the `USDA_MYMARKETNEWS_API_KEY` of the backend .env (never logged or returned); it is sent as the
HTTP Basic user name with an empty password.

Always request a date window: an unfiltered report returns its whole history and times out."""

import os
from datetime import date, timedelta

import httpx

BASE_URL = 'https://marsapi.ams.usda.gov/services/v1.2'
TIMEOUT = 90


class MarsError(RuntimeError):
    """A user-presentable reason a MARS request failed."""


def _key() -> str:
    key = (os.environ.get('USDA_MYMARKETNEWS_API_KEY') or '').strip()
    if not key:
        raise MarsError('No USDA My Market News key configured (set USDA_MYMARKETNEWS_API_KEY in the backend .env file).')
    return key


def date_window(days: int = 21) -> str:
    """The `report_begin_date` filter for the last `days` days, in MARS's MM/DD/YYYY:MM/DD/YYYY form."""
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days)
    return f'{start:%m/%d/%Y}:{end:%m/%d/%Y}'


def fetch_report(slug: str | int, days: int = 21) -> dict[str, list[dict]]:
    """{section name: rows} of the report over the last `days` days."""
    try:
        response = httpx.get(f'{BASE_URL}/reports/{slug}', auth=(_key(), ''), params={'q': f'report_begin_date={date_window(days)}', 'allSections': 'true'},
                             timeout=TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as error:
        raise MarsError(f'The USDA My Market News API could not be reached: {error}') from error
    if response.status_code == 401:
        raise MarsError('The USDA My Market News key was rejected (401). Check USDA_MYMARKETNEWS_API_KEY.')
    if response.status_code >= 400:
        raise MarsError(f'The USDA My Market News API returned {response.status_code} for report {slug}.')
    data = response.json()
    sections = data if isinstance(data, list) else [data]
    return {section.get('reportSection', 'report'): section.get('results', []) for section in sections}
