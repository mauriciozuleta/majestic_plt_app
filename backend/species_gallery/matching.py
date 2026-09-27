"""Cross-market variety matching (spec section 4) — deterministic, plain
point-scoring over each variety's own `characteristics_json` fields, never
AI, never image similarity. Every point is auditable: the score breakdown
lists exactly which fields matched and which didn't, so a result is never a
black box.

One point per shared trait whose values agree (a trait missing on either
side never scores, for or against — it's simply not counted, not treated
as a mismatch). All traits are weighted equally (1 point each) — deliberately
simple and documented here rather than a tuned/opaque weighting scheme,
per this feature's own "keep it simple and documented" instruction. Ties
(more than one target variety reaching the same top score) are broken by
MIN_COMPARABLE_FIELDS below first (see its own comment for the real data
this was measured against — a real, reported bug: a candidate with ZERO
comparable data could out-rank one that actually had shared data and
disagreed on it, purely by creation order, since the old tie-break never
looked at max_possible at all), then confirmed-over-unverified, then by
created_at (earlier bootstrap wins, for stability)."""

import json
from dataclasses import dataclass, field

# Real distribution this number was measured against (recomputed live
# against every same-species variety pair actually in the `varieties` table
# — see VARIETY_GALLERY_METHODOLOGY.md Part 4.2 for the full derivation,
# re-run any time via species_gallery.matching.score_variety_pair against
# real rows): as of the fix, 5 real bootstrapped varieties existed, spanning
# 2 species — only Solanum lycopersicum had more than one variety (4:
# "Kidney" Tomato, Tomate Chonto, Caribe Tomato, Carolina Gold Tomato),
# giving 6 real pairwise comparisons. Their real max_possible values: 0 in
# 4 of 6 pairs, 1 in the other 2 (never higher — max_possible is the
# INTERSECTION of both sides' filled fields, so it can never exceed the
# smaller side's own field-fill count, which topped out at 2 per variety
# in this sample). Requiring max_possible >= 2 would have rejected every
# real comparison this app had ever produced (0 of 6) — the data doesn't
# justify it. Requiring >= 1 keeps exactly the pairs that had a genuine
# shared, comparable trait (2 of 6: Tomate Chonto vs Carolina Gold — a real
# disagreement on `shape` — and Caribe vs Carolina Gold — a real agreement
# on `firmness`) while excluding the 4 pairs with literally nothing in
# common to compare — precisely the bug this constant targets, without
# being so strict it excludes nearly everything given how sparse real
# LangSearch-derived characteristics currently are.
MIN_COMPARABLE_FIELDS = 1


@dataclass
class MatchCandidate:
    variety_id: str
    variety_name: str
    source_country: str
    confidence_status: str
    created_at: str
    characteristics: dict


@dataclass
class MatchResult:
    best: MatchCandidate | None
    score: int
    max_possible: int
    field_breakdown: list[dict] = field(default_factory=list)  # [{field, source_value, target_value, matched}]
    all_candidates: list[dict] = field(default_factory=list)  # every candidate's own score, for transparency


def _load_characteristics(raw_json: str) -> dict:
    try:
        return json.loads(raw_json) or {}
    except Exception:
        return {}


def score_variety_pair(source_characteristics: dict, target_characteristics: dict) -> tuple[int, int, list[dict]]:
    """Returns (score, max_possible, breakdown). max_possible is the number
    of traits BOTH sides actually have a value for (traits only one side
    has a value for can't score either way, so they don't inflate the
    denominator) — this keeps the score meaningful when characteristics
    are sparse (e.g. an unconfirmed bootstrap that only filled 2 of 5
    traits) rather than making every comparison look artificially weak
    against a fixed 5-point denominator."""
    breakdown = []
    score = 0
    max_possible = 0
    all_fields = sorted(set(source_characteristics.keys()) | set(target_characteristics.keys()))
    for field_name in all_fields:
        source_value = source_characteristics.get(field_name)
        target_value = target_characteristics.get(field_name)
        if source_value is None or target_value is None:
            continue  # missing on either side never scores for or against
        max_possible += 1
        matched = source_value == target_value
        if matched:
            score += 1
        breakdown.append({'field': field_name, 'source_value': source_value, 'target_value': target_value, 'matched': matched})
    return score, max_possible, breakdown


def find_best_match(source_variety_row, target_variety_rows: list) -> MatchResult:
    """`source_variety_row`/`target_variety_rows` are models.Variety ORM rows
    (or anything with the same attributes). Scores every target-country
    variety of the same species against the source and returns the highest
    scorer with its full breakdown, plus every candidate's own score for
    transparency (never just the winner, silently)."""
    source_characteristics = _load_characteristics(source_variety_row.characteristics_json)

    all_candidates = []
    scored = []
    for target_row in target_variety_rows:
        target_characteristics = _load_characteristics(target_row.characteristics_json)
        score, max_possible, breakdown = score_variety_pair(source_characteristics, target_characteristics)
        candidate = MatchCandidate(
            variety_id=target_row.id,
            variety_name=target_row.variety_name,
            source_country=target_row.source_country,
            confidence_status=target_row.confidence_status,
            created_at=target_row.created_at,
            characteristics=target_characteristics,
        )
        all_candidates.append({'variety_id': target_row.id, 'variety_name': target_row.variety_name, 'score': score, 'max_possible': max_possible})
        scored.append((score, candidate, breakdown, max_possible))

    if not scored:
        return MatchResult(best=None, score=0, max_possible=0, field_breakdown=[], all_candidates=[])

    # Highest score wins first. Ties are then broken by MIN_COMPARABLE_FIELDS
    # (row[3] is max_possible): a candidate that met the real-data-backed
    # comparability bar (`>= MIN_COMPARABLE_FIELDS` sorts False, i.e. first)
    # outranks one that didn't (e.g. genuinely had zero shared fields to
    # compare) — this is the actual fix for the reported bug, where a 0/0
    # "no data at all" candidate could beat a 0/1 "compared and disagreed"
    # candidate purely by creation order. Within that, more comparable
    # fields (`-row[3]`) is preferred as further real signal, then
    # confirmed-over-unverified, then by earlier created_at (stable,
    # auditable — never a coin flip).
    scored.sort(key=lambda row: (
        -row[0],
        row[3] < MIN_COMPARABLE_FIELDS,
        -row[3],
        row[1].confidence_status != 'confirmed',
        row[1].created_at,
    ))
    best_score, best_candidate, best_breakdown, best_max = scored[0]
    return MatchResult(best=best_candidate, score=best_score, max_possible=best_max, field_breakdown=best_breakdown, all_candidates=all_candidates)
