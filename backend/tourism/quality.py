"""Validation of observations and their data-quality label.

"Verified" means the observation passed the checks below (valid country code, plausible value and unit, no duplicate), NOT that the provider's
estimate was independently proven correct.
"""

from datetime import datetime, timezone

from . import constants as c


def validate(indicator_code: str, value, unit: str, year: int, *, iso_known: bool = True, is_calculated: bool = False, is_estimated: bool = False, today_year: int | None = None) -> tuple[str, list[str]]:
    """(status, problems). Status is one of Verified / Calculated / Estimated / Historical / Missing / Requires Review."""
    today_year = today_year or datetime.now(timezone.utc).year
    problems: list[str] = []
    indicator = c.INDICATORS.get(indicator_code)
    if indicator is None:
        return c.REQUIRES_REVIEW, [f'Unknown indicator {indicator_code}.']
    if value is None:
        return c.MISSING, ['No value.']
    if not iso_known:
        problems.append('The country code is not in the registry.')
    if unit != indicator.unit:
        problems.append(f'Unit "{unit}" differs from the expected "{indicator.unit}" (possible unit-conversion error).')
    if not isinstance(year, int) or year < 1900 or year > today_year + 1:
        problems.append(f'Implausible reference year {year}.')
    if indicator_code == c.POPULATION and value <= 0:
        problems.append('Population must be positive.')
    if indicator_code in (c.TOURISM_GDP_TOTAL, c.TOURISM_GDP_DIRECT, c.TOURISM_EMPLOYMENT) and not 0 <= value <= 100:
        problems.append('A share must be between 0 and 100 percent (a fraction such as 0.12 would be a unit error).')
    if indicator_code in (c.TOURISM_RECEIPTS, c.GDP_USD) and value < 0:
        problems.append('Receipts and GDP cannot be negative.')
    if indicator_code == c.GDP_USD and value == 0:
        problems.append('GDP of zero cannot be a denominator.')
    if indicator_code == c.TOURISM_DEPENDENCY and value < 0:
        problems.append('Dependency cannot be negative.')
    if problems:
        return c.REQUIRES_REVIEW, problems
    if is_calculated:
        return c.CALCULATED_STATUS, []
    if is_estimated:
        return c.ESTIMATED, []
    if year < today_year - c.HISTORICAL_AFTER_YEARS:
        return c.HISTORICAL, [f'Older than {c.HISTORICAL_AFTER_YEARS} years.']
    return c.VERIFIED, []
