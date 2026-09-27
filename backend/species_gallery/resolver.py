"""Scientific-name resolution — the Variety Gallery's category anchor step
(spec section 1). Confirmed live before writing this: GBIF's own /match and
/search endpoints CANNOT reliably turn a plain English common name into a
scientific name — 'tomato'/'onion'/'apple'/'peach'/'mango'/'grape'/'cassava'/
'chickpea'/'trout'/'chicken' all return matchType NONE from /match, and
common-name /search results rank the actual crop far below unrelated
same-named plant pathogens/viruses (searching "peach" ranks Prunus
andersonii above the real peach, Prunus persica) or, worse, return a
wrong-but-plausible-looking EXACT match ('papaya' -> "? papaya Olsson,
1922", an obscure DOUBTFUL fossil taxon, kingdom Animalia — not the fruit
at all). See gbif_client.py's module docstring for the full live trace.

So GBIF is used here ONLY as a validator/confirmer of a candidate SCIENTIFIC
name this resolver already produced some other way — never as the
common-name discovery mechanism itself. Discovery happens through, in
priority order:

  1. VERNACULAR_PHRASES — a short curated list of well-known multi-word
     common names (e.g. "rainbow trout"), checked against the product's own
     RAW name first. Needed because some HS descriptions bundle several
     congeneric species under one code (e.g. HS0302's trout heading lists
     "Salmo trutta, Oncorhynchus mykiss, ..." together) and only the raw
     product name says which one this particular product actually is.

  2. An embedded Latin binomial inside the HS classification description
     itself — chapter 03 (fish/seafood) descriptions from this app's own
     product_classification.py frequently already spell out the real
     scientific name in parentheses (e.g. "Trout (Salmo trutta,
     Oncorhynchus mykiss, ...)"). When present and (1) didn't already
     resolve it, the FIRST listed binomial is taken as the best-effort
     anchor — documented as such; a customs HS code conflating several
     regionally-distinct species under one heading is a known limitation of
     the classification itself, not something this resolver invents.

  3. COMMODITY_TERMS — the curated dictionary (commodity_dictionary.py),
     matched against the cleaned HS description first (per this feature's
     own design note: a classified product's HS description, e.g.
     "Vegetables; tomatoes, fresh or chilled", is a much cleaner signal than
     a raw variety name like "Chonto Tomato").

  4. COMMODITY_TERMS again, matched against the RAW product name with
     known variety/qualifier words stripped — used only when the product
     has no HS classification yet (a genuine gap, not a preference).

  5. Otherwise: unresolved. Never a guess.

Every candidate produced by (1)/(2)/(3)/(4) is then passed to
gbif_client.confirm_scientific_name() and only persisted if GBIF itself
confirms it (EXACT/FUZZY match, rank SPECIES/SUBSPECIES/VARIETY, status
ACCEPTED, confidence >= 90) — a dictionary typo or a wrong embedded binomial
still can't silently make it through.
"""

import re
from dataclasses import dataclass
from typing import Optional

from . import gbif_client
from .commodity_dictionary import COMMODITY_TERMS, VERNACULAR_PHRASES

# Words stripped from a raw product name before it's checked against the
# dictionary in step 4 — variety/qualifier language that would otherwise
# stop a plain-substring dictionary lookup from matching at all (e.g.
# "Chonto Tomato" only matches the "tomato" key once "chonto" is gone).
# Deliberately conservative: strips known noise words, never invents a
#"base" word the product name doesn't actually contain.
_QUALIFIER_WORDS = {
    'local', 'domestic', 'import', 'imported', 'grade', 'export', 'organic',
    'conventional', 'fresh', 'frozen', 'whole', 'baby', 'jumbo', 'mini',
}

_LATIN_BINOMIAL_RE = re.compile(r'\(([^)]+)\)')
_BINOMIAL_TOKEN_RE = re.compile(r'^[A-Z][a-z]+ [a-z\-]+$')


@dataclass
class ResolutionResult:
    status: str  # 'resolved' | 'unresolved'
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    gbif_key: Optional[int] = None
    gbif_rank: Optional[str] = None
    kingdom: Optional[str] = None
    family: Optional[str] = None
    resolved_from: Optional[str] = None  # 'vernacular_phrase' | 'hs_latin_binomial' | 'commodity_dictionary_hs' | 'commodity_dictionary_name'
    resolved_term: Optional[str] = None  # the exact term/phrase that matched
    reason: Optional[str] = None  # only set when unresolved


def _strip_qualifiers(raw_name: str) -> str:
    words = re.findall(r"[A-Za-z']+", raw_name.lower())
    return ' '.join(w for w in words if w not in _QUALIFIER_WORDS)


def _find_longest_key(text: str, table: dict[str, str]) -> Optional[tuple[str, str]]:
    """Longest-phrase-first substring match of `table`'s keys inside `text`
    (already lowercased) — so a multi-word key like "sweet potato" or
    "chickpea" is preferred over a shorter key ("potato", "pea") that would
    otherwise match first inside it. Returns (matched_term, scientific_name)
    or None."""
    for term in sorted(table.keys(), key=len, reverse=True):
        if re.search(r'\b' + re.escape(term) + r'\b', text):
            return term, table[term]
    return None


def _find_all_keys(text: str, table: dict[str, str]) -> list[tuple[str, str]]:
    return [(term, table[term]) for term in table if re.search(r'\b' + re.escape(term) + r'\b', text)]


def _find_key_disambiguated_by_raw_name(hs_description_lower: str, raw_name_lower: str, table: dict[str, str]) -> Optional[tuple[str, str]]:
    """Some HS headings genuinely combine more than one distinct commodity
    under a single code (e.g. HS0804.50 covers guavas, mangoes AND
    mangosteens together) — picking the longest dictionary term found in
    the description alone is wrong here (confirmed live: a real "guava"
    product's own HS description contains both "guavas" and "mangoes", and
    naive longest-match picked "mangoes" — Mangifera indica — for a product
    that is actually a guava). When more than one dictionary term matches
    the HS description, this prefers whichever of those terms ALSO appears
    in the product's own raw name (the one piece of evidence that actually
    says which commodity this specific product is); only when none of them
    do (or there's exactly one candidate to begin with) does it fall back
    to the longest match, same as _find_longest_key."""
    candidates = _find_all_keys(hs_description_lower, table)
    if not candidates:
        return None
    if len(candidates) > 1:
        # Matched against the SAME SCIENTIFIC NAME the HS-description term
        # maps to, not the literal term string — a dictionary's singular
        # ("guava") and plural ("guavas") keys map to the same value, but a
        # raw product name using the singular form would never literal-
        # string-match the HS description's own plural phrasing ("guavas,
        # mangoes and mangosteens"). Checked live: without this, "guava"
        # (raw name has no plural 's') failed to match the 'guavas' key by
        # literal string and silently fell back to the longest match
        # instead ('mangoes'), resolving a real guava product to Mangifera
        # indica (mango) — exactly the wrong-but-plausible-looking mistake
        # this whole disambiguation step exists to prevent.
        def _any_synonym_in_raw_name(value: str) -> bool:
            return any(re.search(r'\b' + re.escape(k) + r'\b', raw_name_lower) for k, v in table.items() if v == value)

        in_raw_name = [c for c in candidates if _any_synonym_in_raw_name(c[1])]
        if in_raw_name:
            candidates = in_raw_name
    candidates.sort(key=lambda c: len(c[0]), reverse=True)
    return candidates[0]


def _extract_latin_binomial(hs_description: str) -> Optional[str]:
    for paren_match in _LATIN_BINOMIAL_RE.finditer(hs_description):
        for token in paren_match.group(1).split(','):
            token = token.strip()
            if _BINOMIAL_TOKEN_RE.match(token):
                return token
    return None


def resolve_scientific_name(product_name: str, hs_description: Optional[str] = None) -> ResolutionResult:
    raw_lower = (product_name or '').lower()
    candidate: Optional[str] = None
    resolved_from: Optional[str] = None
    resolved_term: Optional[str] = None

    # (1) vernacular phrase, against the raw name
    hit = _find_longest_key(raw_lower, VERNACULAR_PHRASES)
    if hit:
        resolved_term, candidate = hit
        resolved_from = 'vernacular_phrase'

    # (2) embedded Latin binomial in the HS description
    if candidate is None and hs_description:
        binomial = _extract_latin_binomial(hs_description)
        if binomial:
            candidate = binomial
            resolved_from = 'hs_latin_binomial'
            resolved_term = binomial

    # (3) commodity dictionary against the HS description — disambiguated
    # by the raw product name when the HS heading combines more than one
    # commodity (see _find_key_disambiguated_by_raw_name's docstring for
    # the real "guava" vs "mango" case this fixes).
    if candidate is None and hs_description:
        hit = _find_key_disambiguated_by_raw_name(hs_description.lower(), raw_lower, COMMODITY_TERMS)
        if hit:
            resolved_term, candidate = hit
            resolved_from = 'commodity_dictionary_hs'

    # (4) commodity dictionary against the raw name, qualifiers stripped
    if candidate is None:
        stripped = _strip_qualifiers(product_name or '')
        hit = _find_longest_key(stripped, COMMODITY_TERMS)
        if hit:
            resolved_term, candidate = hit
            resolved_from = 'commodity_dictionary_name'

    if candidate is None:
        return ResolutionResult(status='unresolved', reason='no_recognized_commodity_term')

    confirmation = gbif_client.confirm_scientific_name(candidate)
    if confirmation is None:
        return ResolutionResult(
            status='unresolved',
            reason=f'gbif_could_not_confirm:{candidate}',
            resolved_from=resolved_from,
            resolved_term=resolved_term,
        )

    return ResolutionResult(
        status='resolved',
        scientific_name=confirmation.scientific_name,
        gbif_key=confirmation.gbif_key,
        gbif_rank=confirmation.rank,
        kingdom=confirmation.kingdom,
        family=confirmation.family,
        resolved_from=resolved_from,
        resolved_term=resolved_term,
    )


def validate_dictionary() -> list[dict]:
    """Self-test, not used at runtime: re-checks every distinct scientific
    name in COMMODITY_TERMS/VERNACULAR_PHRASES against GBIF live, so the
    dictionary's own claims can be re-verified at any time rather than
    trusted forever from whenever they were first written. Returns one
    failure dict per entry that no longer confirms; an empty list means
    every entry currently passes GBIF's own gates."""
    failures = []
    all_names = set(COMMODITY_TERMS.values()) | set(VERNACULAR_PHRASES.values())
    for name in sorted(all_names):
        confirmation = gbif_client.confirm_scientific_name(name)
        if confirmation is None:
            failures.append({'scientific_name': name, 'reason': 'gbif_did_not_confirm'})
    return failures
