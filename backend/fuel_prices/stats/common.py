"""Shared helpers of the statistics layer. Series are plain lists of (date, value) sorted by date, so every function is testable on synthetic data."""

import math
from collections import defaultdict
from datetime import date, timedelta

Points = list[tuple[date, float]]


class Refused(Exception):
    """The data are too thin (or missing) for an honest number; the message says why and is returned to the UI instead of a statistic."""


def need(points, minimum: int, what: str):
    if len(points) < minimum:
        raise Refused(f'{what} needs at least {minimum} observations; only {len(points)} available.')


def sort_points(points: Points) -> Points:
    return sorted(points, key=lambda p: p[0])


def window(points: Points, start: date | None = None, end: date | None = None) -> Points:
    return [p for p in points if (start is None or p[0] >= start) and (end is None or p[0] <= end)]


def weekly(points: Points) -> Points:
    """Last observation of each ISO week, dated to that week's Monday."""
    last: dict[date, tuple[date, float]] = {}
    for d, v in sort_points(points):
        monday = d - timedelta(days=d.weekday())
        last[monday] = (d, v)
    return [(k, v[1]) for k, v in sorted(last.items())]


def monthly(points: Points) -> Points:
    """Mean of each calendar month, dated to the 1st."""
    acc: dict[date, list[float]] = defaultdict(list)
    for d, v in points:
        acc[d.replace(day=1)].append(v)
    return [(k, sum(v) / len(v)) for k, v in sorted(acc.items())]


def align(a: Points, b: Points) -> tuple[list[date], list[float], list[float]]:
    bm = dict(b)
    dates = [d for d, _ in sort_points(a) if d in bm]
    am = dict(a)
    return dates, [am[d] for d in dates], [bm[d] for d in dates]


def log_returns(points: Points) -> Points:
    out = []
    for (_, v0), (d1, v1) in zip(points, points[1:]):
        if v0 > 0 and v1 > 0:
            out.append((d1, math.log(v1 / v0)))
    return out


def diffs(points: Points) -> Points:
    return [(d1, v1 - v0) for (_, v0), (d1, v1) in zip(points, points[1:])]


def mean(xs):
    return sum(xs) / len(xs)


def std(xs):
    if len(xs) < 2:
        return 0.0
    mu = mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def corr(x, y):
    if len(x) < 3:
        return None
    sx, sy = std(x), std(y)
    if sx == 0 or sy == 0:
        return None
    mx, my = mean(x), mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / ((len(x) - 1) * sx * sy)


def ols(x, y) -> dict:
    n = len(x)
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        raise Refused('the explanatory series does not vary in this window.')
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    intercept = my - slope * mx
    resid = [b - (intercept + slope * a) for a, b in zip(x, y)]
    ss_res = sum(r * r for r in resid)
    ss_tot = sum((b - my) ** 2 for b in y)
    se = math.sqrt(ss_res / (n - 2) / sxx) if n > 2 else None
    return {'slope': slope, 'intercept': intercept, 'r2': 1 - ss_res / ss_tot if ss_tot else None, 'slope_se': se, 'n': n}


def meta(points: Points, quality_mix: dict | None = None) -> dict:
    """Sample size, date range and data-quality mix — attached to every statistic."""
    return {'n': len(points), 'from': points[0][0].isoformat() if points else None, 'to': points[-1][0].isoformat() if points else None, 'quality_mix': quality_mix or {}}
