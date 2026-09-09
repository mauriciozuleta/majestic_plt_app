"""Weekly National Chicken Report.
https://www.ams.usda.gov/mnreports/ams_3646.pdf — National Composite Whole
Bird (page 1) + the domestic Fresh/Conventional/FOB parts table (page 2,
before the Export sub-sections). Uses Weighted Average, not the top of the
price range — the range top is a single outlier trade, not representative
(deliberate judgment call carried over from the spec). Domestic, no origin
filtering needed."""

import re
from io import BytesIO

import pdfplumber

from .common import download_pdf, extract_report_date

URL = 'https://www.ams.usda.gov/mnreports/ams_3646.pdf'
REPORT_NAME = f'USDA AMS Weekly National Chicken Report ({URL})'

WHOLE_BIRD = re.compile(r'National Composite Whole (\d+\.\d{2}) - (\d+\.\d{2}) +(\d+\.\d{2})')
PART_LINE = re.compile(
    r'^([A-Za-z /\-]+): +(\d+\.\d{2}) - (\d+\.\d{2}) +(\d+\.\d{2}) +[-\d.]+ +[\d,]+ +[\d.]+ +[\d,]+', re.MULTILINE
)


def fetch_poultry_products():
    pdf_bytes = download_pdf(URL)
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        page1_text = pdf.pages[0].extract_text()
        page2_text = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ''

    source_date = extract_report_date(page1_text)
    products = []

    whole_match = WHOLE_BIRD.search(page1_text)
    if whole_match:
        _, _, wtd_avg = whole_match.groups()
        products.append(
            {
                'category': 'Poultry',
                'product_en': 'Whole Bird (National Composite)',
                'price': round(float(wtd_avg) / 100, 4),
                'unit': 'USD/lb',
                'source_date': source_date,
                'report': REPORT_NAME,
                'quality_note': 'Weighted average, domestic fresh conventional, delivered',
            }
        )

    # Only the first "Domestic - Fresh - Conventional - FOB" parts block —
    # stop before any "Export -" sub-section.
    domestic_section = page2_text.split('Export - Fresh')[0]
    for match in PART_LINE.finditer(domestic_section):
        name, _, _, wtd_avg = match.groups()
        products.append(
            {
                'category': 'Poultry',
                'product_en': name.strip(),
                'price': round(float(wtd_avg) / 100, 4),
                'unit': 'USD/lb',
                'source_date': source_date,
                'report': REPORT_NAME,
                'quality_note': 'Weighted average, domestic fresh conventional, FOB',
            }
        )
    return products
