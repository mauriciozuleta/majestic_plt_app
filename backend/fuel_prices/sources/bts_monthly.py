"""Scheduled U.S. carrier monthly system-wide prices from BTS's public history table.

The published price is retained: costs and gallons on this page are rounded to
millions, so dividing those rounded totals would introduce avoidable error.
"""

import calendar
import math
from datetime import date
from html.parser import HTMLParser

import httpx

from .base import Job, Observation, SourceAdapter

URL = 'https://www.transtats.bts.gov/fuel.asp'
SERIES_ID = 'bts_p12:US:scheduled'


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row, self.cell = None, None


def parse(text: str) -> list[Observation]:
    parser = _Rows()
    parser.feed(text)
    months = {name: i for i, name in enumerate(calendar.month_name) if name}
    if 'U.S. Carriers - Scheduled' not in text:
        raise ValueError('BTS scheduled-carrier table heading missing; no data imported')
    result = {}
    for row in parser.rows:
        if len(row) < 2 or row[1] not in months or not row[0].isdigit():
            continue  # totals, year-to-date and percentage-change rows
        if len(row) != 11:
            raise ValueError('BTS monthly columns changed; no data imported')
        when = date(int(row[0]), months[row[1]], 1)
        values = [float(v.replace(',', '').replace('$', '')) for v in row[2:]]
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError(f'Invalid BTS values for {when}')
        gallons, cost, price = values[6:9]
        if abs(cost / gallons - price) > 0.02:
            raise ValueError(f'BTS cost/gallons do not match price for {when}')
        if when in result:
            raise ValueError(f'Duplicate BTS month {when}')
        result[when] = Observation(
            series_id=SERIES_ID, obs_date=when, value_usd_per_gal=price,
            value_original=price, unit_original='usd_gal', currency_original='USD',
            period_type='month', geo_level='country', country_iso2='US',
            operator_class='scheduled', price_basis='airline_paid', source_id='bts_p12',
            quality='observed', raw_ref={'url': URL, 'scope': 'U.S. scheduled carriers, domestic + international',
                                       'cost_usd_millions': cost, 'gallons_millions': gallons,
                                       'method': 'BTS published average price per gallon'})
    if not result:
        raise ValueError('No BTS monthly rows found; no data imported')
    return [result[d] for d in sorted(result)]


class BtsMonthlyAdapter(SourceAdapter):
    source_id = 'bts_p12'
    automatic = True

    def jobs(self):
        return [Job('monthly_summary', 'daily', 'Monthly airline-paid price (daily release check)', SERIES_ID)]

    def fetch(self, since=None):
        response = httpx.get(URL, timeout=60, follow_redirects=True)
        response.raise_for_status()
        # One public table contains the full history. Reconcile all months to
        # capture revisions, including ones older than an incremental overlap.
        return parse(response.text)
