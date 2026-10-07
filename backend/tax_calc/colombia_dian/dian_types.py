"""The result contract of a DIAN lookup (camelCase JSON, ISO dates, one shape) — see README.md."""

from dataclasses import dataclass, field

SCHEMA_VERSION = 1

ERROR_CODES = (
    'INVALID_HS_CODE',
    'DIAN_UNAVAILABLE',
    'DIAN_TIMEOUT',
    'HS_CODE_NOT_FOUND',
    'PAGE_STRUCTURE_CHANGED',
    'MEASURE_PARSE_FAILED',
    'BROWSER_NOT_INSTALLED',  # Playwright's Chromium isn't installed on this machine (run: playwright install chromium)
)

UNITS = ('percent', 'specific', 'specific_per_kg', 'mixed', 'formula')


@dataclass
class TaxValue:
    """One row of a DIAN measure popup (Gravamen or IVA).

    `rate` is a number (percent) ONLY for a percentage formula; a specific, per-kg, mixed or unrecognised formula keeps `rate = None`,
    sets `unit` and keeps the text in `formulaRaw` — it is never coerced into a percent. `classification` is DIAN's own tag when its
    text carries one ("0 % - EXCLUIDO" -> excluded, "0 % - EXENTO" -> exempt); it is information, not a legal interpretation."""

    rate: float | None
    unit: str | None
    formulaRaw: str
    validFrom: str | None
    validTo: str | None
    rawText: str = ''
    concept: str | None = None  # "GRAVAMEN ARANCELARIO", "ARANCEL VARIABLE" … or, for a conditional IVA, the product it applies to
    classification: str | None = None  # 'excluded' | 'exempt' | None
    hasLegalBasis: bool = False  # the Leg icon is present (its text is not followed)

    def to_dict(self) -> dict:
        data = {
            'rate': self.rate,
            'unit': self.unit,
            'formulaRaw': self.formulaRaw,
            'validFrom': self.validFrom,
            'validTo': self.validTo,
            'rawText': self.rawText,
            'concept': self.concept,
            'hasLegalBasis': self.hasLegalBasis,
        }
        if self.classification:
            data['classification'] = self.classification
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'TaxValue':
        return cls(
            rate=data.get('rate'),
            unit=data.get('unit'),
            formulaRaw=data.get('formulaRaw', ''),
            validFrom=data.get('validFrom'),
            validTo=data.get('validTo'),
            rawText=data.get('rawText', ''),
            concept=data.get('concept'),
            classification=data.get('classification'),
            hasLegalBasis=bool(data.get('hasLegalBasis')),
        )


@dataclass
class LookupError_:
    code: str
    message: str
    diagnostics: dict | None = None

    def to_dict(self) -> dict:
        data = {'code': self.code, 'message': self.message}
        if self.diagnostics:
            data['diagnostics'] = {key: value for key, value in self.diagnostics.items() if value is not None}
        return {'status': 'error', 'error': data}


class DianError(Exception):
    """Raised inside the provider; becomes a `status: 'error'` result."""

    def __init__(self, code: str, message: str, **diagnostics):
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or None

    def to_result(self) -> dict:
        return LookupError_(self.code, self.message, self.diagnostics).to_dict()


@dataclass
class ProgressEvent:
    step: str  # connecting | searching | resolving | gravamen | iva | complete | batch
    message: str
    index: int | None = None  # batch: 1-based position
    total: int | None = None

    def to_dict(self) -> dict:
        return {'step': self.step, 'message': self.message, 'index': self.index, 'total': self.total}


@dataclass
class TaxLookupRequest:
    country: str
    hsCode: str
    date: str | None = None  # ISO; DIAN only answers for today (see README)
    forceRefresh: bool = False
    debug: bool = False
    onProgress: object = field(default=None, repr=False)  # callable(ProgressEvent) | None
