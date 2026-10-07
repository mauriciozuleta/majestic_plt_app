"""The nomenclature pages of WebArancel: the "Por código de nomenclatura" listing, the product profile and the "no results" page."""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from .. import selectors
from .dates_numbers import fix_mojibake, fold, normalize_text

_LINE_CODE = re.compile(r'^\d{4}\.\d{2}\.\d{2}\.\d{2}$')


@dataclass
class ListedLine:
    hsCode: str  # 10 digits
    displayCode: str  # 0901.21.10.00
    description: str  # the line's own designation ("- - - En grano")
    profileId: str | None = None  # the id passed to mostrarPerfil(); informational only, never used to build a URL

    def to_dict(self) -> dict:
        return {'hsCode': self.hsCode, 'description': self.description}


def is_not_found(html: str) -> bool:
    """The search page answers an unknown code in place with 'No existen nomenclaturas'."""
    return selectors.NOT_FOUND_TEXT in fold(BeautifulSoup(html, 'html.parser').get_text(' '))


def parse_listing(html: str) -> list[ListedLine]:
    """Every 10-digit tariff line of the 'Por código de nomenclatura' result, in page order. Heading rows (chapter, 6-digit
    subheading, dash-prefixed groups) have no link text of that shape and are skipped; a heading's description is added to the
    designation of the lines under it by the caller when it needs the full wording."""
    soup = BeautifulSoup(html, 'html.parser')
    lines: list[ListedLine] = []
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 4:
            continue
        link = cells[0].find('a')
        code = normalize_text(link.get_text()) if link else ''
        if not _LINE_CODE.match(code):
            continue
        onclick = link.get('onclick') or ''
        match = re.search(r'mostrarPerfil\((\d+)\)', onclick)
        lines.append(ListedLine(hsCode=code.replace('.', ''), displayCode=code, description=fix_mojibake(normalize_text(cells[3].get_text(' '))), profileId=match.group(1) if match else None))
    return lines


@dataclass
class MeasureRow:
    name: str
    importAvailable: bool
    buttonId: str | None = None


@dataclass
class Profile:
    recognized: bool
    displayCode: str | None = None
    hsCode: str | None = None
    description: str | None = None
    unit: str | None = None
    measures: list[MeasureRow] = field(default_factory=list)

    def measure(self, name: str) -> MeasureRow | None:
        """The row whose visible name is `name` (accent- and case-insensitive) — never found by position or by generated ids."""
        wanted = fold(name)
        return next((row for row in self.measures if fold(row.name) == wanted), None)


def parse_profile(html: str) -> Profile:
    """The 'Perfil de la mercancía' page: code, description, unit and the measures table with the availability of each Importaciones button."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', id=re.compile(selectors.MEASURES_TABLE_ID_SUFFIX + '$'))
    code_cell = next((td for td in soup.find_all('td') if _LINE_CODE.match(normalize_text(td.get_text()))), None)
    if table is None or code_cell is None:
        return Profile(recognized=False)
    profile = Profile(recognized=True, displayCode=normalize_text(code_cell.get_text()))
    profile.hsCode = profile.displayCode.replace('.', '')
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) >= 2 and fold(cells[0].get_text()) == 'descripcion':
            profile.description = normalize_text(cells[1].get_text(' - '))
        elif len(cells) >= 2 and fold(cells[0].get_text()) == 'unidad fisica':
            profile.unit = normalize_text(cells[1].get_text(' '))
    for tr in table.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        name_span = cells[0].find('span')
        if name_span is None:
            continue
        button = tr.find('input', id=re.compile(selectors.IMPORT_BUTTON_ID_SUFFIX + '$'))
        profile.measures.append(MeasureRow(name=normalize_text(name_span.get_text()), importAvailable=button is not None and not button.has_attr('disabled'), buttonId=button.get('id') if button else None))
    return profile
