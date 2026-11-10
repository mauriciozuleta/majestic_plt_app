"""Plain-language differences between two versions of a dataset, for the history view and for the approval screen."""

import difflib

from . import guard

SAMPLE = 8
MAX_DIFF_LINES = 200_000


def _identity(product: dict) -> str:
    if product.get('id') not in (None, ''):
        return f"id:{product['id']}"
    name = product.get('name') or product.get('product_en') or product.get('nameEs') or ''
    return f"{str(name).strip().lower()}|{product.get('unit') or ''}|{product.get('category') or ''}"


def diff_products(old: list | None, new: list | None) -> dict:
    old = old if isinstance(old, list) else []
    new = new if isinstance(new, list) else []
    old_by, new_by = {_identity(p): p for p in old if isinstance(p, dict)}, {_identity(p): p for p in new if isinstance(p, dict)}
    added, removed = [k for k in new_by if k not in old_by], [k for k in old_by if k not in new_by]
    changed = []
    for key in new_by.keys() & old_by.keys():
        before, after = old_by[key].get('price'), new_by[key].get('price')
        if before != after:
            changed.append({'product': old_by[key].get('name') or old_by[key].get('product_en') or key, 'from': before, 'to': after})
    label = lambda p: p.get('name') or p.get('product_en') or p.get('nameEs') or _identity(p)  # noqa: E731
    return {'type': 'products', 'old_count': len(old), 'new_count': len(new), 'added': len(added), 'removed': len(removed), 'price_changed': len(changed),
            'added_sample': [label(new_by[k]) for k in added[:SAMPLE]], 'removed_sample': [label(old_by[k]) for k in removed[:SAMPLE]], 'price_changed_sample': changed[:SAMPLE]}


def diff_market_size(kind: str, old: dict | None, new: dict | None) -> dict:
    old_total, old_rows = guard.market_size_total(kind, (old or {}).get('data', old or {}))
    new_total, new_rows = guard.market_size_total(kind, (new or {}).get('data', new or {}))
    return {'type': 'market_size', 'old_total': old_total, 'new_total': new_total, 'old_rows': old_rows, 'new_rows': new_rows,
            'change_pct': round((new_total - old_total) / old_total * 100, 1) if old_total else None}


def diff_files(old: bytes | None, new: bytes | None) -> dict:
    old, new = old or b'', new or b''
    result = {'type': 'file', 'old_size': len(old), 'new_size': len(new), 'identical': old == new}
    try:
        old_lines, new_lines = old.decode('utf-8').splitlines(), new.decode('utf-8').splitlines()
    except UnicodeDecodeError:
        return result
    result.update(old_lines=len(old_lines), new_lines=len(new_lines))
    if len(old_lines) + len(new_lines) <= MAX_DIFF_LINES and old != new:
        added = removed = 0
        for line in difflib.unified_diff(old_lines, new_lines, lineterm='', n=0):
            if line.startswith('+') and not line.startswith('+++'):
                added += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed += 1
        result.update(lines_added=added, lines_removed=removed)
    return result


def diff(scope: str, old_kind: str | None, old, new_kind: str | None, new) -> dict:
    """Dispatch on the scope's type. `old`/`new` are the decoded data (None = nothing / deleted)."""
    if scope.startswith('market_size:'):
        return diff_market_size(scope.split(':', 1)[1], old, new)
    if scope.startswith('file:'):
        return diff_files(old if old_kind == 'file' else None, new if new_kind == 'file' else None)
    return diff_products(old if old_kind == 'json' else None, new if new_kind == 'json' else None)
