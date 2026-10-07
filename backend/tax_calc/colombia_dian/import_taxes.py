"""The Colombian import taxes of a shipment, from the Gravamen and IVA DIAN publishes. A PURE function: no network, no state.

Money is Decimal throughout; nothing is rounded until the very end (ROUND_HALF_UP to `decimals`, default 2 — one documented rule), so the
intermediate values the UI shows are exact and the amounts add up.
"""

from decimal import ROUND_HALF_UP, Decimal

IVA_NOT_LISTED_NOTE = 'No IVA listed by DIAN; calculated as 0. Verify the product’s IVA treatment.'
IVA_BASE_ASSUMPTION = (
    'IVA base = customs value + Gravamen (the usual rule for imports). Verify with a customs broker or DIAN before relying on it.'
)


def iva_base_for_imports(customs_value: Decimal, gravamen_amount: Decimal) -> Decimal:
    """THE place where the IVA base is decided. On imports into Colombia the IVA is normally charged on the customs value plus the
    Gravamen (the customs duty). This has not been verified against DIAN's rules here — if it turns out to differ for some goods (e.g.
    additional charges that also form part of the base), change it in this one function; everything else follows."""
    return customs_value + gravamen_amount


def _money(value: Decimal, decimals: int) -> float:
    return float(value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


def _percent_rate(tax: dict | None) -> Decimal | None:
    """The rate as a Decimal when the tax is a plain percentage, else None."""
    if not tax or tax.get('unit') != 'percent' or tax.get('rate') is None:
        return None
    return Decimal(str(tax['rate']))


def _validity(tax: dict | None) -> dict | None:
    if not tax:
        return None
    return {'validFrom': tax.get('validFrom'), 'validTo': tax.get('validTo')}


def calculate_import_taxes(customs_value, gravamen: dict | None, iva: dict | None, iva_status: str = 'listed', decimals: int = 2) -> dict:
    """-> { status, ... }.

    status:
      'ok'                  both taxes computed (an IVA of 0 % counts, and so does 'not_listed': 0 with a note)
      'unsupported_formula' a tax is not a plain percentage (specific, per kg, mixed, formula): that tax is NOT computed and its `formulaRaw` is returned
      'not_calculable'      there is no Gravamen to work from (gravamen is None)

    Every intermediate figure comes back (base, rates, amounts, total) with the validity dates of the rates used, so the UI can show its work.
    """
    value = Decimal(str(customs_value))
    if value < 0:
        raise ValueError('customs value cannot be negative')
    notes: list[str] = []
    warnings: list[str] = []
    out: dict = {
        'status': 'ok',
        'customsValue': _money(value, decimals),
        'gravamen': {'rate': None, 'amount': None, 'formulaRaw': (gravamen or {}).get('formulaRaw'), **(_validity(gravamen) or {})},
        'iva': {'rate': None, 'base': None, 'amount': None, 'formulaRaw': (iva or {}).get('formulaRaw'), **(_validity(iva) or {})},
        'totalTaxes': None,
        'totalWithTaxes': None,
        'notes': notes,
        'warnings': warnings,
    }

    if gravamen is None:
        out['status'] = 'not_calculable'
        warnings.append('No Gravamen available for this product, so the taxes cannot be calculated.')
        return out

    gravamen_rate = _percent_rate(gravamen)
    if gravamen_rate is None:
        out['status'] = 'unsupported_formula'
        warnings.append(f'The Gravamen is not a plain percentage ("{gravamen.get("formulaRaw")}"): it is not computed.')
        return out
    gravamen_amount = value * gravamen_rate / 100
    out['gravamen'].update({'rate': float(gravamen_rate), 'amount': _money(gravamen_amount, decimals)})

    if iva_status == 'not_listed':
        iva_amount = Decimal(0)
        out['iva'].update({'rate': 0.0, 'base': None, 'amount': 0.0})
        notes.append(IVA_NOT_LISTED_NOTE)
    else:
        iva_rate = _percent_rate(iva)
        if iva_rate is None:
            out['status'] = 'unsupported_formula'
            warnings.append(f'The IVA is not a plain percentage ("{(iva or {}).get("formulaRaw")}"): it is not computed.')
            return out
        base = iva_base_for_imports(value, gravamen_amount)
        iva_amount = base * iva_rate / 100
        out['iva'].update({'rate': float(iva_rate), 'base': _money(base, decimals), 'amount': _money(iva_amount, decimals)})
        notes.append(IVA_BASE_ASSUMPTION)
        if (iva or {}).get('classification'):
            tag = 'EXCLUIDO' if iva['classification'] == 'excluded' else 'EXENTO'
            notes.append(f'DIAN lists this IVA as {tag} (0 %). Excluded and exempt goods are treated differently in Colombian law; DIAN’s wording is kept as shown.')

    total = gravamen_amount + iva_amount
    out['totalTaxes'] = _money(total, decimals)
    out['totalWithTaxes'] = _money(value + total, decimals)
    return out
