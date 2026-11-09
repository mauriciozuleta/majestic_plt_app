"""Unit normalization: everything is converted to USD per US gallon. The original value and unit are kept by the caller; nothing is converted silently."""

from . import config as c

UNITS = ('usd_gal', 'usd_bbl', 'cts_gal', 'usd_mt', 'usd_litre', 'local_per_litre', 'local_per_gal')


class UnitError(ValueError):
    pass


def to_usd_per_gal(value: float, unit: str, *, fx_to_usd: float | None = None, bbl_per_mt: float | None = None) -> float:
    """`fx_to_usd` (USD per 1 unit of local currency) is required, and only used, for the local_* units — a missing rate is an error, never a guess."""
    unit = (unit or '').strip().lower()
    value = float(value)
    if unit == 'usd_gal':
        return value
    if unit == 'usd_bbl':
        return value / c.GALLONS_PER_BARREL
    if unit == 'cts_gal':
        return value / 100.0
    if unit == 'usd_mt':
        factor = bbl_per_mt if bbl_per_mt is not None else c.BBL_PER_METRIC_TON
        return value / factor / c.GALLONS_PER_BARREL
    if unit == 'usd_litre':
        return value * c.LITRES_PER_US_GALLON
    if unit in ('local_per_litre', 'local_per_gal'):
        if not fx_to_usd or fx_to_usd <= 0:
            raise UnitError(f'{unit} needs an explicit fx_to_usd rate')
        per_gal = value * (c.LITRES_PER_US_GALLON if unit == 'local_per_litre' else 1.0)
        return per_gal * fx_to_usd
    raise UnitError(f'unknown unit {unit!r}')
