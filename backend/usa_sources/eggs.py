"""Daily National Shell Egg Index Report (5-day rolling average).
https://www.ams.usda.gov/mnreports/ams_2843.pdf — split by housing type
(National: Caged/Cage-Free/Free-Range/USDA Organic; California: Cage-Free/
USDA Organic). Domestic, no origin filtering needed.

Everything that defines a price is read from the report itself rather than
assumed: each section's header states its price unit and delivery basis
("30-Dozen Cases / Cents Per Dozen / FOB"), and each row group states its
type ("Graded Loose" = Grade A or higher, sold loose in 30-dozen cases).

Per housing/color combination, the size with the largest traded volume
today is used — the most representative price — not simply the largest
size, which can rest on a single thin trade. A size with no trades today
shows only a stale "last reported"/"year ago" figure and no weighted
average, so the row pattern below never matches it."""

import re
from io import BytesIO

import pdfplumber

from .common import download_pdf, extract_report_date

URL = 'https://www.ams.usda.gov/mnreports/ams_2843.pdf'
REPORT_NAME = f'USDA AMS Daily National Shell Egg Index Report ({URL})'

SECTION = re.compile(r'(NATIONAL|CALIFORNIA) SHELL EGGS. - (Caged|Cage-Free|Free-Range|USDA Organic)')
SECTION_UNITS = re.compile(r'30-Dozen Cases / (Cents|Dollars) Per Dozen / (\w+)')
ROW_TYPE = re.compile(r'^(Graded Loose|Gradeable Nest Run)\b')
ROW = re.compile(
    r'^(?:Graded Loose |Gradeable Nest Run \d+ )?(White|Brown) (Jumbo|Extra Large|Large|Medium|Small)'
    r' +([\d,]+) +(\d+\.\d{2}) - (\d+\.\d{2}) +(\d+\.\d{2})'
)


def fetch_egg_products():
    pdf_bytes = download_pdf(URL)
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = '\n'.join(page.extract_text() or '' for page in pdf.pages)

    source_date = extract_report_date(text)
    sections = list(SECTION.finditer(text))

    best = {}
    for i, section in enumerate(sections):
        end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        block = text[section.end() : end]
        scope, housing = section.groups()
        units = SECTION_UNITS.search(block)
        if not units:
            continue  # a section whose price unit can't be read is skipped, never guessed
        divisor = 100 if units.group(1) == 'Cents' else 1
        basis = units.group(2)
        row_type = None
        for line in block.split('\n'):
            line = line.strip()
            type_match = ROW_TYPE.match(line)
            if type_match:
                row_type = type_match.group(1)  # printed on a group's first row only
            match = ROW.match(line)
            if not match:
                continue
            color, size, volume, _lo, _hi, wtd_avg = match.groups()
            volume_cases = int(volume.replace(',', ''))
            key = (scope, housing, color)
            if key not in best or volume_cases > best[key]['volume']:
                best[key] = {
                    'size': size,
                    'price': float(wtd_avg) / divisor,
                    'volume': volume_cases,
                    'basis': basis,
                    'row_type': row_type or 'Shell eggs',
                }

    products = []
    for (scope, housing, color), row in best.items():
        products.append(
            {
                'category': 'Eggs',
                'product_en': f'Shell Eggs, {scope.title()} {housing} - {color} {row["size"]}',
                'price': round(row['price'], 4),
                'unit': f'USD/dozen ({row["row_type"]}, 30-dozen case, {row["basis"]})',
                'source_date': source_date,
                'report': REPORT_NAME,
                'quality_note': (
                    f'Wholesale weighted average for the most-traded size today ({row["volume"]:,} cases); '
                    f'{row["row_type"]}, {row["basis"]} — a bulk wholesale price before packing, freight or retail margin'
                ),
            }
        )
    return products
