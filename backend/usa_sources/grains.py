"""Louisiana and Texas Export Bids.
https://www.ams.usda.gov/mnreports/ams_3147.pdf — Gulf Coast export-elevator
bids (not a domestic-consumption cash bid report — this is specifically the
price for grain headed out of the country, the correct source for an
export-portfolio context). Uses the "Current" (nearest/spot) delivery
window's Price($/Bu) band, not a quality tier (there isn't one here — these
are live bid quotes). Domestic-grown by definition (a US export bid)."""

import re
from io import BytesIO

import pdfplumber

from .common import download_pdf, extract_report_date

URL = 'https://www.ams.usda.gov/mnreports/ams_3147.pdf'
REPORT_NAME = f'USDA AMS Louisiana and Texas Export Bids ({URL})'

GRAIN_HEADING = re.compile(r'^(US #\d+ [A-Za-z ]+?) \(Bulk\)$', re.MULTILINE)
CURRENT_PRICE = re.compile(r'(\d+\.\d{4})-(\d+\.\d{4})[^\n]*CIF-B +Current')


def fetch_grain_products():
    pdf_bytes = download_pdf(URL)
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = '\n'.join(page.extract_text() or '' for page in pdf.pages)

    source_date = extract_report_date(text)
    headings = list(GRAIN_HEADING.finditer(text))

    products = []
    for i, heading in enumerate(headings):
        start = heading.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]
        match = CURRENT_PRICE.search(block)
        if not match:
            continue
        lo, hi = match.groups()
        price = round((float(lo) + float(hi)) / 2, 4)
        products.append(
            {
                'category': 'Grains (Export)',
                'product_en': heading.group(1).strip(),
                'price': price,
                'unit': 'USD/bushel',
                'source_date': source_date,
                'report': REPORT_NAME,
                'quality_note': f'Gulf Coast export elevator, Current (spot) delivery, CIF-B, quoted range {lo}-{hi}',
            }
        )
    return products
