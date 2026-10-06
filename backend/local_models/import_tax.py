"""Import-tax questions in the local-model chat ("how much tax per kg to import tomatoes from
Colombia to Jamaica?").

A question like that is answered from the DESTINATION country's baked documents, not from whichever
country is selected in the chat, and it needs the product's exact tariff row, not just the passages
that happen to read like it. So before the model writes anything this module:

1. works out the destination and origin countries and the product from the question,
2. finds the product's HS code (the cache of classified product names),
3. looks up the tariff rows for that HS code in the destination's baked documents (plus the best
   semantic passages), has the model read the rates from them, and
4. computes the tax per kg / per USD of customs value in code,

then hands the model those FACTS to write the answer from. The model never does the arithmetic.
"""

import re
from collections import Counter

from .. import models
from ..database import SessionLocal
from . import tax_report

TAX_WORDS = re.compile(r'\b(tax|taxes|duty|duties|tariff|tariffs|levy|levies|vat|gct|customs)\b', re.IGNORECASE)
IMPORT_WORDS = re.compile(r'\bimport(?:s|ed|ing)?\b', re.IGNORECASE)
STOP = {'much', 'cost', 'costs', 'import', 'imports', 'imported', 'importing', 'taxes', 'tariff', 'tariffs', 'terms', 'paid', 'from', 'into', 'what', 'that', 'this', 'with', 'have', 'will', 'tax', 'duty', 'duties', 'levy', 'levies', 'customs', 'price', 'fresh', 'per', 'the', 'and', 'for', 'how', 'are', 'kilo', 'kilogram', 'kilograms'}


def _singular(word: str) -> str:
    word = word.lower()
    for ending, replacement in (('ies', 'y'), ('oes', 'o'), ('es', 'e'), ('s', '')):
        if word.endswith(ending) and len(word) > len(ending) + 2:
            return word[: -len(ending)] + replacement
    return word


def _countries(db) -> list[str]:
    return sorted({(row.name or '').strip() for row in db.query(models.CommercialCountry) if (row.name or '').strip()}, key=len, reverse=True)


def _mentions(request: str, names: list[str]) -> list[tuple[int, str, str]]:
    """(position, country, preceding word) for each country named in the request."""
    found, taken = [], []
    for name in names:
        for match in re.finditer(re.escape(name), request, re.IGNORECASE):
            if any(start <= match.start() < end for start, end in taken):
                continue
            taken.append((match.start(), match.end()))
            before = re.findall(r'[A-Za-z]+', request[: match.start()])[-1:]
            found.append((match.start(), name, (before[0] if before else '').lower()))
    return sorted(found)


def _product(db, request: str, exclude: list[str]) -> tuple[str, str | None] | None:
    """(product word, its most common HS code) from the cache of classified product names."""
    text = request
    for name in exclude:
        text = re.sub(re.escape(name), ' ', text, flags=re.IGNORECASE)
    words = [word for word in re.findall(r'[A-Za-z]{4,}', text) if word.lower() not in STOP]
    best = None
    for word in sorted(set(words), key=len, reverse=True):
        stem = _singular(word)
        rows = db.query(models.ProductHsCode).filter(models.ProductHsCode.product_key.like(f'%{stem}%'), models.ProductHsCode.hs_code.isnot(None)).all()
        rows = [row for row in rows if stem in row.product_key.lower()]
        if rows:
            code = Counter(row.hs_code for row in rows).most_common(1)[0][0]
            if best is None or len(rows) > best[2]:
                best = (word, code, len(rows))
    return (best[0], best[1]) if best else (words[0], None) if words else None


def _source_price(db, origin: str | None, destination: str, product: str) -> float | None:
    """USD/kg of the product in the origin country, from the saved Market Opportunities (median of matches)."""
    query = db.query(models.MarketOpportunityComparison).filter(
        models.MarketOpportunityComparison.target_country == destination,
        models.MarketOpportunityComparison.product_name.ilike(f'%{_singular(product)}%'),
        models.MarketOpportunityComparison.source_price_normalized.isnot(None),
    )
    if origin:
        query = query.filter(models.MarketOpportunityComparison.source_country == origin)
    prices = sorted(row.source_price_normalized for row in query)
    return prices[len(prices) // 2] if prices else None


def detect(request: str, selected_country: str) -> dict | None:
    """The destination/origin/product of an import-tax question, or None if the request isn't one
    (a tax-on-opportunities request is the PDF report, handled elsewhere)."""
    if not (TAX_WORDS.search(request) and IMPORT_WORDS.search(request)) or re.search(r'opportunit', request, re.IGNORECASE):
        return None
    with SessionLocal() as db:
        names = _countries(db)
        mentions = _mentions(request, names)
        destination = next((name for _, name, before in mentions if before in ('to', 'into', 'in', 'for')), None)
        origin = next((name for _, name, before in mentions if before == 'from'), None)
        if destination is None:
            others = [name for _, name, _ in mentions if name != origin]
            destination = others[0] if others else selected_country
        product = _product(db, request, [name for _, name, _ in mentions])
        if not product:
            return None
        word, hs_code = product
        price = _source_price(db, origin, destination, word)
    return {'destination': destination, 'origin': origin, 'product': word, 'hs_code': hs_code, 'source_price': price}


def _pct(value) -> str:
    return 'none found' if value is None else f'{value:g}%'


def facts(info: dict, rates: dict | None, rows: list[dict]) -> str:
    """The FACTS block the model writes its answer from (everything numeric is computed here)."""
    lines = [
        f"Question: import taxes on {info['product']} ({'HS ' + info['hs_code'] if info['hs_code'] else 'HS code unknown'}) "
        f"from {info['origin'] or 'any origin'} into {info['destination']}. Taxes below are those charged by {info['destination']} at import.",
    ]
    if rows:
        lines.append('Tariff rows found in the documents for this HS code:')
        lines += [f"- {row['text']}" for row in rows]
    if not rates or rates['total_pct'] is None:
        lines.append(f"The rate of import taxes on this product was NOT found in {info['destination']}'s documents.")
        return '\n'.join(lines)
    duty, stamp, vat, other = (rates[key] or 0 for key in ('duty_pct', 'stamp_duty_pct', 'vat_pct', 'other_pct'))
    lines.append(
        f"Rates read from the documents: import duty {_pct(rates['duty_pct'])}; additional stamp duty {_pct(rates['stamp_duty_pct'])}; "
        f"consumption tax/VAT {_pct(rates['vat_pct'])}; other levies {_pct(rates['other_pct'])}" + (f" ({rates['other_note']})" if rates['other_note'] else '') + '.'
    )
    # Assumption (stated in the answer): duty, stamp duty and levies on the customs value; the consumption tax on value + duty + stamp duty + levies.
    per_usd = {
        'import duty': duty / 100,
        'additional stamp duty': stamp / 100,
        'other levies': other / 100,
    }
    per_usd['consumption tax/VAT'] = (1 + sum(per_usd.values())) * vat / 100
    total = sum(per_usd.values())
    lines.append(f'Computed per USD 1.00 of customs value: ' + '; '.join(f'{name} USD {amount:.4f}' for name, amount in per_usd.items() if amount) + f'; TOTAL taxes USD {total:.4f} ({total * 100:.1f}% of the customs value).')
    price = info['source_price']
    if price is not None:
        lines.append(
            f"Customs value used: USD {price:.2f}/kg ({info['origin'] or 'source'} price from our Market Opportunities, not including freight or insurance). "
            f"Computed taxes per kg: " + '; '.join(f'{name} USD {amount * price:.3f}' for name, amount in per_usd.items() if amount) + f'; TOTAL USD {total * price:.3f} per kg.'
        )
    else:
        lines.append('We have no saved price for this product from the origin, so no USD-per-kg figure can be given; give the rates and the cost per USD 1.00 of value, and say that a per-kg figure needs the customs value (price + freight + insurance) per kg.')
    lines.append(
        'ANSWER FORMAT: first one or two sentences answering the question directly (the total tax rate, and the USD per kg if a customs value is given). Then a short list of each tax and its rate. '
        'Then one line on the assumptions (value base, how the consumption tax is applied) and that the documents, not official customs, are the source. Use the numbers above exactly; do not recompute.'
    )
    return '\n'.join(lines)


def prepare(request: str, selected_country: str, cancel) -> dict | None:
    """Everything the chat answer needs, or None when the request isn't an import-tax question.
    Raises ValueError (message shown to the user) when the destination's documents aren't baked."""
    info = detect(request, selected_country)
    if not info:
        return None
    from ..rag_files import store

    destination = info['destination']
    if not store.baked_path(destination).exists():
        raise ValueError(f"The question is about importing into {destination}, but {destination} has no baked documents yet — Load and Bake its files in RAG Files first.")
    chunks = tax_report._own_chunks(destination)
    product = {'product_name': info['product'], 'hs_code': info['hs_code']}
    passages = tax_report.evidence(destination, chunks, product)
    rows = tax_report.hs_rows(chunks, info['hs_code']) if info['hs_code'] else []
    info['passages'] = passages
    info['rows'] = rows
    return info
