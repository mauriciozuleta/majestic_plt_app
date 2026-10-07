"""A fallback parser for diagnostics only: every table of a page as { label, columns, rows, rawText }."""

from bs4 import BeautifulSoup

from .dates_numbers import normalize_text


def parse_generic_tables(html: str, limit: int = 6) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    tables = []
    for table in soup.find_all('table'):
        rows = [[normalize_text(cell.get_text(' ')) for cell in tr.find_all(['th', 'td'], recursive=False)] for tr in table.find_all('tr') if tr.find_parent('table') is table]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        tables.append({'label': table.get('id') or ' '.join(table.get('class') or []) or None, 'columns': rows[0], 'rows': rows[1:], 'rawText': normalize_text(table.get_text(' '))[:500]})
        if len(tables) >= limit:
            break
    return tables


def page_summary(html: str) -> dict:
    """What to show when the expected structure isn't there: the title and the tables found."""
    soup = BeautifulSoup(html, 'html.parser')
    return {'title': normalize_text(soup.title.get_text()) if soup.title else None, 'tables': parse_generic_tables(html)}
