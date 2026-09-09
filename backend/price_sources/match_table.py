"""
Manual, curated Corabastos-name -> La Mayorista-name lookup (spec §3: a human
comparing both real product lists, never a fuzzy-string-match algorithm).

Only entries where the two sources spell the same real product differently
need to be listed here — identical names (e.g. "acelga"/"acelga") already
join automatically on their lowercased name. This is a starting point built
from the first real bulletins pulled for this module, not exhaustive; treat
it as a maintained asset and extend it as more overlaps are confirmed by a
human reviewing both sources side by side.

Keys and values are lowercased product names (matching how each parser
builds its `id` field); both get accent-stripped again by `normalize_id`
after lookup, so writing them with or without accents is equivalent.
"""

CORABASTOS_TO_LA_MAYORISTA_ID = {
    'cebolla cabezona blanca': 'cebolla blanca',
    'cebolla cabezona roja': 'cebolla roja',
    'brocoli': 'brócoli',
    'frijol verde': 'fríjol verde',
    'mazorca': 'chócolo mazorca',
    'arveja verde sabanera': 'arveja verde',
    'repollo': 'repollo blanco',
    'papa criolla lavada': 'papa criolla',
    'platano harton': 'plátano hartón',
    # Corabastos (Bogotá) splits by varietal/region where La Mayorista
    # (Medellín) lists one generic product, or the two markets use
    # different regional names for the same vegetable.
    'yuca armenia': 'yuca',
    'yuca llanera': 'yuca',
    'cebolla larga': 'cebolla junca',  # Bogotá "larga" == Antioquia "junca" (scallion) — not "cebolla puerro" (leek)
    'rabano rojo': 'rabano',
    'pina gold': 'pina oro miel',  # "oro" = "gold"; the only pineapple varieties either bulletin lists
}
