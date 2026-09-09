import unicodedata


def normalize_id(name):
    """Strip accents before using a product name as the cross-source join key.

    Corabastos' bulletin consistently omits accents in product names (e.g.
    'limon comun', 'tomate de arbol') while La Mayorista's sheet keeps them
    ('Limón Común', 'Tomate de Árbol') — matching on the raw lowercased name
    silently failed for most accented products. Both parsers must call this
    so the same product resolves to the same id regardless of source.
    """
    decomposed = unicodedata.normalize('NFD', name)
    stripped = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return stripped.lower().strip()
