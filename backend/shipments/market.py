"""Destination-market rules of the shipment builder (ported line for line from src/services/marketOpportunitySettings.js): the Market Level of a product and its suggested sale
price. The markets are Settings ▸ Market Opportunity settings ▸ Destination Market: [{key, label, min, max, cargo_cap_kg, sell_pct, min_margin_pct, cap_reduction_kg}]."""

import math

# Shipment builder order: wholesalers get their Cargo Cap first, then premium theirs, and the niche markets share what is left.
MARKET_PRIORITY = ['wholesalers', 'premium', 'niche']
# A product with no match in the target market (no target price to compare) is a niche market product by definition.
UNMATCHED_MARKET_KEY = 'niche'


def market_level_for(ddp_per_kg, target_price_per_kg, markets) -> dict:
    """The Destination Market whose from/to range (in %) holds the DDP price as a % of the target price; an empty end of a range is open.
    -> {level, key, share, configured, cargoCapKg} — `level` / `key` are None when no category matches / none is set."""
    if ddp_per_kg is None or not target_price_per_kg:
        return {'level': None, 'key': None, 'share': None, 'configured': False, 'cargoCapKg': None}
    share = (ddp_per_kg / target_price_per_kg) * 100
    configured = [market for market in (markets or []) if market.get('min') is not None or market.get('max') is not None]
    match = next((market for market in configured
                  if share >= (market['min'] if market.get('min') is not None else -math.inf) and share <= (market['max'] if market.get('max') is not None else math.inf)), None)
    return {'level': match.get('label') if match else None, 'key': match.get('key') if match else None, 'share': share, 'configured': len(configured) > 0,
            'cargoCapKg': match.get('cargo_cap_kg') if match else None}


def suggested_sell_price(market_key, ddp_per_kg, target_price_per_kg, markets) -> dict:
    """Suggested sell price per kg by market level (Destination Market `sell_pct`): wholesalers -> sell_pct % of the target price; niche / premium -> the DDP price plus
    sell_pct % profit. Whatever the rule gives, never below the DDP price (the product's cost): such a product sells at cost, not at a loss.
    -> {value, note} — value is None when what the rule needs is missing."""
    market = next((item for item in (markets or []) if item.get('key') == market_key), None)
    if not market:
        return {'value': None, 'note': ''}
    if market.get('sell_pct') is None:
        return {'value': None, 'note': f"Set the sell price % of {market.get('label')} in Settings ▸ Market Opportunity settings ▸ Destination Market."}
    if market_key == 'wholesalers':
        if not target_price_per_kg:
            return {'value': None, 'note': 'Needs the target price'}
        value, note = (target_price_per_kg * market['sell_pct']) / 100, f"{_num(market['sell_pct'])}% of the target price"
    else:
        if ddp_per_kg is None:
            return {'value': None, 'note': 'Needs the DDP price'}
        value, note = ddp_per_kg * (1 + market['sell_pct'] / 100), f"DDP price + {_num(market['sell_pct'])}% profit"
    if ddp_per_kg is not None and value < ddp_per_kg:
        return {'value': ddp_per_kg, 'note': f'{note} is below the cost (DDP price), so it sells at cost'}
    return {'value': value, 'note': note}


def _num(value) -> str:
    """A number as JavaScript writes it in a template string: 60.0 -> '60', 12.5 -> '12.5'."""
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
