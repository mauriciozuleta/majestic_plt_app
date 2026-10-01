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
# <price>[-<price>]] ...". The optional "mostly" band is the one the spec
# says to use ("top of the quoted 'mostly' price band ... not the full
# outer range, which includes rarer outlier trades") — and it can be a
# single value ("6.00-12.00 mostly 10.00"), not only a range.
_PRICE_LINE = re.compile(
    r'^([A-Za-z0-9x/,\- ]+?) +(\d+\.\d{2})(?:-(\d+\.\d{2}))?(?: +mostly +(\d+\.\d{2})(?:-(\d+\.\d{2}))?)?'
)

# A priced line that is really the wrapped tail of the previous line's
# qualifier ("...mostly 23.95-25.95 some" / "varieties 29.95-30.95") — a
# sub-price for part of the same lot, not a separate product row.
_CONTINUATION_TAIL = re.compile(r'\b(some|few|occasional)$', re.I)

# A variety/type label USDA prints above a price block ("RED GLOBE", "Autumn
# Royal", "Hass", "ROMA", "MATURE GREENS"): at most four capitalized words, no
# punctuation or digits — which is what keeps a wrapped market-narrative line
# ("ABOUT STEADY. Extra services included.") or a grade line ("85% U.S. One or
# Better") from being mistaken for one.
_VARIETY_LINE = re.compile(r'^[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,3}$')

# Crop section marker, e.g. "---TOMATOES, CHERRY: SUPPLY VERY LIGHT. ..."
_CROP_LINE = re.compile(r'^---([A-Z, ]+?):')

# The container line USDA prints above a block of size grades ("25 lb cartons
# loose", "flats 8 1-lb containers with lids", "cartons 2 layer") — it applies
# to every priced size line under it until the next container/crop/region line.
_PACK_WORD = re.compile(r'\b(cartons?|containers?|flats?|bushels?|cups?|baskets?|lugs?|boxes|bags?|crates?|sacks?)\b', re.I)

# Net weight, only when the report itself states it in lb/oz: a count of
# fixed-weight units ("flats 12 6-oz cups" = 72 oz) or a single stated weight
# ("25 lb cartons"). Volume/layer packs ("1-pint", "1/2 bushel", "2 layer")
# state no weight and deliberately return None.
_COUNT_EACH_WEIGHT = re.compile(r'\b(\d+)\s+(\d+(?:\.\d+)?)-(lb|oz)\b', re.I)
_SINGLE_WEIGHT = re.compile(r'\b(\d+(?:\.\d+)?)\s*-?\s*(lb|oz)\b', re.I)


def pack_net_weight_lb(pack):
    if not pack:
        return None
    match = _COUNT_EACH_WEIGHT.search(pack)
    if match:
        count, each, unit = int(match.group(1)), float(match.group(2)), match.group(3).lower()
        total = count * each
    else:
        match = _SINGLE_WEIGHT.search(pack)
        if not match:
            return None
        total, unit = float(match.group(1)), match.group(2).lower()
    return total / 16 if unit == 'oz' else total


def produce_rows_with_stated_weight(rows):
    """Keeps only rows whose USDA container line states a net weight — a
    per-carton price with no stated weight can't become a $/kg figure, so it
    isn't stored at all rather than kept as an unconvertible row."""
    kept = []
    for row in rows:
        weight_lb = pack_net_weight_lb(row['pack'])
        if weight_lb:
            kept.append({**row, 'pack_net_weight_lb': weight_lb})
    return kept


def produce_product_name(row):
    """"Grapes, Organic Red Seedless (San Joaquin Valley ...)" — the variety/
    organic qualifier USDA prints above a price block, so two differently
    priced lots of the same crop and region never share one product name."""
    qualifier = ' '.join(part for part in ('Organic' if row['organic'] else None, row['variety']) if part)
    crop = f"{row['crop']}, {qualifier}" if qualifier else row['crop']
    return f"{crop} ({row['region']})"


def produce_unit_label(row):
    if row['label'] == row['pack']:
        return f"USD/{row['pack']}"
    return f"USD/{row['pack']} — {row['label']}"


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
        current_pack = None
        current_variety = None
        current_organic = False
        previous_line = ''
        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue
            is_continuation = bool(_CONTINUATION_TAIL.search(previous_line))
            previous_line = line
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''

            if line.isupper() and not line.startswith('---') and next_line.startswith(_REGION_FOLLOWUP):
                current_region = line
                region_excluded = bool(exclude_region_pattern and exclude_region_pattern.search(line))
                current_crop = None
                current_pack = None
                current_variety = None
                current_organic = False
                continue

            crop_match = _CROP_LINE.match(line)
            if crop_match:
                current_crop = crop_match.group(1).strip().title()
                current_pack = None
                current_variety = None
                current_organic = False
                continue

            if current_region is None or region_excluded or current_crop is None:
                continue

            price_match = _PRICE_LINE.match(line)
            if not price_match:
                if _PACK_WORD.search(line):
                    current_pack = line
                elif line.upper() == 'ORGANIC':
                    current_organic = True
                    current_variety = None
                    current_pack = None
                elif _VARIETY_LINE.match(line):
                    current_variety = line.title() if line.isupper() else line
                    current_pack = None
                continue
            if is_continuation:
                continue
            label, lo, hi, mostly_lo, mostly_hi = price_match.groups()
            label = label.strip()
            # A priced line can carry its own container ("flats 12 6-oz cups
            # with lids 16.00-22.00") instead of sitting under a separate one.
            pack = label if _PACK_WORD.search(label) else current_pack
            if mostly_hi:
                price = float(mostly_hi)
                range_text = f'{mostly_lo}-{mostly_hi} (mostly band; full range {lo}-{hi or lo})'
            elif mostly_lo:
                price = float(mostly_lo)
                range_text = f'mostly {mostly_lo} (full range {lo}-{hi or lo})'
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
                    'variety': current_variety,
                    'organic': current_organic,
                    'label': label,
                    'pack': pack,
                    'price': price,
                    'range_text': range_text,
                }
            )
    return rows
