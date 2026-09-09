"""National Weekly Boxed Beef Cutout And Boxed Beef Cuts - Negotiated Sales.
https://www.ams.usda.gov/mnreports/ams_2461.pdf — pulls the "Weekly
Composite Primal Values" table. Domestic by construction (US cattle
industry reporting) — no origin filtering needed."""

import re
from io import BytesIO

import pdfplumber

from .common import download_pdf, extract_report_date

URL = 'https://www.ams.usda.gov/mnreports/ams_2461.pdf'
REPORT_NAME = f'USDA AMS National Weekly Boxed Beef Cutout ({URL})'

PRIMAL_LINE = re.compile(r'^Primal ([A-Za-z ]+?) +(\d+\.\d{2}) +(\d+\.\d{2})$', re.MULTILINE)


def fetch_beef_products():
    pdf_bytes = download_pdf(URL)
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text()

    source_date = extract_report_date(text)
    products = []
    for match in PRIMAL_LINE.finditer(text):
        name, choice, select = match.groups()
        products.append(
            {
                'category': 'Beef',
                'product_en': f'Primal {name.strip()}',
                'price': float(choice),
                'unit': 'USD/cwt (100lb)',
                'source_date': source_date,
                'report': REPORT_NAME,
                'quality_note': f'Choice grade (Select column also reported: {select})',
            }
        )
    return products
