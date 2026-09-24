"""Tier 1/2 registry for the fallback discovery chain (see discovery.py):
a small, explicit, pluggable per-territory map from CountryReferenceCatalog
`country_code` (ISO alpha-2) to its own national statistics authority
(tier 1) and, failing that, its administering/parent country's statistics
office — ONLY if it publishes a breakout specific to that territory, never
the parent's national total (tier 2).

There is no universal API for this — every entry here was individually
researched and verified live (real URL, real robots.txt, real look at what
data is actually published), never guessed or fabricated. A country_code
absent from TERRITORY_SOURCES simply has no tier 1/2 candidate registered
and falls straight through to tier 3 (FRED) or `none_found` — that's the
expected, common case, not a bug. Add more entries here as they get
researched; discovery.py's chain logic never needs to change to support a
new one.

Two territories were researched for this feature:

Turks and Caicos Islands (TC) — the Turks & Caicos Islands Statistics
Authority (https://www.gov.tc/stats/) is real, currently operating, and
its international-trade page IS robots.txt-accessible (gov.tc's
robots.txt only disallows /administrator/, /api/, /bin/, /cache/, /cli/,
/components/, /includes/, /installation/, /language/, /layouts/,
/libraries/, /logs/, /modules/, /plugins/, /tmp/ — a stock Joomla list,
not /stats/). It genuinely publishes downloadable trade datasets (Google
Sheets exports: "Value of Imports and Exports", "Imports by Country",
"Merchandise Imports by SITC Sections/Divisions", ...). It is marked
`integrated: False` here anyway: that data is classified under SITC
(Standard International Trade Classification), not HS (Harmonized
System) — this app's entire category → product → subheading drill-down is
HS chapter/heading/subheading-shaped (see comtrade/classification.py), and
there's no verified SITC→HS correlation table in this app to populate that
schema from SITC figures without fabricating a mapping. A real adapter
could be added later (set `integrated: True` and provide `fetch`) if a
verified crosswalk is built.

Sint Maarten (SX) — both candidate tiers were checked:
  - Tier 1, its own statistics office: sintmaartengov.org's Department of
    Statistics (STAT) page describes its mandate, including merchandise
    import/export classification, but links to no actual dataset, PDF, or
    API — nothing to fetch. Marked `integrated: False`.
  - Tier 2, the administering country's office: Statistics Netherlands
    (CBS), the source the original feature request named as an example,
    turns out NOT to apply — statistical responsibility for Sint Maarten
    was transferred FROM CBS TO Sint Maarten's own STAT department in
    2010, ahead of its constitutional change that year, and CBS no longer
    publishes a Sint-Maarten-specific trade breakout (it only covers the
    Netherlands' own trade). No tier-2 entry is registered for SX as a
    result — this is exactly the "step 2 genuinely doesn't apply, fall
    through" case the fallback chain is designed to handle.

Both territories fall through to tier 3 (FRED) in this build — see
discovery.py and fred_client.py, both of which have real, verified,
working series for these two (EXP2430/IMP2430 for TC, EXP2774/IMP2774 for
SX, confirmed live on fred.stlouisfed.org).
"""

TERRITORY_SOURCES: dict[str, dict] = {
    'TC': {
        'tier1': {
            'source_id': 'tci_statistics_authority',
            'name': 'Turks and Caicos Islands Statistics Authority',
            'check_url': 'https://www.gov.tc/stats/statistics/economic/11-international-trade',
            'integrated': False,
            'unavailable_reason': (
                'Publishes real, robots.txt-accessible trade data (Google Sheets: imports by country, '
                'merchandise imports by SITC section/division), but classified under SITC, not HS — no '
                "verified SITC-to-HS crosswalk exists in this app to populate the category/product/"
                'subheading schema without fabricating a mapping.'
            ),
        },
        'tier2': None,
    },
    'SX': {
        'tier1': {
            'source_id': 'sxm_stat_department',
            'name': 'Sint Maarten Department of Statistics (STAT)',
            'check_url': 'https://www.sintmaartengov.org/Ministries/Departments/Pages/The-Department-of-Statistics-(STAT).aspx',
            'integrated': False,
            'unavailable_reason': "Describes STAT's mandate but publishes no downloadable trade dataset, PDF, or API to fetch.",
        },
        # CBS Netherlands ruled out for tier 2 — see module docstring.
        'tier2': None,
    },
}


def tiers_for(country_code: str) -> tuple[dict | None, dict | None]:
    """(tier1_entry, tier2_entry) for a country_code, or (None, None) if
    nothing is registered for it."""
    entry = TERRITORY_SOURCES.get((country_code or '').upper())
    if not entry:
        return None, None
    return entry.get('tier1'), entry.get('tier2')
