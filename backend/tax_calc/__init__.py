"""Import-tax calculators, one per country (see base.py). Register a new country's adapter here."""

from .bahamas import BahamasCalculator
from .barbados import BarbadosCalculator
from .base import Calculator, Inputs
from .grenada import GrenadaCalculator
from .jamaica import JamaicaCalculator
from .trinidad import TrinidadCalculator
from .saint_lucia import SaintLuciaCalculator
from .sint_maarten import SintMaartenCalculator
from .turks_caicos import TurksCaicosCalculator
from .usa import UsaCalculator

CALCULATORS: dict[str, Calculator] = {calculator.name: calculator for calculator in (JamaicaCalculator(), UsaCalculator(), TrinidadCalculator(), BahamasCalculator(), SaintLuciaCalculator(), GrenadaCalculator(), BarbadosCalculator(), TurksCaicosCalculator(), SintMaartenCalculator())}


def get(country: str) -> Calculator | None:
    wanted = (country or '').strip().lower()
    return next((calculator for name, calculator in CALCULATORS.items() if name.lower() == wanted), None)


__all__ = ['CALCULATORS', 'Calculator', 'Inputs', 'get']
