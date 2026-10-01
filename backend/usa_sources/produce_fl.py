"""Orlando Shipping Point Vegetables Prices.
https://www.ams.usda.gov/mnreports/or_fv120.pdf — confirmed domestic (real
US districts named in the report body), no origin filtering needed. Only
covers tomatoes and okra at time of writing — this report does NOT cover
Florida's full produce range; see the module's open items."""

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

URL = 'https://www.ams.usda.gov/mnreports/or_fv120.pdf'
REPORT_NAME = f'USDA AMS Orlando Shipping Point Vegetables Prices ({URL})'


def fetch_produce_fl_products():
    pdf_bytes = download_pdf(URL)
    products = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        full_text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        source_date = extract_report_date(full_text)
        for page in pdf.pages:
            for row in produce_rows_with_stated_weight(parse_two_column_regions(page)):
                products.append(
                    {
                        'category': 'Produce (FL Shipping Point)',
                        'product_en': produce_product_name(row),
                        'price': row['price'],
                        'unit': produce_unit_label(row),
                        'pack': row['pack'],
                        'pack_net_weight_lb': row['pack_net_weight_lb'],
                        'source_date': source_date,
                        'report': REPORT_NAME,
                        'quality_note': f"Top of quoted FOB range, {row['range_text']}",
                    }
                )
    return products
