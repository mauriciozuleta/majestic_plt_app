"""Turns a document into a structured JSON file ready for retrieval — the
RAG Files module's converter.

Ported from the standalone "PDF to RAG" tool (pdf_to_rag.py), which turned
FAA handbook chapters into {chapter, title, sections[]} JSON with a
deterministic pipeline (extract → clean → detect headings → build sections).
What was kept: the text cleaning (page numbers, captions, repeated headers/
footers, table rewriting, joining wrapped lines) and the heading detection.
What changed for country documents:

  * not only PDF — Word (.docx), Excel (.xlsx/.xlsm/.xls), CSV/TSV,
    Markdown and plain text all produce the same JSON;
  * nothing FAA-specific (no "Chapter N", no glossary mode, no chapter number);
  * headings also recognise numbered headings ("1.2 Import Rules"), Spanish
    title-case words, and real structure where the format has it (Markdown
    `#`, Word heading styles);
  * every section carries its heading path ("Trade > Tariffs") and level;
  * spreadsheets become sections of a few dozen rows, each row written as
    "Column: value; Column: value", so a retrieved chunk reads on its own;
  * a PDF with no text layer (a scan) is reported instead of producing an
    empty file; text files try several encodings.

Everything is deterministic and offline — no AI is involved.

The JSON written (see `convert_file`):
    {schema_version, country, title, source{file, format, size_bytes, sha256},
     converted_at, stats{sections, characters}, warnings[],
     sections[{id, title, path, level, content, tags[]}]}
"""

import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

SCHEMA_VERSION = 1

PDF_EXTENSIONS = {'.pdf'}
WORD_EXTENSIONS = {'.docx'}
EXCEL_EXTENSIONS = {'.xlsx', '.xlsm', '.xls'}
CSV_EXTENSIONS = {'.csv', '.tsv'}
TEXT_EXTENSIONS = {'.md', '.markdown', '.txt'}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | WORD_EXTENSIONS | EXCEL_EXTENSIONS | CSV_EXTENSIONS | TEXT_EXTENSIONS
FORMAT_LABELS = {
    '.pdf': 'PDF', '.docx': 'Word', '.xlsx': 'Excel', '.xlsm': 'Excel', '.xls': 'Excel',
    '.csv': 'CSV', '.tsv': 'CSV', '.md': 'Markdown', '.markdown': 'Markdown', '.txt': 'Text',
}
UNSUPPORTED_HINTS = {
    '.doc': 'Old Word (.doc) files are not supported — save it as .docx and add it again.',
    '.ppt': 'PowerPoint files are not supported.',
    '.pptx': 'PowerPoint files are not supported.',
}

ROWS_PER_SECTION = 25
MAX_ROWS_PER_SHEET = 20000
MIN_SECTION_CHARS = 200
MIN_STRUCTURED_SECTION_CHARS = 60


class ConversionError(Exception):
    """A user-presentable reason a file could not be converted."""


# ------------------------------------------------------------------ cleaning
# (ported from pdf_to_rag.py)

_RE_PAGE_NUMBER = re.compile(r'^\s*(?:\d{1,3}-\d{1,3}|Page\s+\d+|P[áa]gina\s+\d+|\d{1,4})\s*$', re.MULTILINE | re.IGNORECASE)
_RE_FIGURE_CAPTION = re.compile(r'^\s*(?:Figure|Figura|Fig\.)\s+[\d\w\-]+[.:].*$', re.MULTILINE | re.IGNORECASE)
_RE_IMAGE_CAPTION = re.compile(r'^\s*(?:Image|Photo|Illustration|Diagram|Imagen|Foto)\s+[\d\w\-]+[.:].*$', re.MULTILINE | re.IGNORECASE)
_RE_CID_ARTIFACT = re.compile(r'\(cid:\d+\)')
_RE_IMAGE_ONLY_LINE = re.compile(r'^\s*(?:image|photo|illustration|diagram|graphic|imagen)\s*$', re.IGNORECASE)
_RE_DRAWING_LINE = re.compile(r'^[\s_\-=\.|/\\<>\[\]\(\)~`•·:]{4,}$')
_RE_TABLE_SEP = re.compile(r'\t+| {2,}')
_RE_MULTI_BLANK = re.compile(r'\n{3,}')


def _looks_list_bullet(line: str) -> bool:
    return bool(re.match(r'^(?:[-*•]|\d+[.)]|[A-Za-z][.)])\s+', line.strip()))


def _split_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    return [cell.strip() for cell in _RE_TABLE_SEP.split(stripped) if cell.strip()] if stripped else []


def _looks_table_row(line: str) -> bool:
    stripped = line.rstrip()
    if not stripped.strip() or _looks_list_bullet(stripped):
        return False
    return len(_split_table_cells(stripped)) >= 2 and bool(_RE_TABLE_SEP.search(stripped))


def _looks_image_artifact_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _RE_IMAGE_ONLY_LINE.match(stripped) or _RE_DRAWING_LINE.match(stripped):
        return True
    alpha = sum(ch.isalpha() for ch in stripped)
    symbols = sum(ch in '_|-=./\\<>[]()~`•·:' for ch in stripped)
    return alpha <= 2 and symbols >= max(4, len(stripped) // 2)


def _normalise_table_block(block_lines: list[str]) -> list[str]:
    rows = [row for row in (_split_table_cells(line) for line in block_lines) if len(row) >= 2]
    if len(rows) < 3:
        return block_lines
    counts = [len(row) for row in rows]
    dominant = max(set(counts), key=counts.count)
    if sum(1 for count in counts if abs(count - dominant) <= 1) < max(3, int(len(rows) * 0.6)):
        return block_lines

    first = rows[0]
    header_like = (
        len(first) >= 2
        and all(not any(ch.isdigit() for ch in cell) for cell in first)
        and sum(any(ch.isalpha() for ch in cell) for cell in first) >= max(2, len(first) - 1)
    )
    if header_like:
        headers = [re.sub(r'\s+', ' ', cell).strip().rstrip(':') or f'col_{i + 1}' for i, cell in enumerate(first)]
        output = ['Table columns: ' + ' | '.join(headers)]
        for row in rows[1:]:
            pairs = [f"{headers[i] if i < len(headers) else f'col_{i + 1}'}: {re.sub(r'\s+', ' ', cell).strip()}" for i, cell in enumerate(row)]
            output.append('- ' + '; '.join(pairs))
        return output
    return ['Table rows:'] + ['- ' + ' | '.join(re.sub(r'\s+', ' ', cell).strip() for cell in row) for row in rows]


def _rewrite_table_blocks(lines: list[str]) -> list[str]:
    rewritten: list[str] = []
    i = 0
    while i < len(lines):
        if not _looks_table_row(lines[i]):
            rewritten.append(lines[i])
            i += 1
            continue
        block: list[str] = []
        j = i
        gaps = 0
        while j < len(lines):
            current = lines[j]
            if _looks_table_row(current):
                block.append(current)
                gaps = 0
                j += 1
            elif not current.strip() and block and gaps == 0:
                gaps += 1
                j += 1
            else:
                break
        if len(block) >= 3:
            rewritten.extend(_normalise_table_block(block))
            rewritten.append('')
            i = j
        else:
            rewritten.append(lines[i])
            i += 1
    return rewritten


def _join_wrapped_lines(lines: list[str]) -> list[str]:
    joined: list[str] = []
    i = 0
    while i < len(lines):
        current = lines[i].strip()
        if not current:
            joined.append('')
            i += 1
            continue
        while i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if not nxt or _looks_list_bullet(current) or _looks_list_bullet(nxt) or _looks_table_row(current) or _looks_table_row(nxt):
                break
            if current.endswith('-') and nxt[:1].isalnum():
                current = current[:-1] + nxt
                i += 1
                continue
            if current.endswith(('.', '!', '?', ':', ';')):
                break
            if nxt[:1].islower() or current.endswith((',', '(', '/')) or len(current) >= 60:
                current = f'{current} {nxt}'
                i += 1
                continue
            break
        joined.append(re.sub(r'\s+', ' ', current).strip())
        i += 1
    return joined


def clean_text(raw_text: str) -> str:
    """Page numbers, figure captions, image artifacts and repeated headers/
    footers removed; tables rewritten as rows; wrapped lines rejoined."""
    text = _RE_CID_ARTIFACT.sub('', raw_text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0c', '\n\n'))
    text = _RE_FIGURE_CAPTION.sub('', text)
    text = _RE_IMAGE_CAPTION.sub('', text)
    text = _RE_PAGE_NUMBER.sub('', text)
    lines = text.splitlines()
    counts: dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if stripped:
            counts[stripped] = counts.get(stripped, 0) + 1
    kept = [
        line
        for line in lines
        if not (line.strip() and counts.get(line.strip(), 0) >= 3 and len(line.strip()) < 120) and not _looks_image_artifact_line(line)
    ]
    kept = _join_wrapped_lines(_rewrite_table_blocks(kept))
    return _RE_MULTI_BLANK.sub('\n\n', '\n'.join(kept)).strip()


# ---------------------------------------------------------- heading detection

# Short words that are legitimately lowercase inside a Title Case heading (English + Spanish).
_MINOR_WORDS = frozenset(
    'a an the to of in on at for by and or nor but with as from into over under about above below between through during '
    'de del la las el los y e o u en para por con sin sobre entre al un una'.split()
)
_RE_NUMBER_PREFIX = re.compile(r'^(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)]|[A-Z][.)])\s+')


def _looks_title_case(text: str) -> bool:
    words = text.split()
    if not words or not words[0][:1].isupper():
        return False
    for word in words[1:]:
        alpha = word.strip('\'"')
        if not alpha or not alpha[0].isalpha() or alpha.lower() in _MINOR_WORDS:
            continue
        if not alpha[0].isupper():
            return False
    return any(c.isupper() for c in text)


def _is_heading(line: str) -> bool:
    """A short Title Case or ALL CAPS line with no sentence punctuation. A
    leading number ("1.2 Import Rules") is ignored when judging it."""
    stripped = line.strip()
    if not stripped or not stripped[0].isalnum() or not (3 <= len(stripped) <= 120):
        return False
    body = _RE_NUMBER_PREFIX.sub('', stripped, count=1) if _RE_NUMBER_PREFIX.match(stripped) else stripped
    if not body or '.' in body or ':' in body or body.endswith((',', ';')):
        return False
    if _RE_FIGURE_CAPTION.match(stripped) or _RE_PAGE_NUMBER.match(stripped):
        return False
    return _looks_title_case(body) or (body == body.upper() and any(c.isalpha() for c in body))


def _merge_short_sections(sections: list[dict], min_chars: int) -> list[dict]:
    """Headings picked out of lists/tables make tiny sections, which retrieve
    badly — fold them into the section before (or after, for the first one)."""
    sections = [dict(section) for section in sections]
    kept: list[dict] = []
    i = 0
    while i < len(sections):
        section = sections[i]
        if len(section['content']) < min_chars:
            if kept:
                previous = kept[-1]
                previous['content'] = '\n'.join(part for part in (previous['content'], section['title'], section['content']) if part).strip()
                i += 1
                continue
            if i + 1 < len(sections):
                # the first section is short: it absorbs the next one and keeps its own title
                following = sections[i + 1]
                sections[i + 1] = {
                    **section,
                    'content': '\n\n'.join(part for part in (section['content'], following['title'], following['content']) if part).strip(),
                }
                i += 1
                continue
        kept.append(section)
        i += 1
    return kept


def detect_sections(text: str, fallback_title: str = 'Content') -> list[dict]:
    """Splits cleaned text into [{title, content}] by its headings (three
    passes: collect heading lines, merge adjacent ones, drop dense clusters —
    table cells and listings — that only look like headings)."""
    lines = text.splitlines()
    raw = [i for i, line in enumerate(lines) if _is_heading(line) and (i == 0 or lines[i - 1].strip() == '')]
    if not raw:
        return [{'title': fallback_title, 'content': text.strip()}]

    merged: list[dict] = []
    i = 0
    while i < len(raw):
        start, end, parts = raw[i], raw[i], [lines[raw[i]].strip()]
        j = i + 1
        while j < len(raw) and raw[j] - end <= 4 and all(not ln.strip() for ln in lines[end + 1: raw[j]]):
            parts.append(lines[raw[j]].strip())
            end = raw[j]
            j += 1
        merged.append({'line': start, 'end': end, 'title': ' '.join(parts)})
        i = j

    headings: list[dict] = []
    i = 0
    while i < len(merged):
        cluster = [merged[i]]
        j = i + 1
        while j < len(merged) and merged[j]['line'] - merged[j - 1]['end'] <= 12:
            cluster.append(merged[j])
            j += 1
        if len(cluster) < 4:
            headings.extend(cluster)
        i = j
    if not headings:
        return [{'title': fallback_title, 'content': text.strip()}]

    sections: list[dict] = []
    if headings[0]['line'] > 0 and '\n'.join(lines[: headings[0]['line']]).strip():
        sections.append({'title': fallback_title, 'content': '\n'.join(lines[: headings[0]['line']]).strip()})
    for index, heading in enumerate(headings):
        stop = headings[index + 1]['line'] if index + 1 < len(headings) else len(lines)
        sections.append({'title': heading['title'], 'content': '\n'.join(lines[heading['end'] + 1: stop]).strip()})
    return _merge_short_sections(sections, MIN_SECTION_CHARS)


# --------------------------------------------------------------- per format


def _decode(data: bytes) -> str:
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def _pdf_text(path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text
    except ImportError as error:  # pdfminer.six ships with pdfplumber, already a dependency
        raise ConversionError('PDF reading is not available (pdfminer.six is not installed).') from error
    try:
        return extract_text(str(path))
    except Exception as error:
        raise ConversionError(f'Could not read this PDF: {error}') from error


_RE_MD_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')


def sections_from_markdown(text: str, fallback_title: str) -> list[dict]:
    """Sections from `#` headings, each with its level and heading path."""
    sections: list[dict] = []
    stack: list[tuple[int, str]] = []
    title, level, buffer = fallback_title, 1, []
    in_fence = False

    def flush():
        content = '\n'.join(buffer).strip()
        if content or sections:
            sections.append({'title': title, 'level': level, 'path': ' > '.join(name for _, name in stack) or title, 'content': content})

    for line in text.splitlines():
        if line.strip().startswith('```'):
            in_fence = not in_fence
        match = None if in_fence else _RE_MD_HEADING.match(line)
        if match:
            if buffer or stack:
                flush()
            buffer = []
            level, title = len(match.group(1)), match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            buffer.append(line)
    flush()
    sections = [section for section in sections if section['content']]
    return sections or [{'title': fallback_title, 'level': 1, 'path': fallback_title, 'content': text.strip()}]


_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_RE_WORD_HEADING = re.compile(r'^(?:heading|title|subtitle|t[ií]tulo|titre|[üu]berschrift)\s*(\d)?$', re.IGNORECASE)


def _word_paragraph(paragraph) -> tuple[str, str, bool]:
    """(text, style id, is list item) of one w:p."""
    pieces = []
    for node in paragraph.iter():
        if node.tag == f'{_W}t' and node.text:
            pieces.append(node.text)
        elif node.tag == f'{_W}tab':
            pieces.append(' ')
        elif node.tag == f'{_W}br':
            pieces.append('\n')
    properties = paragraph.find(f'{_W}pPr')
    style = ''
    is_list = False
    if properties is not None:
        style_node = properties.find(f'{_W}pStyle')
        if style_node is not None:
            style = style_node.get(f'{_W}val', '')
        is_list = properties.find(f'{_W}numPr') is not None
    return ''.join(pieces).strip(), style, is_list


def _word_to_markdown(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read('word/document.xml'))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise ConversionError('This is not a valid .docx file.') from error
    body = root.find(f'{_W}body')
    lines: list[str] = []
    for child in body if body is not None else []:
        if child.tag == f'{_W}p':
            text, style, is_list = _word_paragraph(child)
            if not text:
                lines.append('')
                continue
            heading = _RE_WORD_HEADING.match(style.replace(' ', ''))
            if heading:
                level = 1 if style.lower().startswith(('title', 'subtitle')) and not heading.group(1) else int(heading.group(1) or 1)
                lines.extend(['', f"{'#' * max(1, min(level, 6))} {text}", ''])
            else:
                lines.append(('- ' if is_list else '') + text)
                if not is_list:
                    lines.append('')
        elif child.tag == f'{_W}tbl':
            rows = []
            for row in child.iter(f'{_W}tr'):
                cells = []
                for cell in row.findall(f'{_W}tc'):
                    cells.append(' '.join(_word_paragraph(p)[0] for p in cell.iter(f'{_W}p') if _word_paragraph(p)[0]).strip())
                rows.append(cells)
            lines.extend(_table_lines(rows))
            lines.append('')
    return '\n'.join(lines)


def _cell_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat(sep=' ')
    return re.sub(r'\s+', ' ', str(value)).strip()


def _table_lines(rows: list[list]) -> list[str]:
    """Rows as "- Header: value; Header: value" under a "Columns:" line."""
    rows = [[_cell_text(cell) for cell in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    header_index = next((i for i, row in enumerate(rows[:10]) if sum(1 for cell in row if cell) >= 2), 0)
    headers = [cell or f'col_{i + 1}' for i, cell in enumerate(rows[header_index])]
    lines = ['Columns: ' + ' | '.join(headers)]
    for row in rows[header_index + 1:]:
        pairs = [f"{headers[i] if i < len(headers) else f'col_{i + 1}'}: {cell}" for i, cell in enumerate(row) if cell]
        if pairs:
            lines.append('- ' + '; '.join(pairs))
    return lines


def _sections_from_rows(sheet_name: str, rows: list[list], warnings: list[str]) -> list[dict]:
    if len(rows) > MAX_ROWS_PER_SHEET:
        warnings.append(f'Sheet "{sheet_name}" has {len(rows)} rows — only the first {MAX_ROWS_PER_SHEET} were converted.')
        rows = rows[:MAX_ROWS_PER_SHEET]
    lines = _table_lines(rows)
    if len(lines) <= 1:
        return []
    columns, data = lines[0], lines[1:]
    sections = []
    for start in range(0, len(data), ROWS_PER_SECTION):
        group = data[start: start + ROWS_PER_SECTION]
        title = sheet_name if len(data) <= ROWS_PER_SECTION else f'{sheet_name} — rows {start + 1}–{start + len(group)}'
        sections.append({'title': title, 'level': 1, 'path': sheet_name, 'content': '\n'.join([columns, *group])})
    return sections


def _excel_sections(path: Path, warnings: list[str]) -> list[dict]:
    sections: list[dict] = []
    if path.suffix.lower() == '.xls':
        try:
            import xlrd

            book = xlrd.open_workbook(str(path))
            for sheet in book.sheets():
                rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
                sections.extend(_sections_from_rows(sheet.name, rows, warnings))
        except Exception as error:
            raise ConversionError(f'Could not read this Excel file: {error}') from error
        return sections
    try:
        import openpyxl

        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in book.worksheets:
                sections.extend(_sections_from_rows(sheet.title, [list(row) for row in sheet.iter_rows(values_only=True)], warnings))
        finally:
            book.close()
    except Exception as error:
        raise ConversionError(f'Could not read this Excel file: {error}') from error
    return sections


def _csv_sections(path: Path, warnings: list[str]) -> list[dict]:
    text = _decode(path.read_bytes())
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == '.tsv' else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    return _sections_from_rows(path.stem, rows, warnings)


# ------------------------------------------------------------------- driver


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def convert_file(path: Path, country: str) -> dict:
    """The JSON document for one file. Raises ConversionError with a reason
    the user can act on."""
    suffix = path.suffix.lower()
    if suffix in UNSUPPORTED_HINTS:
        raise ConversionError(UNSUPPORTED_HINTS[suffix])
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ConversionError(f'"{suffix or path.name}" files are not supported. Use PDF, Word (.docx), Excel, CSV, Markdown or text.')

    warnings: list[str] = []
    stem = path.stem
    if suffix in PDF_EXTENSIONS:
        raw = _pdf_text(path)
        if len(raw.strip()) < 50:
            raise ConversionError('This PDF has no readable text (it may be a scan). Run OCR on it first, then add it again.')
        sections = [{**section, 'level': 1, 'path': section['title']} for section in detect_sections(clean_text(raw), fallback_title=stem)]
    elif suffix in WORD_EXTENSIONS:
        sections = sections_from_markdown(_word_to_markdown(path), stem)
        if len(sections) == 1 and sections[0]['level'] == 1 and sections[0]['title'] == stem:
            sections = [{**s, 'level': 1, 'path': s['title']} for s in detect_sections(clean_text(sections[0]['content']), fallback_title=stem)]
    elif suffix in EXCEL_EXTENSIONS:
        sections = _excel_sections(path, warnings)
    elif suffix in CSV_EXTENSIONS:
        sections = _csv_sections(path, warnings)
    elif suffix in {'.md', '.markdown'}:
        sections = sections_from_markdown(_decode(path.read_bytes()), stem)
    else:  # .txt
        sections = [{**s, 'level': 1, 'path': s['title']} for s in detect_sections(clean_text(_decode(path.read_bytes())), fallback_title=stem)]

    sections = [section for section in sections if section['content'].strip()]
    if not sections:
        raise ConversionError('No readable content was found in this file.')
    if suffix in WORD_EXTENSIONS | TEXT_EXTENSIONS - {'.txt'}:
        # real headings (Markdown, Word styles): only fold in near-empty sections
        sections = _merge_short_sections(sections, MIN_STRUCTURED_SECTION_CHARS)

    numbered = [
        {'id': str(number), 'title': section['title'], 'path': section.get('path') or section['title'], 'level': section.get('level', 1), 'content': section['content'].strip(), 'tags': []}
        for number, section in enumerate(sections, start=1)
    ]
    title = stem if suffix in EXCEL_EXTENSIONS | CSV_EXTENSIONS else numbered[0]['path'].split(' > ')[0]
    for section in numbered:
        if len(section['content']) < 20:
            warnings.append(f'Section {section["id"]} ("{section["title"]}") is very short.')
    return {
        'schema_version': SCHEMA_VERSION,
        'country': country,
        'title': title,
        'source': {'file': path.name, 'format': FORMAT_LABELS[suffix], 'size_bytes': path.stat().st_size, 'sha256': file_sha256(path)},
        'converted_at': datetime.now(timezone.utc).isoformat(),
        'stats': {'sections': len(numbered), 'characters': sum(len(s['content']) for s in numbered)},
        'warnings': warnings[:20],
        'sections': numbered,
    }
