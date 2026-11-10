"""Modification reports: one markdown document per manual change to the product catalog (today: products deleted from a Country Product Portfolio).
The files live in documents/modification_reports/ and routers/knowledge_base.py mirrors them into Documentation ▸ Modification Reports
(report_key `modification_report:<file name>`)."""

from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent / 'documents' / 'modification_reports'
KEY_PREFIX = 'modification_report:'
NL = chr(10)


def _cell(value) -> str:
    text = '' if value is None else str(value)
    return text.replace('|', '/').replace('\n', ' ').strip() or '—'


def write_deletion_report(removed: list[dict], requested: int, deleted_by: str) -> tuple[Path, str]:
    """`removed` = [{country, source, category, name, unit, price, currency, per_kg, id}]; returns (path, display name)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y-%m-%d_%H%M%S')
    countries = sorted({item['country'] for item in removed if item['country']})
    sources = sorted({item['source'] for item in removed})
    noun = 'product' if len(removed) == 1 else 'products'
    title = f'Modification report — {len(removed)} {noun} deleted ({", ".join(countries) or "catalog"})'

    lines = [
        f'# {title}',
        '',
        f'- **Date (UTC):** {now.strftime("%Y-%m-%d %H:%M:%S")}',
        f'- **Done by:** {deleted_by or "unknown user"}',
        '- **Action:** products deleted from the product catalog (Market Analysis ▸ Country Information ▸ Country Product Portfolio)',
        f'- **Products selected:** {requested}',
        f'- **Products removed from the database:** {len(removed)}',
        f'- **Sources affected:** {", ".join(sources) or "none"}',
        '',
        '## Deleted products',
        '',
        '| # | Country | Source | Category | Product | Unit | Price | Price per kg |',
        '|---|---------|--------|----------|---------|------|-------|--------------|',
    ]
    for number, item in enumerate(removed, start=1):
        price = f'{item["price"]} {item["currency"]}'.strip() if item.get('price') is not None else '—'
        per_kg = f'{item["per_kg"]} {item["currency"]}'.strip() if item.get('per_kg') is not None else '—'
        lines.append(
            f'| {number} | {_cell(item["country"])} | {_cell(item["source"])} | {_cell(item["category"])} | {_cell(item["name"])} | {_cell(item["unit"])} | {_cell(price)} | {_cell(per_kg)} |'
        )
    lines += [
        '',
        '## Notes',
        '',
        '- The products were removed from the stored catalog of each source. Updating a source again from its website can bring them back.',
        '- Custom price/weight overrides saved for these rows are kept (they only apply when the product reappears).',
        '',
    ]
    path = REPORTS_DIR / f'{stamp}_{len(removed)}-products.md'
    path.write_text(NL.join(lines), encoding='utf-8')
    return path, title


def write_chat_report(messages: list[dict], cleared_by: str) -> tuple[Path, str]:
    """`messages` = the Assistant chat log, oldest first: [{sender, text, sources, created_at}]. The whole conversation is kept in the report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    noun = 'message' if len(messages) == 1 else 'messages'
    title = f'Modification report — Assistant chat cleared ({len(messages)} {noun})'
    lines = [
        f'# {title}',
        '',
        f'- **Date (UTC):** {now.strftime("%Y-%m-%d %H:%M:%S")}',
        f'- **Done by:** {cleared_by or "unknown user"}',
        '- **Action:** the Assistant chat (Agents tab) was cleared; the conversation below was removed from the database',
        f'- **Messages removed:** {len(messages)}',
        f'- **Conversation from:** {messages[0].get("created_at", "")} **to** {messages[-1].get("created_at", "")}',
        '',
        '## Conversation',
        '',
    ]
    for message in messages:
        who = 'You' if message.get('sender') == 'user' else 'Assistant'
        lines.append(f'**{who}** · {message.get("created_at", "")}')
        lines.append('')
        lines.extend(f'> {line}' if line.strip() else '>' for line in (message.get('text') or '').splitlines() or [''])
        sources = [source for source in message.get('sources') or [] if source]
        if sources:
            lines.append('')
            lines.append(f'_Sources: {"; ".join(sources)}_')
        lines.append('')
    path = REPORTS_DIR / f'{now.strftime("%Y-%m-%d_%H%M%S")}_chat-cleared.md'
    path.write_text(NL.join(lines), encoding='utf-8')
    return path, title
