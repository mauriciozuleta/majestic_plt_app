"""National Daily Pork Report FOB Plant - Negotiated Sales.
https://www.ams.usda.gov/mnreports/ams_2496.pdf (morning edition — the
afternoon edition ams_2498.pdf carries the same table shape and would be an
equally valid daily snapshot per the spec; morning is used here since either
is sufficient for one daily figure). Pulls "Today's Estimated Primal Cutout
Values" — the first (most recent) row. No grade tiers, no origin filtering
(domestic FOB-plant negotiated report)."""

import re
from io import BytesIO

import pdfplumber

from .common import download_pdf, extract_report_date

URL = 'https://www.ams.usda.gov/mnreports/ams_2496.pdf'
REPORT_NAME = f'USDA AMS National Daily Pork Report FOB Plant - Morning ({URL})'

TABLE_ROW = re.compile(
    r'Date Loads Carcass Loin Butt Pic Rib Ham Belly\n'
    r'(\d{2}/\d{2}/\d{4}) +(\d+\.\d+) +(\d+\.\d+) +(\d+\.\d+) +(\d+\.\d+) +(\d+\.\d+) +(\d+\.\d+) +(\d+\.\d+) +(\d+\.\d+)'
)

PRIMAL_LABELS = ['Carcass', 'Loin', 'Butt', 'Picnic', 'Rib', 'Ham', 'Belly']


def fetch_pork_products():
    pdf_bytes = download_pdf(URL)
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text()

    source_date = extract_report_date(text)
    match = TABLE_ROW.search(text)
    if not match:
        raise ValueError("Could not find today's Estimated Primal Cutout Values row")

    report_date, loads, *values = match.groups()
    products = []
    for label, value in zip(PRIMAL_LABELS, values):
        products.append(
            {
                'category': 'Pork',
                'product_en': f'Primal {label}',
                'price': float(value),
                'unit': 'USD/cwt (100lb)',
                'source_date': source_date or report_date,
                'report': REPORT_NAME,
                'quality_note': f'FOB plant negotiated, {report_date} ({loads} loads)',
            }
        )
    return products
