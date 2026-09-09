"""Daily National Shell Egg Index Report (5-day rolling average).
https://www.ams.usda.gov/mnreports/ams_2843.pdf — split by housing type
(National: Caged/Cage-Free/Free-Range/USDA Organic; California: Cage-Free/
USDA Organic — the report scopes some housing types to California
specifically, in addition to the national tables). Per color/housing
combination, uses the largest graded size that has a genuine same-day
traded price (Jumbo > Extra Large > Large > Medium > Small); a size with no
trades today only shows a stale "last reported"/"year ago" figure with no
current Weighted Average, which the row pattern below naturally excludes
(no separate carve-out needed). Domestic, no origin filtering needed."""

import re
from io import BytesIO

import pdfplumber

from .common import download_pdf, extract_report_date

URL = 'https://www.ams.usda.gov/mnreports/ams_2843.pdf'
REPORT_NAME = f'USDA AMS Daily National Shell Egg Index Report ({URL})'

SECTION = re.compile(r'(NATIONAL|CALIFORNIA) SHELL EGGS. - (Caged|Cage-Free|Free-Range|USDA Organic)')
ROW = re.compile(
    r'^(?:Graded Loose |Gradeable Nest Run \d+ )?(White|Brown) (Jumbo|Extra Large|Large|Medium|Small)'
    r' +([\d,]+) +(\d+\.\d{2}) - (\d+\.\d{2}) +(\d+\.\d{2})',
    re.MULTILINE,
)
SIZE_RANK = {'Jumbo': 4, 'Extra Large': 3, 'Large': 2, 'Medium': 1, 'Small': 0}


def fetch_egg_products():
    pdf_bytes = download_pdf(URL)
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = '\n'.join(page.extract_text() or '' for page in pdf.pages)

    source_date = extract_report_date(text)
    sections = list(SECTION.finditer(text))

    best = {}
    for i, section in enumerate(sections):
        start = section.end()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        block = text[start:end]
        scope, housing = section.groups()
        for match in ROW.finditer(block):
            color, size, volume, lo, hi, wtd_avg = match.groups()
            key = (scope, housing, color)
            rank = SIZE_RANK[size]
            if key not in best or rank > best[key][0]:
                best[key] = (rank, size, float(wtd_avg), volume)

    # National tables are quoted FOB; the California-scoped tables are
    # quoted Delivered — the report states this explicitly per section.
    basis = {'NATIONAL': 'FOB', 'CALIFORNIA': 'Delivered'}

    products = []
    for (scope, housing, color), (_, size, wtd_avg, volume) in best.items():
        products.append(
            {
                'category': 'Eggs',
                'product_en': f'{scope.title()} {housing} - {color} {size}',
                'price': round(wtd_avg / 100, 4),
                'unit': f'USD/dozen (30-dozen case, {basis.get(scope, "FOB")})',
                'source_date': source_date,
                'report': REPORT_NAME,
                'quality_note': f'Weighted average, largest graded size with a same-day trade (volume {volume} cases)',
            }
        )
    return products
