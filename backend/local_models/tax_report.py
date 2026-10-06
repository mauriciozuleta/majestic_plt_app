"""Tax-cost report for a country's opportunities, written by a local model.

For every product of one opportunity rating (default "Very High") that is
saved in Market Opportunities for a target country, the model reads that
country's baked documents and states the import taxes the product faces
(customs duty, stamp duty, consumption tax/VAT, other levies) with the
excerpt behind each figure — or says the documents don't cover it. The model
then writes the summary, and the result is laid out as a PDF saved in the
country's `reports` folder.

What the model does and doesn't do: it only extracts rates from the excerpts
and writes the summary text; it is never allowed to answer from memory. The
excerpts come from two places: (1) rows of tariff tables whose code starts with
the product's HS code (exact lookup in the baked documents) and (2) the
best semantic matches for the product's taxes. The PDF layout and the
"tax per kg" arithmetic (rate × the source price) are plain code.
"""

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import models
from ..database import SessionLocal
from ..rag_files import store
from . import ollama_client

OPTIONS = {'num_ctx': 6144, 'temperature': 0, 'num_predict': 450}
SUMMARY_OPTIONS = {'num_ctx': 6144, 'temperature': 0.2, 'num_predict': 700}
MAX_JOBS = 10
HS_ROWS = 6  # tariff-table rows handed to the model per product
SEMANTIC_PASSAGES = 3
MAX_PASSAGE_CHARS = 1100
# documents that only describe our own analysis (they mention HS codes but hold no tax rules)
OWN_DOCUMENTS = re.compile(r'Product (Portfolio|Opportunities)', re.IGNORECASE)

SYSTEM_PROMPT = """You extract import tax rates for one product from numbered excerpts of our own documents about one country.
Rules:
- Use ONLY the excerpts. Never use memory. If the excerpts do not give a rate, use null for it.
- Rates in the excerpts are already percentages (import duty 40% = 40). "GCT" is the general consumption tax, the VAT. A row whose code starts with the product's HS code applies to the product; if several rows differ, use the one that best matches the product, and say so in basis.
- Answer with ONE JSON object and nothing else, with exactly these keys:
{"duty_pct": number|null, "stamp_duty_pct": number|null, "vat_pct": number|null, "other_pct": number|null, "other_note": string, \
"status": "found"|"partial"|"not_covered", "basis": string, "cites": [excerpt numbers]}
- Percentages are plain numbers (40 for 40%). other_pct is the sum of every other tax or levy listed (environmental levy, SCF levy, excise, special consumption tax…) and other_note names them. \
basis is one short sentence saying where the rates come from and any condition (exemptions, zero-rating, origin). Use status "not_covered" when the excerpts give no rate for this product."""

SUMMARY_PROMPT = """You write the summary of an internal tax-cost report for a food import-export company. You are given FACTS (already computed, \
exact) and a table of products with the import tax rates found in our documents. Use ONLY the FACTS and the table; do not add or recompute numbers. \
Write 150-220 words of plain prose (no headings, no bullet lists): the overall picture of taxes on these products, which products carry the highest and the lowest total tax, \
how many products the documents did not cover, and what to verify before relying on these figures. Voice: "we" and "our"."""

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- evidence


def _own_chunks(country: str) -> list[dict]:
    path = store.baked_path(country)
    if not path.exists():
        return []
    data = store._read_json(path, {})
    return [chunk for chunk in data.get('chunks', []) if not OWN_DOCUMENTS.search(chunk.get('document') or '')]


# Columns of the national tariff tables (e.g. Jamaica's printable tariff) -> what they are.
# Their values are fractions (0.4 = 40%), which are shown to the model as percentages
# so it never has to convert units.
TARIFF_COLUMNS = {
    'ID': 'import duty',
    'ASD': 'additional stamp duty',
    'GCT': 'GCT (the VAT)',
    'EXC': 'excise',
    'SCTA': 'special consumption tax (A)',
    'SCTS': 'special consumption tax (S)',
    'SCTF': 'special consumption tax (F)',
    'SCF': 'SCF levy',
    'ENVL': 'environmental levy',
    'DCESS': 'cess',
}


def _percent(fraction: float) -> str:
    return f'{round(fraction * 100, 3):g}%'


def _compact_row(line: str) -> str:
    """'- Tariff Code: 0704100000; Description: …; ID 01: 0.4; ASD05: 0.32857; GCT 06: 0.15' ->
    'Tariff code 0704100000, …: import duty 40%; additional stamp duty 32.857%; GCT (the VAT) 15%'.
    Empty ('-') fields and administrative columns are left out."""
    code, description, rates = '', '', []
    for part in (piece.strip() for piece in line.lstrip('- ').split(';')):
        key, _, value = part.partition(':')
        key, value = key.strip(), value.strip()
        if key.lower() == 'tariff code':
            code = value
        elif key.lower() == 'description':
            description = value
        else:
            column = re.sub(r'[^A-Za-z]', '', key).upper()
            name = next((label for prefix, label in TARIFF_COLUMNS.items() if column.startswith(prefix.upper()) and len(column) <= len(prefix) + 2), None)
            if name and re.fullmatch(r'\d+(?:\.\d+)?', value):
                rates.append(f'{name} {_percent(float(value))}')
    if not code and not rates:
        return line.lstrip('- ').strip()
    return f"Tariff code {code}{' (' + description + ')' if description else ''}: {'; '.join(rates) if rates else 'no rates listed'}"


def hs_rows(chunks: list[dict], hs_code: str) -> list[dict]:
    """Lines of the baked documents whose tariff code starts with the HS code (the code with
    any punctuation removed), so a 6-digit HS finds its 10-digit national lines. Heading rows
    without rates are skipped, and a line repeated by overlapping chunks (or cut by a chunk
    edge) is kept once, in its longest form."""
    code = re.sub(r'\D', '', hs_code or '')
    if len(code) < 4:
        return []
    pattern = re.compile(rf'(?<![\d.]){code}\d*(?!\d)')
    best: dict[str, dict] = {}
    for chunk in chunks:
        for line in chunk['text'].splitlines():
            if not pattern.search(line) or line.count(';') < 3:
                continue
            row = _compact_row(line)
            if 'no rates listed' in row:
                continue
            key = pattern.search(row).group() if pattern.search(row) else row
            if key not in best or len(row) > len(best[key]['text']):
                best[key] = {'text': row, 'document': chunk.get('document'), 'section': chunk.get('section')}
    return [best[key] for key in sorted(best)][:HS_ROWS]


ROW_RATE = re.compile(r'(import duty|additional stamp duty|GCT \(the VAT\)|[A-Za-z][A-Za-z() ]*?) (\d+(?:\.\d+)?)%')

PICK_PROMPT = """You choose which tariff row applies to a product. You get the product and numbered tariff rows (code, description, rates). \
Answer with ONLY the number of the row whose description best matches the product (for example 2), or 0 if no row fits."""


def row_rates(row: dict) -> dict | None:
    """The taxes of one tariff row (as rewritten by _compact_row), read by code: duty, stamp duty, VAT, and
    everything else added up as 'other'. None for a row without rates."""
    found = {'duty_pct': None, 'stamp_duty_pct': None, 'vat_pct': None}
    other, names = 0.0, []
    for name, value in ROW_RATE.findall(row['text'].rsplit('): ', 1)[-1]):
        value = float(value)
        key = {'import duty': 'duty_pct', 'additional stamp duty': 'stamp_duty_pct', 'GCT (the VAT)': 'vat_pct'}.get(name.strip())
        if key:
            found[key] = value
        else:
            other += value
            names.append(f'{name.strip()} {value:g}%')
    if all(value is None for value in found.values()) and not names:
        return None
    result = {**found, 'other_pct': round(other, 4) if names else None, 'other_note': ' + '.join(names)}
    parts = [value for key, value in result.items() if key.endswith('_pct') and value is not None]
    result['total_pct'] = round(sum(parts), 3) if parts else None
    return result


def _words(text: str) -> set[str]:
    skip = {'other', 'fresh', 'chilled', 'frozen', 'whole', 'with', 'than', 'that', 'from', 'into', 'import', 'duty', 'taxes', 'much', 'cost', 'tariff', 'code'}
    out = set()
    for word in re.findall(r'[A-Za-z]{4,}', text.lower()):
        if word in skip:
            continue
        for ending in ('ies', 'es', 's'):
            if word.endswith(ending) and len(word) > len(ending) + 3:
                word = word[: -len(ending)] + ('y' if ending == 'ies' else '')
                break
        out.add(word)
    return out


def rates_from_rows(model: str, product: dict, rows: list[dict], cancel, context: str = '') -> dict | None:
    """The product's rates straight from its tariff row(s) in the documents: the numbers are read by code, never
    by the model. If several rows with different rates share the HS code, the model only picks which row fits the
    product's description. None when there is no usable row (the caller then falls back to reading the excerpts)."""
    parsed = [(row, row_rates(row)) for row in rows]
    parsed = [(row, rates) for row, rates in parsed if rates and rates['total_pct'] is not None]
    if not parsed:
        return None
    distinct = {tuple(sorted((key, value) for key, value in rates.items() if key != 'other_note')) for _, rates in parsed}
    choice = 0
    catch_all_used = False
    if len(distinct) > 1:
        # 1) words of the product (and the question) found in a row's description; a single best match wins
        # only words that single a row out count ("wing" names one row; "chicken" is in several, so it decides nothing)
        wanted = _words(f"{product['product_name']} {context}")
        row_words = [_words(row['text'].rsplit('): ', 1)[0]) for row, _ in parsed]
        scores = [sum(1 for word in wanted & words if sum(word in other for other in row_words) == 1) for words in row_words]
        best = max(scores)
        tied = [index for index, score in enumerate(scores) if score == best]
        if best > 0 and len(tied) == 1:
            choice = tied[0]
        else:
            # 2) otherwise the model picks among the best-matching rows (all of them if none matched)
            pool = tied if best > 0 else list(range(len(parsed)))
            if best == 0:
                # nothing names the product: tariffs file such goods under the catch-all "Other ..." line
                catch_all = [index for index in pool if parsed[index][0]['text'].split('(', 1)[-1].strip().lower().startswith('other')]
                pool = catch_all or pool
                catch_all_used = bool(catch_all)
            if len(pool) == 1:
                choice = pool[0]
            else:
                listing = '\n'.join(f'{number}. {parsed[index][0]["text"]}' for number, index in enumerate(pool, start=1))
                answer = _ask(model, PICK_PROMPT, f"PRODUCT: {product['product_name']}\nQUESTION: {context or product['product_name']}\n\nROWS:\n{listing}", cancel, {'num_ctx': 4096, 'temperature': 0, 'num_predict': 8})
                match = re.search(r'\d+', answer)
                number = int(match.group()) if match else 0
                if not 1 <= number <= len(pool):
                    return None  # no row clearly fits: let the caller read the excerpts and flag it
                choice = pool[number - 1]
    row, rates = parsed[choice]
    code = row['text'].split(':', 1)[0]
    how = 'the catch-all line, as no row names the product' if catch_all_used else 'chosen by description'
    note = f'{code} in {row["document"]}' + (f' (one of {len(parsed)} rows for this HS code, {how})' if len(distinct) > 1 else '')
    return {**rates, 'status': 'found', 'basis': f'Tariff row {note}.', 'cites': [1]}


def evidence(country: str, chunks: list[dict], product: dict) -> list[dict]:
    """Numbered excerpts for one product: exact tariff rows first, then the best semantic matches."""
    passages = [{'text': row['text'], 'document': row['document'], 'section': row['section']} for row in hs_rows(chunks, product['hs_code'])]
    query = f"import duty customs tariff consumption tax VAT stamp duty levy on {product['product_name']} (HS {product['hs_code'] or 'unknown'})"
    seen = {passage['text'] for passage in passages}
    for result in store.search_country(country, query, top_k=SEMANTIC_PASSAGES + 2):
        if OWN_DOCUMENTS.search(result.get('document') or '') or result['text'] in seen:
            continue
        passages.append({'text': result['text'][:MAX_PASSAGE_CHARS], 'document': result.get('document'), 'section': result.get('section')})
        seen.add(result['text'])
        if len(passages) >= HS_ROWS + SEMANTIC_PASSAGES:
            break
    return passages


# ---------------------------------------------------------------- model calls


def _ask(model: str, system: str, user: str, cancel, options: dict) -> str:
    text = ''
    for piece in ollama_client.stream_chat(model, [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], cancel, options):
        text += piece
    return re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE).strip()


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r'-?\d+(?:\.\d+)?', value)
        return float(match.group()) if match else None
    return None


def parse_answer(raw: str) -> dict | None:
    """The JSON object in the model's reply, with its numbers cleaned; None if there isn't a usable one."""
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start: end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    result = {key: _number(data.get(key)) for key in ('duty_pct', 'stamp_duty_pct', 'vat_pct', 'other_pct')}
    # the total is added up here, never taken from the model (small models add badly)
    parts = [value for value in result.values() if value is not None]
    result['total_pct'] = round(sum(parts), 3) if parts else None
    status = data.get('status') if data.get('status') in ('found', 'partial', 'not_covered') else None
    result['status'] = status or ('found' if result['total_pct'] is not None else 'not_covered')
    result['other_note'] = str(data.get('other_note') or '')[:200]
    result['basis'] = str(data.get('basis') or '')[:400]
    cites = data.get('cites') if isinstance(data.get('cites'), list) else []
    result['cites'] = [int(cite) for cite in cites if isinstance(cite, (int, float)) and not isinstance(cite, bool)]
    return result


def product_message(country: str, product: dict, passages: list[dict]) -> str:
    excerpts = '\n\n'.join(
        f"[{number}] {passage.get('document') or 'document'} > {passage.get('section') or 'section'}\n{passage['text']}"
        for number, passage in enumerate(passages, start=1)
    )
    return f"COUNTRY: {country}\nPRODUCT: {product['product_name']}\nHS CODE: {product['hs_code'] or 'unknown'}\n\nEXCERPTS:\n\n{excerpts}"


# ---------------------------------------------------------------- the job


def _opportunities(country: str, rating: str) -> list[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(models.MarketOpportunityComparison)
            .filter(models.MarketOpportunityComparison.target_country == country, models.MarketOpportunityComparison.opportunity_rating == rating)
            .order_by(models.MarketOpportunityComparison.diff_pct)
            .all()
        )
        seen, products = set(), []
        for row in rows:
            key = (row.source_country, row.product_name.lower(), row.hs_code)
            if key in seen:
                continue
            seen.add(key)
            products.append(
                {
                    'product_name': row.product_name,
                    'source_country': row.source_country,
                    'hs_code': row.hs_code,
                    'source_price_usd_kg': row.source_price_normalized,
                    'target_price_usd_kg': row.target_price_normalized,
                    'diff_pct': row.diff_pct,
                }
            )
        return products


def _table_text(rows: list[dict]) -> str:
    def rate(value):
        return 'n/a' if value is None else f'{value:g}%'

    lines = ['product | from | HS | duty | stamp | VAT | other | TOTAL | status']
    for row in rows:
        lines.append(
            f"{row['product_name']} | {row['source_country']} | {row['hs_code'] or '-'} | {rate(row['duty_pct'])} | {rate(row['stamp_duty_pct'])} | "
            f"{rate(row['vat_pct'])} | {rate(row['other_pct'])} | {rate(row['total_pct'])} | {row['status']}"
        )
    return '\n'.join(lines)


def _facts(rows: list[dict]) -> str:
    covered = sorted((row for row in rows if row['total_pct'] is not None), key=lambda row: row['total_pct'])
    lines = [f'Products in the report: {len(rows)}. With tax rates found: {len(covered)}. Not covered or unreadable: {len(rows) - len(covered)}.']
    if covered:
        totals = [row['total_pct'] for row in covered]
        middle = totals[len(totals) // 2] if len(totals) % 2 else (totals[len(totals) // 2 - 1] + totals[len(totals) // 2]) / 2
        lines.append(f'Total tax rate: lowest {totals[0]:g}%, median {middle:g}%, highest {totals[-1]:g}%.')
        lines.append('Highest total tax: ' + '; '.join(f"{row['product_name']} (from {row['source_country']}) {row['total_pct']:g}%" for row in covered[::-1][:3]) + '.')
        lines.append('Lowest total tax: ' + '; '.join(f"{row['product_name']} (from {row['source_country']}) {row['total_pct']:g}%" for row in covered[:3]) + '.')
        for label, key in (('import duty', 'duty_pct'), ('additional stamp duty', 'stamp_duty_pct'), ('VAT', 'vat_pct')):
            values = [row[key] for row in covered if row[key] is not None]
            if values:
                lines.append(f'{label.capitalize()}: found for {len(values)} products, range {min(values):g}% to {max(values):g}%.')
    return '\n'.join(lines)


def _run(job: dict) -> None:
    country, model, rating, cancel = job['country'], job['model'], job['rating'], job['cancel']
    try:
        products = _opportunities(country, rating)
        if job['limit']:
            products = products[: job['limit']]
        if not products:
            raise ollama_client.OllamaError(f'No "{rating}" opportunities are saved for {country}. Run Market Opportunities for it first.')
        chunks = _own_chunks(country)
        if not chunks:
            raise ollama_client.OllamaError(f"{country} has no baked tax documents yet — Load and Bake its files in RAG Files first.")
        job['total'] = len(products)
        started = time.monotonic()
        for index, product in enumerate(products, start=1):
            if cancel.is_set():
                break
            job['status_text'] = f"Reading taxes for {product['product_name']} ({index} of {len(products)})"
            passages = evidence(country, chunks, product)
            row = {**product, 'duty_pct': None, 'stamp_duty_pct': None, 'vat_pct': None, 'other_pct': None, 'total_pct': None, 'other_note': '', 'basis': '', 'cites': [], 'status': 'not_covered', 'evidence': passages}
            if passages:
                parsed = rates_from_rows(model, product, hs_rows(chunks, product['hs_code']), cancel)
                if not parsed and not cancel.is_set():
                    raw = _ask(model, SYSTEM_PROMPT, product_message(country, product, passages), cancel, OPTIONS)
                    parsed = parse_answer(raw)
                if parsed:
                    row.update(parsed)
                elif not cancel.is_set():
                    row['basis'] = 'The model did not return a readable answer for this product.'
                    row['status'] = 'unreadable'
            else:
                row['basis'] = 'No excerpt in the documents mentions this product or its HS code.'
            job['rows'].append(row)
            job['done'] = index
            left = (time.monotonic() - started) / index * (len(products) - index)
            job['eta_seconds'] = round(left)
        if cancel.is_set():
            job['status'] = 'cancelled'
            job['finished_at'] = time.time()
            return

        job['status_text'] = 'Writing the summary…'
        summary = _ask(model, SUMMARY_PROMPT, f"COUNTRY: {country}\nOPPORTUNITY RATING: {rating}\n\nFACTS:\n{_facts(job['rows'])}\n\nTABLE:\n{_table_text(job['rows'])}", cancel, SUMMARY_OPTIONS)
        if cancel.is_set():
            job['status'] = 'cancelled'
            job['finished_at'] = time.time()
            return
        job['summary'] = summary or 'The model returned no summary.'
        job['status_text'] = 'Laying out the PDF…'
        path = _write_pdf(job)
        job['file'] = path.name
        job['folder'] = f'backend/documents/rag_files/{path.parent.parent.name}/reports'
        job['status'] = 'done'
        job['status_text'] = 'Done.'
    except ollama_client.OllamaError as error:
        job['status'], job['error'] = 'failed', str(error)
    except Exception as error:  # reported to the screen, not raised into a dead thread
        job['status'], job['error'] = 'failed', f'Could not build the report: {error}'
    job['finished_at'] = time.time()


# ---------------------------------------------------------------- PDF


def _plain(text: str) -> str:
    """Text the PDF's built-in font can show (Windows-1252), with markup characters escaped."""
    text = str(text or '').replace('→', '->').replace('≈', '~').replace('•', '-')
    text = text.encode('cp1252', 'replace').decode('cp1252')
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _pct(value) -> str:
    return '—' if value is None else f'{value:g}%'


def _write_pdf(job: dict) -> Path:
    country, rating = job['country'], job['rating']
    folder = store.country_dir(country) / 'reports'
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = folder / f'{now:%Y-%m-%d_%H%M%S} Tax cost - {rating} opportunities.pdf'

    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['BodyText'], fontSize=9.5, leading=13)
    small = ParagraphStyle('small', parent=body, fontSize=7.4, leading=9.2)
    head = ParagraphStyle('head', parent=small, textColor=colors.white, fontName='Helvetica-Bold')
    note = ParagraphStyle('note', parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor('#555555'))

    rows = job['rows']
    covered = [row for row in rows if row['total_pct'] is not None]
    story = [
        Paragraph(_plain(f'{country}: import tax cost of our "{rating}" opportunities'), styles['Title']),
        Paragraph(_plain(f"Written by {job['model']} (local model) from {country}'s baked documents · {now:%Y-%m-%d %H:%M} UTC · {len(rows)} products, {len(covered)} with tax rates found"), note),
        Spacer(1, 5 * mm),
    ]
    for paragraph in [part for part in re.split(r'\n\s*\n', job['summary']) if part.strip()]:
        story.append(Paragraph(_plain(re.sub(r'[*_#`]+', '', paragraph).strip()), body))
        story.append(Spacer(1, 2 * mm))
    story.append(Spacer(1, 3 * mm))

    header = ['Product', 'From', 'HS', 'Duty', 'Stamp', 'VAT', 'Other', 'Total tax', 'Tax USD/kg*', 'Basis (from the documents)']
    data = [[Paragraph(label, head) for label in header]]
    for row in rows:
        per_kg = row['source_price_usd_kg'] * row['total_pct'] / 100 if row['total_pct'] is not None and row['source_price_usd_kg'] is not None else None
        basis = row['basis'] if row['status'] != 'not_covered' else (row['basis'] or 'Not covered in the documents.')
        if row['status'] == 'not_covered' and 'Not covered' not in basis:
            basis = 'Not covered in the documents. ' + basis
        other = _pct(row['other_pct']) + (f" ({row['other_note']})" if row['other_note'] and row['other_pct'] is not None else '')
        cells = [row['product_name'], row['source_country'], row['hs_code'] or '—', _pct(row['duty_pct']), _pct(row['stamp_duty_pct']), _pct(row['vat_pct']), other, _pct(row['total_pct']), '—' if per_kg is None else f'{per_kg:.2f}', basis]
        data.append([Paragraph(_plain(cell), small) for cell in cells])
    table = Table(data, repeatRows=1, colWidths=[42 * mm, 20 * mm, 16 * mm, 13 * mm, 18 * mm, 13 * mm, 24 * mm, 16 * mm, 17 * mm, 96 * mm])
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            _plain(
                '* Tax USD/kg = total tax rate x the product\'s source price per kg (as found in Majestic Market Opportunities); an indication only. '
                'Customs value, the order in which taxes compound, exemptions and origin rules can change the real amount. Rates were read by the model from the excerpts '
                'it was given, not from official sources: verify them with Customs before quoting a landed price.'
            ),
            note,
        )
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(12 * mm, 7 * mm, _plain(f'Majestic P.L.T. · {country} · {rating} opportunities · written by {job["model"]}'))
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 7 * mm, f'Page {doc.page}')
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm, title=f'{country} - tax cost of {rating} opportunities', author=job['model']).build(
        story, onFirstPage=footer, onLaterPages=footer
    )
    return path


# ---------------------------------------------------------------- job API


def start(model: str, country: str, rating: str = 'Very High', limit: int | None = None) -> dict:
    job = {
        'id': uuid.uuid4().hex,
        'model': model,
        'country': country,
        'rating': rating,
        'limit': limit,
        'status': 'running',
        'status_text': 'Finding the opportunities…',
        'done': 0,
        'total': 0,
        'eta_seconds': None,
        'rows': [],
        'summary': '',
        'file': None,
        'folder': None,
        'error': None,
        'cancel': threading.Event(),
        'started_at': time.time(),
        'finished_at': None,
    }
    with _lock:
        _jobs[job['id']] = job
        for stale in sorted(_jobs.values(), key=lambda item: item['started_at'])[: max(0, len(_jobs) - MAX_JOBS)]:
            if stale['status'] != 'running':
                del _jobs[stale['id']]
    threading.Thread(target=_run, args=(job,), name=f"tax-report-{job['id'][:8]}", daemon=True).start()
    return snapshot(job)


def snapshot(job: dict) -> dict:
    keys = ('id', 'model', 'country', 'rating', 'status', 'status_text', 'done', 'total', 'eta_seconds', 'summary', 'file', 'folder', 'error', 'started_at', 'finished_at')
    rows = [{key: row[key] for key in ('product_name', 'source_country', 'hs_code', 'duty_pct', 'stamp_duty_pct', 'vat_pct', 'other_pct', 'total_pct', 'status', 'basis')} for row in job['rows']]
    return {**{key: job[key] for key in keys}, 'rows': rows}


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def cancel_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    if job:
        job['cancel'].set()
    return job
