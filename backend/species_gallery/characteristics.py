"""Turns a LangSearch web-search result into the `characteristics` fields
this feature's spec calls for (shape, firmness, primary_culinary_use,
skin_flesh, ripening_type for produce) — by plain keyword matching against
the search results' own snippet/text, never a model call of any kind (the
$0 constraint applies here too: an LLM would be the obvious way to do this
well, so it's deliberately NOT used). A trait whose keyword vocabulary
doesn't appear anywhere in the search text is left null rather than
guessed — the same "never invent a plausible-looking wrong answer"
discipline as the rest of this app.

Schema-less by design (species_gallery/models.Variety.characteristics_json
is a JSON blob, not fixed columns) so a different category can extend this
with its own trait vocabulary without a migration — TRAIT_VOCABULARY below
is produce-first but structured so a meat/seafood set (cut, fat_marbling,
typical_size) is just another entry in the same dict, read the same way.
"""

import re
from typing import Optional

# category -> {trait_name: {value: [keyword, ...]}}. Longest/most specific
# keyword wins when two values' keyword lists both appear (e.g. "round" and
# "oblong" both present just means neither is picked confidently — see
# extract_characteristics below, which requires a value's keywords to
# appear WITHOUT a competing value's keywords also appearing, or it leaves
# that trait null rather than guessing between them).
TRAIT_VOCABULARY = {
    'produce': {
        'shape': {
            'round': ['round', 'globe-shaped', 'spherical'],
            'oblong': ['oblong', 'elongated', 'oval'],
            'pear-shaped': ['pear-shaped', 'pyriform'],
            'flattened': ['flattened', 'flat-shaped'],
            'heart-shaped': ['heart-shaped'],
        },
        'firmness': {
            'firm': ['firm', 'dense flesh', 'crisp'],
            'soft': ['soft', 'tender flesh', 'delicate flesh'],
        },
        'primary_culinary_use': {
            'fresh eating': ['fresh eating', 'eaten fresh', 'table variety', 'snacking'],
            'cooking': ['cooking variety', 'used for cooking', 'culinary use', 'sauce'],
            'salad': ['salad'],
            'juicing': ['juicing', 'juice production'],
            'processing': ['processing variety', 'canning', 'industrial use'],
        },
        'skin_flesh': {
            'red': ['red skin', 'red-skinned', 'red flesh'],
            'green': ['green skin', 'green-skinned'],
            'yellow': ['yellow skin', 'yellow-skinned', 'yellow flesh'],
            'orange': ['orange skin', 'orange-skinned', 'orange flesh'],
            'purple': ['purple skin', 'purple-skinned'],
        },
        'ripening_type': {
            'climacteric': ['ripens after harvest', 'climacteric'],
            'non-climacteric': ['does not ripen after harvest', 'non-climacteric'],
        },
    },
}


def _combined_text(search_results: list[dict]) -> str:
    parts = []
    for item in search_results:
        parts.append(item.get('name') or '')
        parts.append(item.get('snippet') or '')
        parts.append(item.get('text') or '')
    return ' '.join(parts).lower()


def extract_characteristics(search_results: list[dict], category: str = 'produce') -> dict:
    """Returns {trait: value | None} for every trait this `category` defines
    in TRAIT_VOCABULARY, filled only where the search text contains one
    value's keywords and not a conflicting value's — an empty dict (all
    None) is a legitimate, honest result when the search text doesn't say
    anything the vocabulary recognizes."""
    vocabulary = TRAIT_VOCABULARY.get(category, {})
    text = _combined_text(search_results)
    result = {}
    for trait, values in vocabulary.items():
        matched = None
        match_count = 0
        for value, keywords in values.items():
            if any(re.search(re.escape(kw), text) for kw in keywords):
                matched = value
                match_count += 1
        result[trait] = matched if match_count == 1 else None
    return result
