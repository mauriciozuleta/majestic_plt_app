"""Decimal-safe tourism dependency calculation: international tourism receipts / GDP x 100, same country, same year, both current US$."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PLACES = Decimal('0.0001')


def to_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        number = Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def tourism_dependency(receipts_usd, gdp_usd) -> Decimal | None:
    """Receipts / GDP x 100, rounded to 4 decimals. None when either value is missing, GDP is not positive or receipts are negative.
    The caller must pass observations of the SAME country and year — this function cannot check that."""
    receipts, gdp = to_decimal(receipts_usd), to_decimal(gdp_usd)
    if receipts is None or gdp is None or gdp <= 0 or receipts < 0:
        return None
    return (receipts / gdp * Decimal(100)).quantize(PLACES, rounding=ROUND_HALF_UP)
