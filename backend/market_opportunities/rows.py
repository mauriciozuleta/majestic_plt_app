"""The comparison rows: one matched source/target pair becomes a row with both sides' original quotes, both USD/kg figures, the exchange rates used and the reasons a
person should check it; then several matches of one source product become ONE reference row. A line for line port of `buildComparisonRow`, `referenceRow` and
`oneRowPerSourceProduct` of src/services/marketOpportunities.js (the text of the reasons is part of what people read, so it is kept word for word)."""

from decimal import ROUND_HALF_UP, Decimal

from ..portfolio.merge import per_kg  # noqa: F401 — re-exported for the engine


def _half_up(value) -> Decimal:
    """Round to cents the way JavaScript's toLocaleString does: half away from zero on the SHORTEST decimal form of the number (1.005 -> 1.01, 2.675 -> 2.68), where
    Python's own round() works on the binary value and rounds halves to even."""
    return Decimal(repr(float(value))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def amount(value) -> str:
    """12 -> '12', 12.5 -> '12.5', 1234.567 -> '1,234.57' (JavaScript's toLocaleString('en-US', {maximumFractionDigits: 2}))."""
    text = f'{_half_up(value):,.2f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def usd(value) -> str:
    return f'USD {_half_up(value):,.2f}'


def _rate(rates: dict, currency):
    return rates.get(currency) if currency else None


def _usd_per_kg(product: dict, rate) -> float | None:
    if product.get('perKgLocal') is None or not (rate or {}).get('available'):
        return None
    return product['perKgLocal'] / rate['rate']


def build_comparison_row(source_product: dict, target_product: dict, match_tier: str, source_country: str, target_country: str, rates: dict, ai_note: str | None = None) -> dict:
    source_rate, target_rate = _rate(rates, source_product.get('priceCurrency')), _rate(rates, target_product.get('priceCurrency'))
    # both sides convert independently to USD — DIVIDE by the stored rate (units of that currency per 1 USD), never source currency straight to target currency
    source_normalized, target_normalized = _usd_per_kg(source_product, source_rate), _usd_per_kg(target_product, target_rate)

    reasons: list[str] = []
    if match_tier == 'curated_override':
        reasons.append('Matched via a curated name override, not an identical name after translation/normalization — see crossCountryMatchOverrides.js.')
    if match_tier == 'hs_code':
        code = f"{source_product.get('hsCode')}{': ' + source_product['hsDescription'] if source_product.get('hsDescription') else ''}"
        reasons.append(
            f'Shares HS code {code}, and AI confirmed it as the same product — {ai_note}' if ai_note
            else f"Matched by shared HS code ({code}) only — the AI check couldn't run, and other products on either side may share this same code, so this pairing is one of possibly several."
        )
    if match_tier == 'ai_match':
        reasons.append(f"Matched by AI as the same product{' — ' + ai_note if ai_note else ''}. Not an identical name or a shared HS code; check the pairing before relying on it.")
    if source_product.get('priceLevel') and target_product.get('priceLevel') and source_product['priceLevel'] != target_product['priceLevel']:
        label = lambda level: 'retail' if level == 'retail' else 'wholesale'  # noqa: E731
        reasons.append(
            f"Different price levels — {source_country} is a {label(source_product['priceLevel'])} price, {target_country} is a {label(target_product['priceLevel'])} price. "
            'Part of the gap is packing, freight and retail margin, not an opportunity in itself.'
        )
    if source_product.get('perKgLocal') is None:
        reasons.append(f"Source ({source_country}): {source_product.get('unitComment')}")
    if target_product.get('perKgLocal') is None:
        reasons.append(f"Target ({target_country}): {target_product.get('unitComment')}")
    if source_product.get('priceCurrency') and not (source_rate or {}).get('available'):
        reasons.append(f"No USD exchange rate available for {source_product['priceCurrency']} (source).")
    if target_product.get('priceCurrency') and not (target_rate or {}).get('available'):
        reasons.append(f"No USD exchange rate available for {target_product['priceCurrency']} (target).")
    if not source_product.get('priceCurrency'):
        reasons.append(f'Source ({source_country}): no currency could be determined for this product.')
    if not target_product.get('priceCurrency'):
        reasons.append(f'Target ({target_country}): no currency could be determined for this product.')

    # a count-based unit converted to $/kg with a researched or USDA item weight is never presented with the confidence of an exact-name match
    notes: list[str] = []
    for side, product, country in (('source', source_product, source_country), ('target', target_product, target_country)):
        prefix = 'Source' if side == 'source' else 'Target'
        if (product.get('listingCount') or 0) > 1:
            span = (f" ({product.get('priceCurrency') or ''} {amount(product['listingLow'])}–{amount(product['listingHigh'])} / {product.get('priceUnit') or '—'})"
                    if product.get('listingLow') is not None else '')
            notes.append(f"{prefix} ({country}): median of {product['listingCount']} listings{span}.")
        if not product.get('conversionNote'):
            continue
        notes.append(f"{prefix} ({country}): {product['conversionNote']}")
        if product.get('conversionMethod') == 'reference_item_weight':
            reasons.append(f"{prefix} ({country}): converted from a count-based unit using USDA's published item weight ({product.get('conversionConfidence') or 'medium'} confidence) — an average item, check it before relying on this price.")
        if product.get('conversionMethod') == 'researched_item_weight':
            reasons.append(f"{prefix} ({country}): converted from a count-based unit using a web-researched item weight ({product.get('conversionConfidence') or 'unknown'} confidence) — check the weight before relying on this price.")

    return {
        'product_name': source_product['displayName'],
        'source_country': source_country,
        'target_country': target_country,
        'hs_code': source_product.get('hsCode') or None,
        'source_price_value': source_product.get('priceValue'),
        'source_price_unit': source_product.get('priceUnit'),
        'source_price_currency': source_product.get('priceCurrency'),
        'target_price_value': target_product.get('priceValue'),
        'target_price_unit': target_product.get('priceUnit'),
        'target_price_currency': target_product.get('priceCurrency'),
        'source_price_normalized': source_normalized,
        'target_price_normalized': target_normalized,
        'exchange_rate_source_used': (source_rate or {}).get('rate'),
        'exchange_rate_source_date': (source_rate or {}).get('date'),
        'exchange_rate_target_used': (target_rate or {}).get('rate'),
        'exchange_rate_target_date': (target_rate or {}).get('date'),
        'match_tier': match_tier,
        'review_reasons': reasons,
        'conversion_note': ' '.join(notes) if notes else None,
        # display-only: what the results table shows without re-deriving
        '_target_display_name': target_product['displayName'],
    }


def reference_row(candidates: list[dict]) -> dict:
    """One reference price for a source product matched to several target prices: the MEDIAN matched price by USD/kg (the lower middle one for an even count — the matched
    row's own real recorded price, never an average). The row's note lists what it was drawn from."""
    if len(candidates) == 1:
        return candidates[0]
    priced = sorted((row for row in candidates if row['target_price_normalized'] is not None), key=lambda row: row['target_price_normalized'])
    pool = priced or candidates
    chosen = pool[(len(pool) - 1) // 2]
    names = list(dict.fromkeys(row['_target_display_name'] for row in candidates))
    span = f' ({usd(priced[0]["target_price_normalized"])}–{usd(priced[-1]["target_price_normalized"])}/kg)' if len(priced) > 1 else ''
    note = f"Target ({chosen['target_country']}): reference price is the median of {len(candidates)} matched prices{span}, from {len(names)} product{'' if len(names) == 1 else 's'}: {'; '.join(names)}."
    return {**chosen, 'conversion_note': ' '.join(part for part in (chosen.get('conversion_note'), note) if part)}


def one_row_per_source_product(pairs: list[dict], rows: list[dict]) -> list[dict]:
    """Grouped by the source product's name as the portfolio shows it (two source listings with the same name are one product), then by target country."""
    groups: dict[str, dict[str, list[dict]]] = {}
    for pair, row in zip(pairs, rows):
        by_target = groups.setdefault(pair['sp']['displayName'].strip().lower(), {})
        by_target.setdefault(pair['targetCountry'], []).append(row)
    return [reference_row(candidates) for by_target in groups.values() for candidates in by_target.values()]
