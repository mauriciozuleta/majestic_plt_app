"""Descriptive statistics, volatility and seasonality of one price series."""

import math
from datetime import date, timedelta

from .. import config as c
from .common import Points, Refused, log_returns, mean, meta, monthly, need, sort_points, std, weekly, window


def percentile(sorted_values: list[float], q: float) -> float:
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def descriptive(points: Points, window_days: int | None = None, quality_mix=None) -> dict:
    points = sort_points(points)
    if window_days and points:
        points = window(points, points[-1][0] - timedelta(days=window_days))
    need(points, c.MIN_POINTS['descriptive'], 'descriptive statistics')
    values = sorted(v for _, v in points)
    low = min(points, key=lambda p: p[1])
    high = max(points, key=lambda p: p[1])
    return {**meta(points, quality_mix), 'window_days': window_days, 'mean': mean(values), 'median': percentile(values, 0.5), 'std': std(values),
            'percentiles': {str(int(q * 100)): percentile(values, q) for q in (0.05, 0.25, 0.75, 0.95)},
            'min': {'value': low[1], 'date': low[0].isoformat()}, 'max': {'value': high[1], 'date': high[0].isoformat()}, 'last': {'value': points[-1][1], 'date': points[-1][0].isoformat()}}


def volatility(points: Points, event_dates: list[date] | None = None, shock_weeks: int = 8, roll_weeks: int = 13, quality_mix=None) -> dict:
    wk = weekly(points)
    rets = log_returns(wk)
    need(rets, c.MIN_POINTS['volatility'], 'volatility (weekly log-returns)')
    values = [r for _, r in rets]
    rolling = [{'date': rets[i][0].isoformat(), 'vol': std(values[i - roll_weeks + 1:i + 1])} for i in range(roll_weeks - 1, len(rets))]
    shock, calm = [], []
    for d, r in rets:
        in_shock = any(timedelta(0) <= d - e <= timedelta(weeks=shock_weeks) for e in (event_dates or []))
        (shock if in_shock else calm).append(r)
    out = {**meta(wk, quality_mix), 'weekly_vol': std(values), 'annualized_vol': std(values) * math.sqrt(52), 'rolling_weeks': roll_weeks, 'rolling': rolling,
           'shock_window_weeks': shock_weeks, 'calm': {'n': len(calm), 'weekly_vol': std(calm) if len(calm) >= 5 else None},
           'shock': {'n': len(shock), 'weekly_vol': std(shock) if len(shock) >= 5 else None}}
    if not event_dates:
        out['note'] = 'No events recorded, so calm vs shock cannot be compared.'
    elif len(shock) < 5:
        out['note'] = f'Fewer than 5 weekly returns fall in the {shock_weeks} weeks after an event; shock volatility not computed.'
    return out


def seasonality(points: Points, quality_mix=None) -> dict:
    """Month-of-year effect = mean over years of (log of the month's average price - log of that year's average), in percent, with a 95% normal-approximation interval."""
    mo = monthly(points)
    need(mo, c.MIN_POINTS['seasonality'], 'seasonality (months of data)')
    by_year: dict[int, list[tuple[int, float]]] = {}
    for d, v in mo:
        by_year.setdefault(d.year, []).append((d.month, math.log(v)))
    effects: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for year, items in by_year.items():
        if len(items) < 12:
            continue  # only complete years, so the annual mean is not biased by which months exist
        ym = mean([x for _, x in items])
        for month, x in items:
            effects[month].append((x - ym) * 100)
    years = len([1 for items in by_year.values() if len(items) == 12])
    out = []
    for month in range(1, 13):
        xs = effects[month]
        sd = std(xs) if len(xs) > 1 else None
        half = 1.96 * sd / math.sqrt(len(xs)) if sd is not None and len(xs) > 2 else None
        out.append({'month': month, 'effect_pct': mean(xs) if xs else None, 'n_years': len(xs), 'ci95_pct': half})
    if years < 2:
        raise Refused('seasonality needs at least 2 complete calendar years.')
    result = {**meta(mo, quality_mix), 'complete_years': years, 'months': out}
    if years < 5:
        result['warning'] = f'Only {years} complete years of data: the month effects are not reliable (intervals are wide or missing).'
    return result
