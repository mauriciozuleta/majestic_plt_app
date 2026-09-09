"""Shared helpers for the USA sourcing parsers (USDA AMS `mnreports` PDFs).

Each report has a genuinely different table layout (per the module spec —
"Build per-report, not one-size-fits-all"), so there's no generic PDF-table
extractor here. What IS shared: downloading, and the two-column
region-labeled layout used by both Specialty Crops reports (Florida
vegetables, California fruit) — see `parse_two_column_regions`.
"""

import re

import httpx


def download_pdf(url):
    response = httpx.get(url, timeout=30, follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    return response.content


DATE_PATTERN = re.compile(r'([A-Z][a-z]+ \d{1,2},? ?\d{4})')


def extract_report_date(text):
    match = DATE_PATTERN.search(text)
    return match.group(1).replace(',', ', ').replace(',  ', ', ') if match else None


# A region/section header in these reports is always immediately followed
# by this exact boilerplate line — that's how a region header is
# distinguished from an ordinary all-caps variety/pack label (e.g. "RED
# GLOBE", "VARIOUS BLACK VARIETIES") which has no such marker after it.
_REGION_FOLLOWUP = 'Sales F.O.B'

# A line describing one priced size/pack: "<label> <price>[-<price>] [mostly
# <price>-<price>] ...". The optional "mostly" band is the one the spec
# says to use ("top of the quoted 'mostly' price band ... not the full
# outer range, which includes rarer outlier trades").
_PRICE_LINE = re.compile(
    r'^([A-Za-z0-9x/,\- ]+?) +(\d+\.\d{2})(?:-(\d+\.\d{2}))?(?: +mostly +(\d+\.\d{2})-(\d+\.\d{2}))?'
)

# Crop section marker, e.g. "---TOMATOES, CHERRY: SUPPLY VERY LIGHT. ..."
_CROP_LINE = re.compile(r'^---([A-Z, ]+?):')


def parse_two_column_regions(page, exclude_region_pattern=None):
    """Parse one page of a Specialty Crops Market News report (Florida
    vegetables / California fruit) into priced rows tagged by region.

    Each region section is headed by a bold bar (all-caps line immediately
    followed by "Sales F.O.B...."); rows appearing before any such header
    in a column have no reliable region — the spec explicitly calls for an
    exclude-and-flag failure mode rather than silently guessing (a column
    boundary in a 2-column layout means a block with no header of its own
    would otherwise silently inherit the previous column's region, which is
    not necessarily correct), so those rows are dropped, not attributed.

    `exclude_region_pattern`, if given, is a compiled regex checked against
    each region header (e.g. Californias's "MEXICO CROSSINGS THROUGH..." —
    imports mixed into an otherwise-domestic report, which must never be
    included).
    """
    mid = page.width / 2
    columns = [
        page.crop((0, 0, mid, page.height)).extract_text() or '',
        page.crop((mid, 0, page.width, page.height)).extract_text() or '',
    ]

    rows = []
    for column_text in columns:
        lines = column_text.split('\n')
        current_region = None
        region_excluded = False
        current_crop = None
        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''

            if line.isupper() and not line.startswith('---') and next_line.startswith(_REGION_FOLLOWUP):
                current_region = line
                region_excluded = bool(exclude_region_pattern and exclude_region_pattern.search(line))
                current_crop = None
                continue

            crop_match = _CROP_LINE.match(line)
            if crop_match:
                current_crop = crop_match.group(1).strip().title()
                continue

            if current_region is None or region_excluded or current_crop is None:
                continue

            price_match = _PRICE_LINE.match(line)
            if not price_match:
                continue
            label, lo, hi, mostly_lo, mostly_hi = price_match.groups()
            if mostly_hi:
                price = float(mostly_hi)
                range_text = f'{mostly_lo}-{mostly_hi} (mostly band; full range {lo}-{hi or lo})'
            elif hi:
                price = float(hi)
                range_text = f'{lo}-{hi}'
            else:
                price = float(lo)
                range_text = lo

            rows.append(
                {
                    'region': current_region.title(),
                    'crop': current_crop,
                    'label': label.strip(),
                    'price': price,
                    'range_text': range_text,
                }
            )
    return rows
