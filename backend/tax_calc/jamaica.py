"""Jamaica: import taxes from the Jamaica Customs printable tariff (tariff.csv).

The file lists, per 10-digit tariff line, the charges that apply as fractions of the customs value (0.4 = 40%):
  ID 01 import duty · ASD05 additional stamp duty · GCT 06 general consumption tax (the VAT) · EXC023 excise
  SCTA08/SCTS18/SCTF028 special consumption tax · SCF90 SCF levy · ENVL20 environmental protection levy
  DCess96 cess · CAF customs administrative fee
A few lines carry a specific charge written as text ("US$1 per litre", "J$ 1,400 per LPA"); those are reported, not guessed.

Rules applied (see the notes on every result): charges are on the CIF value (goods + freight + insurance); GCT is charged on
CIF plus the duties (cumulative), as Jamaica's profile in RAG Files states; CARICOM-origin goods are free of import duty.
"""

import csv
import re
import shutil
from datetime import datetime
from pathlib import Path

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, money, query_words, rank, stem

FOLDER = DATA_ROOT / 'Jamaica'
RAG_SOURCE = Path(__file__).resolve().parent.parent / 'documents' / 'rag_files' / 'Jamaica' / 'source'

# CSV column -> (label, base): 'cif' = on the CIF value, 'gct' = on CIF + the duties charged before it
CHARGES = {
    'ID 01': ('Import duty', 'cif'),
    'ASD05': ('Additional stamp duty', 'cif'),
    'EXC023': ('Excise duty', 'cif'),
    'SCTA08': ('Special consumption tax (A)', 'cif'),
    'SCTS18': ('Special consumption tax (S)', 'cif'),
    'SCTF028': ('Special consumption tax (F)', 'cif'),
    'SCF90': ('SCF levy', 'cif'),
    'ENVL20': ('Environmental protection levy', 'cif'),
    'DCess96': ('Cess', 'cif'),
    'CAF': ('Customs administrative fee', 'cif'),
    'GCT 06': ('General consumption tax (GCT)', 'gct'),
}
IN_GCT_BASE = ('ID 01', 'ASD05', 'EXC023', 'SCTA08', 'SCTS18', 'SCTF028')  # charged before GCT, so GCT is charged on them too
CARICOM = {
    'antigua and barbuda', 'bahamas', 'barbados', 'belize', 'dominica', 'grenada', 'guyana', 'haiti', 'jamaica', 'montserrat',
    'saint kitts and nevis', 'saint lucia', 'saint vincent and the grenadines', 'suriname', 'trinidad and tobago',
}
ADVANCE_GCT = 0.05  # advance GCT on commercial importation by a GCT-registered taxpayer (credited against GCT later)


def _fraction(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class JamaicaCalculator(Calculator):
    name = 'Jamaica'
    currency = 'JMD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.loaded_at: str | None = None

    # ------------------------------------------------------------ data
    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.csv'

    def refresh(self) -> dict:
        """Takes the tariff from the file uploaded in RAG Files (if present), then reloads it."""
        FOLDER.mkdir(parents=True, exist_ok=True)
        candidates = sorted(RAG_SOURCE.glob('*TARIFF*.csv')) if RAG_SOURCE.exists() else []
        if candidates:
            shutil.copyfile(candidates[-1], self.path)
        self._load()
        return self.info()

    def _load(self) -> None:
        self.lines, self.by_code = [], {}
        if not self.path.exists():
            return
        stack: list[tuple[str, str]] = []  # (code without trailing zeros, description) of the heading rows above
        with open(self.path, encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                code = (row.get('Tariff Code') or '').strip()
                description = (row.get('Description') or '').strip()
                short = re.sub(r'\D', '', code).rstrip('0') if re.fullmatch(r'\d{10}', code) else None
                if short is None or len(short) < 4:
                    short = (re.sub(r'\D', '', code)[:4] or code) if not re.fullmatch(r'\d{10}', code) else short
                while stack and not (short.startswith(stack[-1][0]) and len(stack[-1][0]) < len(short)):
                    stack.pop()
                rates = {column: (row.get(column) or '').strip() for column in CHARGES}
                has_rates = any(value not in ('', '-') for value in rates.values())
                if not has_rates:  # a heading: remembered as context for the lines below it
                    stack.append((short, description))
                    continue
                path = [item[1].rstrip(':').strip() for item in stack] + [description.rstrip(':').strip()]
                line = {
                    'code': code,
                    'description': description,
                    'path': ' > '.join(part for part in path if part),
                    'units': (row.get('Units 1') or '').strip() or None,
                    'rates': {column: value for column, value in rates.items() if value not in ('', '-')},
                }
                self.lines.append(line)
                self.by_code[code] = line
        self.loaded_at = datetime.fromtimestamp(self.path.stat().st_mtime).strftime('%Y-%m-%d')

    def _ensure(self) -> None:
        if not self.lines:
            self._load()

    def info(self) -> dict:
        self._ensure()
        return {
            'country': self.name,
            'ready': bool(self.lines),
            'lines': len(self.lines),
            'source': 'Jamaica Customs printable tariff (tariff.csv)',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the tariff CSV uploaded in RAG Files (Jamaica).',
            'currency': self.currency,
        }

    def signature(self, line: dict):
        """What makes two lines tax alike (used to tell whether a choice between them matters)."""
        return tuple(sorted(line['rates'].items()))

    # ------------------------------------------------------------ lookup
    def _summary(self, line: dict) -> str:
        parts = []
        for column, value in line['rates'].items():
            number = _fraction(value)
            label = CHARGES[column][0]
            parts.append(f'{label} {number * 100:g}%' if number is not None else f'{label} {value}')
        return '; '.join(parts)

    def _public(self, line: dict) -> dict:
        return {'code': line['code'], 'description': line['description'], 'path': line['path'], 'units': line['units'], 'summary': self._summary(line)}

    def search(self, query: str, limit: int = 30) -> list[dict]:
        self._ensure()
        query = (query or '').strip()
        if not query:
            return []
        if re.fullmatch(r'[\d.\s]+', query):
            prefix = digits(query)
            return [self._public(line) for line in self.lines if line['code'].startswith(prefix)][:limit]
        words = query_words(query)
        if not words:
            return []
        scored = []
        for line in self.lines:
            key = rank(line, words)
            if key is not None:
                scored.append((key, line))
        scored.sort(key=lambda item: item[0])
        return [self._public(line) for _, line in scored[:limit]]

    def get(self, code: str) -> dict | None:
        self._ensure()
        line = self.by_code.get((code or '').strip())
        return self._public(line) if line else None

    # ------------------------------------------------------------ calculation
    def calculate(self, code: str, inputs: Inputs) -> Result:
        self._ensure()
        line = self.by_code.get((code or '').strip())
        if line is None:
            raise ValueError(f'Tariff line {code} not found in the Jamaica tariff.')
        cif = inputs.goods_value_usd + inputs.freight_usd + inputs.insurance_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'CIF value', 'amount_usd': round(cif, 2), 'formula': f'goods {money(inputs.goods_value_usd)} + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}'},
            sources=['Jamaica Customs printable tariff, tariff line ' + line['code']],
        )
        result.notes.append('Charges are calculated on the CIF value (goods + freight + insurance) in USD; Jamaican dollar equivalents depend on the exchange rate on the day of entry.')
        result.notes.append('GCT is charged on the CIF value plus import duty, additional stamp duty, excise and special consumption tax (cumulative), as in Jamaica\'s profile.')

        caricom = (inputs.origin or '').strip().lower() in CARICOM
        if caricom:
            result.notes.append(f'{inputs.origin} is a CARICOM member: goods of CARICOM origin (with a certificate of origin) enter free of import duty. Check whether additional stamp duty also falls away for this line.')

        charged = {}
        for column, (label, base) in CHARGES.items():
            value = line['rates'].get(column)
            if value is None:
                continue
            fraction = _fraction(value)
            if fraction is None:
                result.complete = False
                result.warnings.append(f'{label}: this line carries a specific charge written as "{value}" that is not included in the total.')
                continue
            if column == 'ID 01' and caricom:
                result.taxes.append(Tax(label, 0.0, '0% (CARICOM origin)', 'CIF value', f'CARICOM origin: import duty waived (tariff rate {fraction * 100:g}%)'))
                charged[column] = 0.0
                continue
            if base == 'cif':
                amount = cif * fraction
                charged[column] = amount
                result.taxes.append(Tax(label, amount, f'{fraction * 100:g}%', 'CIF value', f'{money(cif)} × {fraction * 100:g}%'))
        if 'GCT 06' in line['rates']:
            fraction = _fraction(line['rates']['GCT 06'])
            if fraction is not None:
                before = sum(charged.get(column, 0.0) for column in IN_GCT_BASE)
                base_value = cif + before
                result.taxes.append(Tax('General consumption tax (GCT)', base_value * fraction, f'{fraction * 100:g}%', 'CIF value + duties', f'({money(cif)} + {money(before)}) × {fraction * 100:g}%'))
                if inputs.commercial_importer and fraction > 0:
                    result.taxes.append(
                        Tax('Advance GCT (commercial importer)', base_value * ADVANCE_GCT, '5%', 'CIF value + duties', f'({money(cif)} + {money(before)}) × 5%', recoverable=True,
                            note='Paid at the border by a GCT-registered commercial importer and credited against GCT later — not counted in the total.')
                    )
        if inputs.origin and not caricom:
            result.notes.append(f'No origin-based preference is applied for {inputs.origin} (none is listed in the Jamaican tariff file); the standard rates apply.')
        result.warnings.append('Import licences, safeguard measures and sanitary/phytosanitary requirements can apply to some products and are not taxes — check them separately.')
        return result
