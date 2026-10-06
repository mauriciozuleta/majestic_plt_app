"""Import-tax calculators, one per country (see base.py). Register a new country's adapter here."""

from .base import Calculator, Inputs
from .jamaica import JamaicaCalculator
from .usa import UsaCalculator

CALCULATORS: dict[str, Calculator] = {calculator.name: calculator for calculator in (JamaicaCalculator(), UsaCalculator())}


def get(country: str) -> Calculator | None:
    wanted = (country or '').strip().lower()
    return next((calculator for name, calculator in CALCULATORS.items() if name.lower() == wanted), None)


__all__ = ['CALCULATORS', 'Calculator', 'Inputs', 'get']
