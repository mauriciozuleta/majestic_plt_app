"""Relationships between series: crude/crack decomposition, regression on Brent, lagged correlations, crack-spread mean reversion, pass-through, retail premium and event windows.

Crack spread here = jet price - Brent, both in USD per US gallon (a simple "jet over crude" spread, not a refinery margin model)."""

import math
from datetime import date, timedelta

from .. import config as c
from .common import Points, Refused, align, corr, diffs, log_returns, mean, meta, monthly, need, ols, sort_points, std, weekly, window

LAGS_WEEKS = list(range(-4, 9))  # negative = jet leads Brent
LAGS_MONTHS = list(range(0, 7))


def crack(jet: Points, brent: Points) -> Points:
    dates, j, b = align(jet, brent)
    return [(d, x - y) for d, x, y in zip(dates, j, b)]


def decomposition(jet: Points, brent: Points, start: date | None = None, end: date | None = None, quality_mix=None) -> dict:
    """jet = Brent + crack. Change over the window split into the crude part and the crack-spread part (they add up exactly)."""
    dates, j, b = align(window(jet, start, end), window(brent, start, end))
    need(dates, 2, 'price decomposition (days with both jet and Brent)')
    cr = [x - y for x, y in zip(j, b)]
    d_jet, d_brent, d_crack = j[-1] - j[0], b[-1] - b[0], cr[-1] - cr[0]
    share = (lambda part: part / d_jet) if abs(d_jet) > 1e-9 else (lambda part: None)
    return {**meta(list(zip(dates, j)), quality_mix), 'start': {'date': dates[0].isoformat(), 'jet': j[0], 'brent': b[0], 'crack': cr[0]},
            'end': {'date': dates[-1].isoformat(), 'jet': j[-1], 'brent': b[-1], 'crack': cr[-1]},
            'delta': {'jet': d_jet, 'crude': d_brent, 'crack': d_crack}, 'share_of_change': {'crude': share(d_brent), 'crack': share(d_crack)},
            'window_mean': {'jet': mean(j), 'brent': mean(b), 'crack': mean(cr)},
            'series': [{'date': d.isoformat(), 'jet': x, 'brent': y, 'crack': z} for d, x, y, z in zip(dates, j, b, cr)],
            'note': 'Basis, into-plane fees and taxes are not separated: no series for them is loaded.'}


def regression(jet: Points, brent: Points, quality_mix=None) -> dict:
    """Jet on Brent, in levels (weekly, last obs of the week) and in weekly changes. Levels of trending prices correlate spuriously; the change regression is the sturdier read."""
    wj, wb = weekly(jet), weekly(brent)
    dates, j, b = align(wj, wb)
    need(dates, c.MIN_POINTS['regression'], 'regression of jet on Brent (weeks with both)')
    levels = ols(b, j)
    jd = [v for _, v in diffs(list(zip(dates, j)))]
    bd = [v for _, v in diffs(list(zip(dates, b)))]
    return {**meta(list(zip(dates, j)), quality_mix), 'levels': levels, 'changes': ols(bd, jd), 'unit': 'USD/gal both sides',
            'note': 'A slope of 1 in levels means one extra dollar of Brent per gallon passes straight into jet.'}


def lagged_correlations(jet: Points, brent: Points, quality_mix=None) -> dict:
    """corr(weekly log-return of jet at t, weekly log-return of Brent at t-k). k>0: Brent leads. Lags tested: -4..8 weeks."""
    wj, wb = log_returns(weekly(jet)), log_returns(weekly(brent))
    dates, j, b = align(wj, wb)
    need(dates, c.MIN_POINTS['lag'], 'lagged correlation (weeks with both returns)')
    jm, bm = dict(zip(dates, j)), dict(zip(dates, b))
    step = timedelta(weeks=1)
    rows = []
    for k in LAGS_WEEKS:
        xs, ys = [], []
        for d in dates:
            other = d - k * step
            if other in bm:
                xs.append(jm[d])
                ys.append(bm[other])
        r = corr(xs, ys) if len(xs) >= 20 else None
        rows.append({'lag_weeks': k, 'corr': r, 'n': len(xs)})
    valid = [r for r in rows if r['corr'] is not None]
    return {**meta(list(zip(dates, j)), quality_mix), 'lags_tested_weeks': LAGS_WEEKS, 'rows': rows, 'best': max(valid, key=lambda r: abs(r['corr'])) if valid else None}


def driver_relationship(crack_pts: Points, driver: Points | None, driver_name: str, quality_mix=None) -> dict:
    """Crack spread vs an inventory / refinery-output driver, weekly levels, lags 0..8 weeks (driver leads). Refuses when the driver series is not loaded."""
    if not driver:
        raise Refused(f'No {driver_name} series is loaded (EIA stock/refinery series are not wired: they need the EIA API and confirmed series IDs).')
    wc, wd = weekly(crack_pts), weekly(driver)
    dates, cs, ds = align(wc, wd)
    need(dates, c.MIN_POINTS['lag'], f'crack vs {driver_name}')
    cm, dm = dict(zip(dates, cs)), dict(zip(dates, ds))
    rows = []
    for k in range(0, 9):
        xs = [cm[d] for d in dates if d - timedelta(weeks=k) in dm]
        ys = [dm[d - timedelta(weeks=k)] for d in dates if d - timedelta(weeks=k) in dm]
        rows.append({'lag_weeks': k, 'corr': corr(xs, ys) if len(xs) >= 20 else None, 'n': len(xs)})
    return {**meta(list(zip(dates, cs)), quality_mix), 'driver': driver_name, 'rows': rows, 'lags_tested_weeks': list(range(0, 9))}


def half_life(crack_pts: Points, quality_mix=None) -> dict:
    """AR(1) on the weekly crack spread: x_t = a + phi x_{t-1}. Half-life = ln(0.5)/ln(phi) weeks when 0 < phi < 1 (how fast a spike decays back toward its mean)."""
    wk = weekly(crack_pts)
    need(wk, c.MIN_POINTS['half_life'], 'mean reversion of the crack spread (weeks)')
    x = [v for _, v in wk]
    fit = ols(x[:-1], x[1:])
    phi = fit['slope']
    out = {**meta(wk, quality_mix), 'phi': phi, 'phi_se': fit['slope_se'], 'long_run_mean': fit['intercept'] / (1 - phi) if phi < 1 else None}
    if 0 < phi < 1:
        out['half_life_weeks'] = math.log(0.5) / math.log(phi)
    else:
        out['half_life_weeks'] = None
        out['note'] = 'phi >= 1 or <= 0: no mean reversion detected in this window (or too noisy to say).'
    return out


def pass_through(spot: Points, paid: Points, quality_mix=None) -> dict:
    """Spot -> airline-paid: correlation of monthly changes at lags 0..6 months (spot leads), and the slope at the best lag."""
    sm, pm = monthly(spot), monthly(paid)
    need(pm, c.MIN_POINTS['passthrough'], 'pass-through (months of airline-paid prices)')
    sd, pd_ = dict(diffs(sm)), diffs(pm)
    rows, best_pairs = [], {}
    for k in LAGS_MONTHS:
        xs, ys = [], []
        for d, v in pd_:
            y, mth = d.year, d.month - k
            while mth < 1:
                y, mth = y - 1, mth + 12
            key = date(y, mth, 1)
            if key in sd:
                xs.append(sd[key])
                ys.append(v)
        rows.append({'lag_months': k, 'corr': corr(xs, ys) if len(xs) >= 12 else None, 'n': len(xs)})
        best_pairs[k] = (xs, ys)
    valid = [r for r in rows if r['corr'] is not None]
    if not valid:
        raise Refused('fewer than 12 overlapping months between spot and airline-paid prices.')
    best = max(valid, key=lambda r: abs(r['corr']))
    xs, ys = best_pairs[best['lag_months']]
    return {**meta(pm, quality_mix), 'lags_tested_months': LAGS_MONTHS, 'rows': rows, 'best': best, 'slope_at_best': ols(xs, ys)['slope']}


def retail_premium(retail: Points, spot: Points, quality_mix=None) -> dict:
    """Posted retail (FBO) minus spot, on the months where both exist."""
    rm, sm = dict(monthly(retail)), dict(monthly(spot))
    both = sorted(set(rm) & set(sm))
    need(both, c.MIN_POINTS['event'], 'retail premium (months with both retail and spot)')
    prem = [(d, rm[d] - sm[d]) for d in both]
    vals = [v for _, v in prem]
    return {**meta(prem, quality_mix), 'mean': mean(vals), 'median': sorted(vals)[len(vals) // 2], 'std': std(vals), 'series': [{'date': d.isoformat(), 'premium': v} for d, v in prem]}


def event_windows(points: Points, events: list[dict], weeks: int = 4, quality_mix=None) -> dict:
    """Mean price in the N weeks before vs after each event date."""
    pts = sort_points(points)
    out = []
    for ev in events:
        d = date.fromisoformat(ev['date']) if isinstance(ev['date'], str) else ev['date']
        before = [v for t, v in pts if d - timedelta(weeks=weeks) <= t < d]
        after = [v for t, v in pts if d <= t <= d + timedelta(weeks=weeks)]
        row = {'date': d.isoformat(), 'title': ev['title'], 'n_before': len(before), 'n_after': len(after)}
        if len(before) >= c.MIN_POINTS['event'] and len(after) >= c.MIN_POINTS['event']:
            row.update(mean_before=mean(before), mean_after=mean(after), change=mean(after) - mean(before), change_pct=(mean(after) / mean(before) - 1) * 100)
        else:
            row['note'] = f'fewer than {c.MIN_POINTS["event"]} observations on one side of the event'
        out.append(row)
    if not any('change' in r for r in out):
        raise Refused('no event has enough observations on both sides in the loaded data.')
    return {**meta(pts, quality_mix), 'weeks': weeks, 'events': out}
