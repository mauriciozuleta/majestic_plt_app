"""HS code, Spanish date and Colombian-locale number parsing for the DIAN pages."""

import re
import unicodedata

from ..dian_types import DianError

SPANISH_MONTHS = {'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dic': 12}
# DIAN prints "...", "-" or nothing where there is no value (an open-ended "Hasta")
EMPTY_MARKERS = {'', '...', '..', '-', '--', 'vacio', 'vacío', 'n/a'}


def strip_accents(text: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')


def normalize_text(text: str | None) -> str:
    """Whitespace collapsed (also non-breaking spaces), ends trimmed."""
    return re.sub(r'\s+', ' ', (text or '').replace('\xa0', ' ')).strip()


_MOJIBAKE = {'Ã³': 'ó', 'Ã©': 'é', 'Ã¡': 'á', 'Ã­': 'í', 'Ã­': 'í', 'Ãº': 'ú', 'Ã±': 'ñ', 'Ã': 'Á', 'Ã': 'É', 'Ã': 'Ó', 'Ã': 'Ú', 'Ã': 'Ñ', 'Ã“': 'Ó', 'Ã‰': 'É', 'Ã‘': 'Ñ'}


def fix_mojibake(text: str) -> str:
    """DIAN's own pages sometimes carry text that was UTF-8 encoded twice ("elaboraciÃ³n"). Repairs the usual accented-letter sequences;
    text without them is returned untouched."""
    if 'Ã' not in text:
        return text
    for broken, fixed in _MOJIBAKE.items():
        text = text.replace(broken, fixed)
    return text


def fold(text: str | None) -> str:
    """Lowercase, accent-free, whitespace-collapsed — for comparing labels ("Gravámenes" == "gravamenes")."""
    return strip_accents(normalize_text(text)).lower()


def is_empty_marker(text: str | None) -> bool:
    return fold(text) in {strip_accents(marker) for marker in EMPTY_MARKERS}


def normalize_hs_code(raw: str | None) -> str:
    """Trim; drop dots, spaces and hyphens; digits only; 4, 6, 8 or 10 digits. Never padded: DIAN resolves what the user typed."""
    code = re.sub(r'[\s.\-]', '', (raw or '').strip())
    if not code.isdigit() or len(code) not in (4, 6, 8, 10):
        raise DianError('INVALID_HS_CODE', f'"{raw}" is not a valid HS code: use 4, 6, 8 or 10 digits (dots, spaces and hyphens are ignored).')
    return code


def parse_date(text: str | None) -> str | None:
    """'01-ene-2017' -> '2017-01-01' (any case, accents tolerated); an empty marker -> None; anything else -> ValueError."""
    if is_empty_marker(text):
        return None
    match = re.fullmatch(r'(\d{1,2})[-/ ]([A-Za-zÁÉÍÓÚáéíóú]{3,})\.?[-/ ](\d{4})', normalize_text(text))
    if not match:
        raise ValueError(f'unrecognised date: {text!r}')
    month = SPANISH_MONTHS.get(fold(match.group(2))[:3])
    if not month:
        raise ValueError(f'unrecognised month in date: {text!r}')
    return f'{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}'


def parse_number(text: str) -> tuple[float | None, list[str]]:
    """A number in Colombian or plain format -> (value, warnings). '15,5' = 15.5; '1.234,50' = 1234.5; DIAN also prints plain
    decimals ('5.0 %', '0.0 %'). A lone separator followed by exactly three digits ('1.234') could be either decimals or thousands:
    it is read as thousands (the Colombian rule) and flagged."""
    warnings: list[str] = []
    cleaned = re.sub(r'[^\d.,\-]', '', normalize_text(text))
    if not cleaned or not re.search(r'\d', cleaned):
        return None, warnings
    if ',' in cleaned and '.' in cleaned:
        decimal_sep = ',' if cleaned.rfind(',') > cleaned.rfind('.') else '.'
        thousands_sep = '.' if decimal_sep == ',' else ','
        cleaned = cleaned.replace(thousands_sep, '').replace(decimal_sep, '.')
    elif ',' in cleaned or '.' in cleaned:
        sep = ',' if ',' in cleaned else '.'
        parts = cleaned.split(sep)
        if len(parts) > 2:  # 1.234.567 -> thousands
            cleaned = ''.join(parts)
        elif len(parts[1]) == 3:
            warnings.append(f'Ambiguous number "{text}": read "{sep}" as a thousands separator.')
            cleaned = ''.join(parts)
        else:
            cleaned = parts[0] + '.' + parts[1]
    try:
        return float(cleaned), warnings
    except ValueError:
        return None, warnings + [f'Could not read the number "{text}".']
