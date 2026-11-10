"""'Does this refresh look worse than what is stored?' Pure functions: they return a list of plain-language findings, empty when the update is fine.
An update with findings is held for a person's approval instead of being saved (data_history.store.hold)."""

# Below this many stored rows a drop is noise (6 egg rows becoming 4); from here on a halving is suspicious.
MIN_ROWS_FOR_DROP_CHECK = 10
MAX_ROW_DROP = 0.5
MAX_TOTAL_DROP = 0.25


def check_products(old: list | None, new: list) -> list[str]:
    old_count = len(old) if isinstance(old, list) else 0
    if old_count == 0:
        return []
    if not new:
        return [f'The update returned no products (the stored list has {old_count}).']
    if old_count >= MIN_ROWS_FOR_DROP_CHECK and len(new) < old_count * (1 - MAX_ROW_DROP):
        drop = round((1 - len(new) / old_count) * 100)
        return [f'The update has {len(new)} products, down from {old_count} (-{drop}%).']
    return []


def market_size_total(kind: str, data: dict) -> tuple[float, int]:
    """(grand total, number of category rows) of a stored SAM ('regions' -> categories) or TAM ('categories') aggregate."""
    if kind == 'sam':
        categories = [category for region in data.get('regions', []) for category in region.get('categories', [])]
    else:
        categories = data.get('categories', [])
    return sum(category.get('value') or 0.0 for category in categories), len(categories)


def check_market_size(kind: str, old: dict | None, new: dict) -> list[str]:
    if not old:
        return []
    old_total, old_rows = market_size_total(kind, old)
    new_total, new_rows = market_size_total(kind, new)
    findings = []
    if old_total > 0 and new_total < old_total * (1 - MAX_TOTAL_DROP):
        findings.append(f'The new {kind.upper()} total is {new_total:,.0f}, down from {old_total:,.0f} (-{round((1 - new_total / old_total) * 100)}%). '
                        'A country that Comtrade could not answer is skipped, so a partial run looks like this.')
    if old_rows >= MIN_ROWS_FOR_DROP_CHECK and new_rows < old_rows * (1 - MAX_ROW_DROP):
        findings.append(f'The new {kind.upper()} has {new_rows} category rows, down from {old_rows}.')
    return findings
