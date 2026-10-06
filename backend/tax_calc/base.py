"""Shared pieces of the per-country import-tax calculators.

Every country has an adapter with the same interface (`Calculator`): find a tariff line by name or code, and compute the
taxes of an import from the line's published rates. All arithmetic is plain code — no model is involved — and every result
carries the formula behind each figure plus the assumptions and anything it could NOT compute, so a number is never shown
with more confidence than it deserves.

Adding a country = a new adapter module + its tariff data under backend/documents/tax_data/<Country>/, registered in
tax_calc/__init__.py.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent.parent / 'documents' / 'tax_data'


@dataclass
class Inputs:
    """What the user is importing. Money is in USD; the adapters convert nothing."""

    goods_value_usd: float  # price paid for the goods (transaction value, before freight and insurance)
    quantity_kg: float | None = None
    quantity_units: float | None = None  # in the tariff line's own unit (doz, liter, no. …) when its duty is per unit
    freight_usd: float = 0.0  # international freight to the destination
    insurance_usd: float = 0.0
    origin: str | None = None  # country the goods come from
    transport: str = 'air'  # 'air' | 'sea' (some fees depend on it)
    commercial_importer: bool = False  # a registered commercial importer (some advance payments depend on it)


@dataclass
class Tax:
    name: str
    amount: float  # USD
    rate: str  # the published rate, as written ("40%", "3.9¢/kg")
    basis: str  # what it is charged on, in words
    formula: str  # the arithmetic, in numbers
    recoverable: bool = False  # an advance payment that is credited later — shown, not counted in the total
    note: str = ''


@dataclass
class Result:
    country: str
    line: dict
    inputs: dict
    value_basis: dict
    taxes: list[Tax] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # assumptions made
    warnings: list[str] = field(default_factory=list)  # things not computed or to verify
    sources: list[str] = field(default_factory=list)
    complete: bool = True  # False when a charge on this line couldn't be computed (the total is then a minimum)

    def to_dict(self) -> dict:
        counted = [tax for tax in self.taxes if not tax.recoverable]
        total = sum(tax.amount for tax in counted)
        goods = self.inputs['goods_value_usd']
        kg = self.inputs.get('quantity_kg')
        return {
            'country': self.country,
            'line': self.line,
            'inputs': self.inputs,
            'value_basis': self.value_basis,
            'taxes': [tax.__dict__ for tax in self.taxes],
            'total_tax_usd': round(total, 2),
            'total_per_kg_usd': round(total / kg, 4) if kg else None,
            'total_pct_of_goods': round(total / goods * 100, 2) if goods else None,
            'landed_cost_usd': round(goods + self.inputs.get('freight_usd', 0) + self.inputs.get('insurance_usd', 0) + total, 2),
            'complete': self.complete,
            'notes': self.notes,
            'warnings': self.warnings,
            'sources': self.sources,
        }


class Calculator:
    """Interface of a country adapter."""

    name: str = ''
    currency: str = 'USD'

    def info(self) -> dict:  # data source, size, date, whether it is loaded
        raise NotImplementedError

    def refresh(self) -> dict:  # (re)load the tariff data from its source
        raise NotImplementedError

    def search(self, query: str, limit: int = 30) -> list[dict]:
        raise NotImplementedError

    def get(self, code: str) -> dict | None:
        raise NotImplementedError

    def calculate(self, code: str, inputs: Inputs) -> Result:
        raise NotImplementedError


# ---------------------------------------------------------------- helpers shared by the adapters

STOP_WORDS = {'the', 'and', 'for', 'with', 'from', 'other', 'fresh', 'chilled', 'of', 'in', 'or'}


def stem(word: str) -> str:
    word = word.lower()
    for ending in ('ies', 'oes', 'es', 's'):
        if word.endswith(ending) and len(word) > len(ending) + 2:
            return word[: -len(ending)] + {'ies': 'y', 'oes': 'o'}.get(ending, '')
    return word


def query_words(query: str) -> list[str]:
    return [stem(word) for word in re.findall(r'[A-Za-z]{2,}', query) if word.lower() not in STOP_WORDS]


def rank(line: dict, words: list[str]) -> tuple | None:
    """Sort key of a tariff line for a search, or None if it doesn't match: every word must appear somewhere in the line's
    path (its headings and its own description). A word in the top heading ("Tomatoes, fresh or chilled") counts most, then
    one in the line's own description; shorter paths first."""
    path = line['path'].lower()
    if not all(word in path for word in words):
        return None
    top = path.split(' > ')[0]
    own = line['description'].lower()
    score = 2 * sum(word in top for word in words) + sum(word in own for word in words)
    return (-score, len(path))


def digits(text: str) -> str:
    return re.sub(r'\D', '', text or '')


def money(value: float) -> str:
    return f'{value:,.2f}'
