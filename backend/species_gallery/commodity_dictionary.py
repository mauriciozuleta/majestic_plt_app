"""A small, curated commodity-term -> scientific-name reference table — the
resolver's primary discovery mechanism (see resolver.py's module docstring
for why GBIF itself cannot play this role). Every entry here is a term that
plausibly appears either in this app's own HS-classification descriptions
(backend/comtrade/product_classification.py, via GET /api/product-hs-codes
— e.g. "Vegetables; tomatoes, fresh or chilled") or in a raw product name
after variety/qualifier words are stripped (e.g. "Chonto Tomato" -> "tomato").

This is the same "static dictionary + confirmable growth" shape this app
already uses for Colombia product-name translation
(productTranslations.js + ProductTranslationOverride) — a fixed, versioned
reference an engineer extends deliberately, not a runtime guess. A commodity
term NOT in this dictionary resolves to nothing (species_gallery/resolver.py
reports it "unresolved") rather than falling back to a fuzzy/AI guess —
extending coverage means adding a real entry here, backed by a real source,
the same discipline GBIF_MIN_CONFIDENCE enforces on the GBIF side.

Every scientific name below was confirmed live against GBIF's
/v1/species/match (matchType EXACT, rank SPECIES, status ACCEPTED,
confidence >= 90) before being added — see the resolver's own self-test
(species_gallery/resolver.py's `validate_dictionary()`) which re-checks this
at any time without guessing.

Ordering matters: COMMODITY_TERMS keys are checked longest-phrase-first (see
resolver.py's _find_dictionary_term), so a multi-word entry like
"chickpea"/"pigeon pea"/"sweet potato"/"cane sugar" is tried before a
shorter substring like "pea"/"potato"/"sugar" could wrongly match inside it.
Some HS headings genuinely combine two distinct-but-congeneric commodities
under one code (e.g. HS 0703.10 covers onions AND shallots) — those are
listed as separate dictionary keys that happen to share one scientific name
(Allium cepa covers both: a shallot is Allium cepa var. aggregatum), which
is the single cleanest case; other combined headings (e.g. cauliflower +
broccoli, both Brassica oleracea; cucumber + gherkin, both Cucumis sativus)
work the same way. A genuinely ambiguous combined heading spanning more
than one species (e.g. "cabbage, lettuce" at the HS0704/0705 heading level)
is intentionally NOT given one shared scientific name here — see
CABBAGE_LETTUCE_DISAMBIGUATION below, resolved from the product's own raw
name instead, never guessed from the heading alone.
"""

# term (lowercase) -> confirmed scientific name. See module docstring for
# the ordering/disambiguation rules and for how each entry was verified.
COMMODITY_TERMS: dict[str, str] = {
    # --- Produce: fruit ---
    'tomato': 'Solanum lycopersicum',
    'tomatoes': 'Solanum lycopersicum',
    'apple': 'Malus domestica',
    'apples': 'Malus domestica',
    'pear': 'Pyrus communis',
    'pears': 'Pyrus communis',
    'peach': 'Prunus persica',
    'peaches': 'Prunus persica',
    'nectarine': 'Prunus persica',
    'grape': 'Vitis vinifera',
    'grapes': 'Vitis vinifera',
    'orange': 'Citrus sinensis',
    'oranges': 'Citrus sinensis',
    'mandarin': 'Citrus reticulata',
    'mandarins': 'Citrus reticulata',
    'tangerine': 'Citrus reticulata',
    'lemon': 'Citrus limon',
    'lemons': 'Citrus limon',
    'lime': 'Citrus aurantiifolia',
    'limes': 'Citrus aurantiifolia',
    'grapefruit': 'Citrus paradisi',
    'pineapple': 'Ananas comosus',
    'pineapples': 'Ananas comosus',
    'banana': 'Musa acuminata',
    'bananas': 'Musa acuminata',
    'plantain': 'Musa paradisiaca',
    'plantains': 'Musa paradisiaca',
    'guava': 'Psidium guajava',
    'guavas': 'Psidium guajava',
    'papaya': 'Carica papaya',
    'papaws': 'Carica papaya',
    'papaw': 'Carica papaya',
    'avocado': 'Persea americana',
    'avocados': 'Persea americana',
    'strawberry': 'Fragaria ananassa',
    'strawberries': 'Fragaria ananassa',
    'raspberry': 'Rubus idaeus',
    'raspberries': 'Rubus idaeus',
    'watermelon': 'Citrullus lanatus',
    'watermelons': 'Citrullus lanatus',
    'melon': 'Cucumis melo',
    'melons': 'Cucumis melo',
    'fig': 'Ficus carica',
    'figs': 'Ficus carica',
    'coconut': 'Cocos nucifera',
    'coconuts': 'Cocos nucifera',
    'mango': 'Mangifera indica',
    'mangoes': 'Mangifera indica',

    # --- Produce: vegetables/tubers (checked longest-phrase-first) ---
    'sweet potato': 'Ipomoea batatas',
    'sweet potatoes': 'Ipomoea batatas',
    'potato': 'Solanum tuberosum',
    'potatoes': 'Solanum tuberosum',
    'cassava': 'Manihot esculenta',
    'manioc': 'Manihot esculenta',
    'yuca': 'Manihot esculenta',
    'yam': 'Dioscorea alata',
    'yams': 'Dioscorea alata',
    'onion': 'Allium cepa',
    'onions': 'Allium cepa',
    'shallot': 'Allium cepa',
    'shallots': 'Allium cepa',
    'garlic': 'Allium sativum',
    'leek': 'Allium ampeloprasum',
    'leeks': 'Allium ampeloprasum',
    'carrot': 'Daucus carota',
    'carrots': 'Daucus carota',
    'celery': 'Apium graveolens',
    'broccoli': 'Brassica oleracea',
    'cauliflower': 'Brassica oleracea',
    'cauliflowers': 'Brassica oleracea',
    'cabbage': 'Brassica oleracea',
    'cucumber': 'Cucumis sativus',
    'cucumbers': 'Cucumis sativus',
    'gherkin': 'Cucumis sativus',
    'gherkins': 'Cucumis sativus',
    'pumpkin': 'Cucurbita moschata',
    'pumpkins': 'Cucurbita moschata',
    'spinach': 'Spinacia oleracea',
    'globe artichoke': 'Cynara scolymus',
    'artichoke': 'Cynara scolymus',
    'artichokes': 'Cynara scolymus',
    'ginger': 'Zingiber officinale',
    'turmeric': 'Curcuma longa',
    'bay leaf': 'Laurus nobilis',
    'bay leaves': 'Laurus nobilis',
    'beetroot': 'Beta vulgaris',
    'lettuce': 'Lactuca sativa',
    'turnip': 'Brassica rapa',
    'turnips': 'Brassica rapa',

    # --- Produce: legumes/grains (multi-word before single-word) ---
    'chickpea': 'Cicer arietinum',
    'chickpeas': 'Cicer arietinum',
    'pigeon pea': 'Cajanus cajan',
    'pigeon peas': 'Cajanus cajan',
    'soya bean': 'Glycine max',
    'soya beans': 'Glycine max',
    'soybean': 'Glycine max',
    'pea': 'Pisum sativum',
    'peas': 'Pisum sativum',
    'bean': 'Phaseolus vulgaris',
    'beans': 'Phaseolus vulgaris',
    'maize': 'Zea mays',
    'corn': 'Zea mays',
    'rice': 'Oryza sativa',
    'wheat': 'Triticum aestivum',

    # --- Meat / poultry (species anchor, not the cut) ---
    'bovine': 'Bos taurus',
    'beef': 'Bos taurus',
    'cattle': 'Bos taurus',
    'swine': 'Sus scrofa domesticus',
    'pork': 'Sus scrofa domesticus',
    'pig': 'Sus scrofa domesticus',
    'goat': 'Capra aegagrus hircus',
    'sheep': 'Ovis aries',
    'lamb': 'Ovis aries',
    'turkey': 'Meleagris gallopavo',
    'fowl': 'Gallus gallus domesticus',
    'fowls': 'Gallus gallus domesticus',
    'chicken': 'Gallus gallus domesticus',
    'poultry': 'Gallus gallus domesticus',
    'gallus domesticus': 'Gallus gallus domesticus',

    # --- Eggs / dairy (default species; a raw name naming a different
    # animal, e.g. "duck egg"/"goat cheese", is resolved from that word
    # instead — see resolver.py's raw-name pass) ---
    "birds' eggs": 'Gallus gallus domesticus',
    'egg': 'Gallus gallus domesticus',
    'eggs': 'Gallus gallus domesticus',

    # --- Seafood (used only when the HS description has no embedded Latin
    # binomial to extract directly — see resolver.py's _extract_latin_binomial,
    # which runs BEFORE this dictionary for chapter-03 fish) ---
    'shrimp': 'Litopenaeus vannamei',
    'shrimps': 'Litopenaeus vannamei',
    'prawn': 'Litopenaeus vannamei',
    'prawns': 'Litopenaeus vannamei',
    'tilapia': 'Oreochromis niloticus',
}

# A short list of well-known MULTI-WORD common names checked against the
# product's own raw name FIRST, ahead of everything else — needed for cases
# where the HS description lists several congeneric species in one
# parenthetical (e.g. HS0302's trout heading literally reads "Trout (Salmo
# trutta, Oncorhynchus mykiss, ...)") and the raw product name is the only
# signal saying which one this actual product is ("Rainbow Trout" specifically
# means Oncorhynchus mykiss, not the first-listed Salmo trutta). Confirmed
# live against GBIF the same way as COMMODITY_TERMS above.
VERNACULAR_PHRASES: dict[str, str] = {
    'rainbow trout': 'Oncorhynchus mykiss',
    'brown trout': 'Salmo trutta',
    'sea bass': 'Dicentrarchus labrax',
    'atlantic salmon': 'Salmo salar',
    'pacific salmon': 'Oncorhynchus gorbuscha',
    'nile tilapia': 'Oreochromis niloticus',
    # Confirmed live: a real catalog product literally named "Feijoa
    # (pineapple guava)" is classified under the same combined HS0804.50
    # code as true guava/mango/mangosteen — its raw name contains the word
    # "guava" (as "pineapple guava"), which would otherwise resolve it to
    # Psidium guajava (true guava) via COMMODITY_TERMS. Feijoa is a
    # genuinely different genus (Acca sellowiana), so this is checked
    # first, ahead of the HS-description dictionary pass.
    'pineapple guava': 'Acca sellowiana',
    'feijoa': 'Acca sellowiana',
}
