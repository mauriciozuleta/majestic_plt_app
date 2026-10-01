"""Fresno Shipping Point Fruit Prices.
https://www.ams.usda.gov/mnreports/fr_fv110.pdf — CRITICAL: this report
mixes domestic California/North Carolina districts with "MEXICO CROSSINGS
THROUGH ..." import sections in the same document (e.g. an imported-avocado
section sits right next to a domestic "SOUTH DISTRICT CALIFORNIA" avocado
section). Every Mexico-crossing section is excluded via
`EXCLUDE_REGION_PATTERN` — this is the single most important rule for this
source; getting it wrong silently turns a USA export portfolio into a mixed
domestic/import list."""

import re
from io import BytesIO

import pdfplumber

from .common import (
    download_pdf,
    extract_report_date,
    parse_two_column_regions,
    produce_product_name,
    produce_rows_with_stated_weight,
    produce_unit_label,
)

URL = 'https://www.ams.usda.gov/mnreports/fr_fv110.pdf'
REPORT_NAME = f'USDA AMS Fresno Shipping Point Fruit Prices ({URL})'

EXCLUDE_REGION_PATTERN = re.compile(r'MEXICO CROSSING', re.IGNORECASE)


def fetch_produce_ca_products():
    pdf_bytes = download_pdf(URL)
    products = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        full_text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        source_date = extract_report_date(full_text)
        for page in pdf.pages:
            for row in produce_rows_with_stated_weight(
                parse_two_column_regions(page, exclude_region_pattern=EXCLUDE_REGION_PATTERN)
            ):
                products.append(
                    {
                        'category': 'Produce (CA Shipping Point)',
                        'product_en': produce_product_name(row),
                        'price': row['price'],
                        'unit': produce_unit_label(row),
                        'pack': row['pack'],
                        'pack_net_weight_lb': row['pack_net_weight_lb'],
                        'source_date': source_date,
                        'report': REPORT_NAME,
                        'quality_note': f"Domestic origin - confirmed via district label; {row['range_text']}",
                    }
                )
    return products
