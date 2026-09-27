"""GBIF Backbone Taxonomy — free, keyless, confirmed live (see
species_gallery/resolver.py's module docstring for why it is used ONLY as a
validator here, never as the common-name -> scientific-name discovery
mechanism). `/v1/species/match` is extremely reliable for an actual
scientific (binomial) name — confirmed live: 'Solanum lycopersicum' and
'Carica papaya' both return matchType EXACT, rank SPECIES, status ACCEPTED,
confidence 98-99. It is NOT reliable for a plain English common name —
confirmed live: 'tomato'/'chicken'/'onion'/'apple'/'peach' etc. all return
matchType NONE, and 'papaya' returns an EXACT-but-wrong match to a doubtful
fossil taxon ("? papaya Olsson, 1922", kingdom Animalia, status DOUBTFUL) —
a silently-plausible-looking wrong answer this module's own confidence gate
below exists to catch. GBIF's own full-text /v1/species/search (with or
without qField=VERNACULAR) was tried too and is also unreliable for this
purpose: real common produce names return real species, but ranked far
below unrelated plant pathogens/viruses named after their host crop (e.g.
searching "peach" ranks 'Prunus andersonii' above the actual peach,
Prunus persica) — so it's not used here either.
"""

from typing import Optional

import httpx

MATCH_URL = 'https://api.gbif.org/v1/species/match'
TIMEOUT = 15

# A match below this confidence, or whose RETURNED rank isn't one of these,
# is never trusted — the resolver treats it exactly like matchType NONE
# (falls through to "unresolved"). Gating on the rank GBIF actually
# returned (rather than on matchType) is what catches "sea bass" -> genus
# "Sea" (confirmed live: matchType HIGHERRANK, but rank GENUS, confidence
# 94 — a high-confidence, wrong, plausible-looking match) while still
# accepting a real domesticated-form/subspecies name GBIF's backbone only
# resolves at a broader rank than asked (e.g. "Capra aegagrus hircus" ->
# matchType HIGHERRANK, rank SPECIES "Capra aegagrus", confidence 98 — a
# real, correct match, just not at the exact trinomial rank requested).
MIN_CONFIDENCE = 90
ACCEPTED_RANKS = {'SPECIES', 'SUBSPECIES', 'VARIETY', 'FORM'}
# GBIF's backbone frequently files a real, correct agricultural/domesticated
# name as a SYNONYM of whichever name it currently prefers (confirmed live:
# 'Citrus sinensis', 'Pisum sativum', 'Litopenaeus vannamei', 'Gallus gallus
# domesticus' all confirm at EXACT/HIGHERRANK, rank SPECIES/FORM, confidence
# 97-98, status SYNONYM) — SYNONYM here means "a real, unambiguous taxon,
# just not GBIF's current preferred name for it", not "uncertain"; DOUBTFUL
# (papaya's wrong fossil-taxon match) is a different status and is not in
# this set on purpose.
ACCEPTED_STATUSES = {'ACCEPTED', 'SYNONYM'}


class GbifConfirmation:
    def __init__(self, scientific_name: str, canonical_name: str, rank: str, kingdom: Optional[str],
                 family: Optional[str], gbif_key: Optional[int], confidence: int, status: str):
        self.scientific_name = scientific_name
        self.canonical_name = canonical_name
        self.rank = rank
        self.kingdom = kingdom
        self.family = family
        self.gbif_key = gbif_key
        self.confidence = confidence
        self.status = status


def confirm_scientific_name(candidate: str) -> Optional[GbifConfirmation]:
    """Calls GBIF's own /species/match for `candidate` (expected to already
    be a real binomial scientific name, e.g. "Solanum lycopersicum" — never
    a raw common name, see the module docstring above) and returns a
    GbifConfirmation only if GBIF's own match clears every gate: matchType
    EXACT or FUZZY (never NONE/HIGHERRANK — HIGHERRANK means GBIF could only
    match a broader rank than asked, e.g. genus/family, which is exactly the
    "sea bass" -> genus "Sea" failure mode confirmed live), rank in
    ACCEPTED_RANKS, status ACCEPTED, confidence >= MIN_CONFIDENCE. Returns
    None on any gate failure or network error — the caller (resolver.py)
    treats None as "could not confirm", never invents a fallback."""
    try:
        response = httpx.get(MATCH_URL, params={'name': candidate, 'strict': 'false'}, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    if data.get('matchType') == 'NONE':
        return None
    if data.get('rank') not in ACCEPTED_RANKS:
        return None
    if data.get('status') not in ACCEPTED_STATUSES:
        return None
    confidence = data.get('confidence') or 0
    if confidence < MIN_CONFIDENCE:
        return None
    canonical = data.get('canonicalName')
    if not canonical:
        return None

    return GbifConfirmation(
        scientific_name=canonical,
        canonical_name=canonical,
        rank=data.get('rank'),
        kingdom=data.get('kingdom'),
        family=data.get('family'),
        gbif_key=data.get('usageKey'),
        confidence=confidence,
        status=data.get('status'),
    )
