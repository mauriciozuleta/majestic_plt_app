"""SAM Overview's opt-in estimation layer — per-category regression of
Comtrade import totals against population and GDP-per-capita, using plain
numpy least-squares (no ML dependency added; requirements.txt already
pins numpy==2.5.3). See MARKET_SIZING_METHODOLOGY.md for the full plain-
language walkthrough of what this produces and why, and routers/comtrade.py's
sam_overview_estimates for how this module is actually called: it only ever
sees a category's CONFIRMED (true Comtrade, non-bilateral) countries as
training data, and only ever predicts for a country that has no existing
row at all for that category — this module has no opinion on that
selection, it just fits and predicts what it's handed.

Guardrails (both non-negotiable thresholds — do not tune without updating
MARKET_SIZING_METHODOLOGY.md to match):
- MIN_SAMPLE_SIZE: fewer confirmed countries than this and fit_category_model
  refuses to fit at all (returns None) — 2 predictors (population, GDP per
  capita) need enough rows to mean anything.
- LOW_CONFIDENCE_R2_THRESHOLD: a fitted model below this R² is still
  returned (and can still be used, if the user opts in), but flagged
  `low_confidence` so every estimate it produces can be shown with a
  visually distinct treatment rather than the same confidence as a
  well-fitting model's estimates."""

import numpy as np

MIN_SAMPLE_SIZE = 5
LOW_CONFIDENCE_R2_THRESHOLD = 0.5


def _r_squared(y_actual, y_predicted) -> float:
    y_actual = np.asarray(y_actual, dtype=float)
    y_predicted = np.asarray(y_predicted, dtype=float)
    ss_res = np.sum((y_actual - y_predicted) ** 2)
    ss_tot = np.sum((y_actual - np.mean(y_actual)) ** 2)
    if ss_tot == 0:
        # Every training value identical — no variance for a model to
        # explain. Treated as "explains none of it" rather than dividing by
        # zero, which reads correctly either way: a constant target isn't a
        # case this regression is meant to handle.
        return 0.0
    return float(1 - ss_res / ss_tot)


def _fit_ols(x_matrix: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ordinary least squares via numpy.linalg.lstsq (x_matrix already
    carries its own intercept column of 1s as its first column). Returns
    (coefficients, fitted_y)."""
    coefficients, *_ = np.linalg.lstsq(x_matrix, y, rcond=None)
    fitted = x_matrix @ coefficients
    return coefficients, fitted


def fit_category_model(training_rows: list[dict]) -> dict | None:
    """training_rows: [{'population': float, 'gdp_per_capita': float,
    'value': float}, ...] — one row per country with CONFIRMED data for this
    category (the caller has already applied that filter; see module
    docstring). Returns None if fewer than MIN_SAMPLE_SIZE rows — the caller
    is expected to report the "not enough confirmed data points" guardrail
    message instead of calling this at all in that case.

    Otherwise fits BOTH forms —
      linear:   value        ~ 1 + population        + gdp_per_capita
      log-log:  log(value)   ~ 1 + log(population)    + log(gdp_per_capita)
    — compares R² on each form's own scale, and keeps whichever fits
    better. Log-log is skipped (linear wins by default) if any training row
    has a non-positive value/population/gdp-per-capita, since log() of a
    non-positive number isn't defined — real Comtrade import totals and
    real population/GDP-per-capita figures are always positive in practice,
    so this only matters for a pathological input.

    Returns {'method': 'linear'|'log-log', 'coefficients': [intercept,
    population_coef, gdp_per_capita_coef], 'r_squared': float,
    'low_confidence': bool, 'sample_size': int} — see predict() below for
    how `coefficients`/`method` are applied to one country's real inputs."""
    n = len(training_rows)
    if n < MIN_SAMPLE_SIZE:
        return None

    population = np.array([row['population'] for row in training_rows], dtype=float)
    gdp = np.array([row['gdp_per_capita'] for row in training_rows], dtype=float)
    value = np.array([row['value'] for row in training_rows], dtype=float)

    x_linear = np.column_stack([np.ones(n), population, gdp])
    coef_linear, fitted_linear = _fit_ols(x_linear, value)
    r2_linear = _r_squared(value, fitted_linear)

    log_log = None
    if np.all(value > 0) and np.all(population > 0) and np.all(gdp > 0):
        log_value = np.log(value)
        x_log = np.column_stack([np.ones(n), np.log(population), np.log(gdp)])
        coef_log, fitted_log = _fit_ols(x_log, log_value)
        log_log = {'coefficients': coef_log, 'r_squared': _r_squared(log_value, fitted_log)}

    if log_log is not None and log_log['r_squared'] > r2_linear:
        method, coefficients, r_squared = 'log-log', log_log['coefficients'], log_log['r_squared']
    else:
        method, coefficients, r_squared = 'linear', coef_linear, r2_linear

    return {
        'method': method,
        'coefficients': [float(c) for c in coefficients],
        'r_squared': r_squared,
        'low_confidence': r_squared < LOW_CONFIDENCE_R2_THRESHOLD,
        'sample_size': n,
    }


def predict(model: dict, population: float, gdp_per_capita: float) -> float:
    """Applies a fitted model (see fit_category_model) to one real
    country's real population/GDP-per-capita, returning a predicted import
    value in the same USD units as every other TAM figure. Clamped at 0 —
    a log-log model can never produce a negative value by construction
    (it's exp() of something), but a linear model's fitted plane can dip
    below zero for an input near the edge of (or outside) its training
    range; shown as $0 rather than a nonsensical negative market size."""
    intercept, population_coef, gdp_coef = model['coefficients']
    if model['method'] == 'log-log':
        predicted = np.exp(intercept + population_coef * np.log(population) + gdp_coef * np.log(gdp_per_capita))
    else:
        predicted = intercept + population_coef * population + gdp_coef * gdp_per_capita
    return max(0.0, float(predicted))
