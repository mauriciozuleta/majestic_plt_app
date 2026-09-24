"""The Assistant chat window's brain. A plain server-side Claude call (same
key/model as knowledge_base/claude_client.py) with tools, so the model can
look things up in the knowledge base itself instead of being handed one
pre-retrieved batch: search the shared knowledge base (uploaded documents and
every generated report), list the portfolio's countries, and request a
Country Commercial Profile or Competitiveness Analysis build.

Builds aren't run here. Competitiveness needs the source country's product
summary, which only the frontend can assemble (see
src/services/competitivenessInputs.js), and the frontend already knows how to
run a build as a background job that reports back into this same chat — so a
build tool just validates and returns an "action" that the chat window
executes with the existing code path.
"""

import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..knowledge_base import rag
from ..knowledge_base.claude_client import ANTHROPIC_API_URL, ANTHROPIC_VERSION, MODEL
from . import product_sources
from .country_profile import PROFILES_DIR
from .knowledge_base import _knowledge_base_document_ids

router = APIRouter()

MAX_TOKENS = 2000
MAX_TOOL_ROUNDS = 6
MAX_HISTORY = 16

SYSTEM_PROMPT = """You are the assistant built into a multi-company portfolio app for a food/agricultural \
import-export business. You can consult the shared knowledge base (the client's own uploaded documents, such as \
their business plan, plus every commercial profile, competitiveness analysis and risk plan already generated) and \
you can start new reports.

How to work:
- For any question about the client's plans, companies, markets, products or existing reports, call \
search_knowledge_base first and answer from what it returns. Search more than once with different wording if the \
first results are thin. Say which document each fact came from. If the documents don't contain the answer, say so \
plainly — never invent details about the client's business.
- To build a Country Commercial Profile: call list_countries to find the country's id, then \
build_country_profile. The build takes a couple of minutes and uses the uploaded documents as its basis; tell the \
user it has started and that a message will appear here when it's ready.
- To build a Competitiveness Analysis (how a source country's products would compete in a target country): the \
target country needs a profile already, and the source country needs product data (Colombia, United States, and any \
country given a source in Settings). Call list_countries, then build_competitiveness_analysis. If the target has no profile, offer \
to build that first.
- To update a product-price source (the ones added in Settings ▸ Product analysis sources — a government market-price \
site, for example): call list_product_sources to find its id, then refresh_product_source. This re-reads the site right \
now, in a few seconds, not a background job — report back the new product count, or the reason it couldn't be read \
(some sites need a file loaded instead, which only Settings can do). A source with no web address can't be refreshed \
this way; say so rather than trying.
- Only start a build when the user actually asks for one.
- Be concise and plain-spoken. No markdown headings; short paragraphs or simple lists are fine."""

TOOLS = [
    {
        'name': 'search_knowledge_base',
        'description': 'Semantic + keyword search over the shared knowledge base: uploaded documents (business plan, etc.) '
        'and generated reports. Returns the best-matching passages with the document each came from.',
        'input_schema': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'What to look for, in natural language.'}},
            'required': ['query'],
        },
    },
    {
        'name': 'list_countries',
        'description': 'Every commercial country set up in the portfolio, with its company, its id, and whether a '
        'Country Commercial Profile has already been built for it.',
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'build_country_profile',
        'description': 'Start building a Country Commercial Profile for a country (get the id from list_countries). '
        'Runs in the background, uses the uploaded documents as its basis.',
        'input_schema': {
            'type': 'object',
            'properties': {'country_id': {'type': 'string'}},
            'required': ['country_id'],
        },
    },
    {
        'name': 'build_competitiveness_analysis',
        'description': "Start building a Competitiveness Analysis: how the source country's product portfolio would "
        "compete if sold into the target country. The target (get its id from list_countries) must already have a "
        "profile. source_country_name is a country name such as 'Colombia' or 'United States'.",
        'input_schema': {
            'type': 'object',
            'properties': {'target_country_id': {'type': 'string'}, 'source_country_name': {'type': 'string'}},
            'required': ['target_country_id', 'source_country_name'],
        },
    },
    {
        'name': 'list_product_sources',
        'description': "Every product-price source added in Settings ▸ Product analysis sources (not the built-in "
        "Colombia/USA pipelines, which aren't updated this way) — its id, name, country, web address, status and "
        "how many products it currently holds.",
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'refresh_product_source',
        'description': 'Re-read a product-price source\'s website right now (get its id from list_product_sources) '
        'and replace its products with what it finds. Only works for a source that has a web address; one that '
        "relies on a loaded file can't be refreshed this way.",
        'input_schema': {
            'type': 'object',
            'properties': {'source_id': {'type': 'string'}},
            'required': ['source_id'],
        },
    },
]

# Colombia and the USA have built-in pipelines; any other country needs a
# source added in Settings (see competitivenessInputs.js). Anything else would
# fail in the frontend anyway, so say so up front instead of after a
# "started" message.
BUILT_IN_PRODUCT_COUNTRIES = {'colombia', 'united states'}


def _countries_with_product_data(db: Session) -> set[str]:
    custom = db.query(models.ProductSource.country_name).filter(models.ProductSource.product_count > 0).all()
    return BUILT_IN_PRODUCT_COUNTRIES | {name.strip().lower() for (name,) in custom}


class ChatTurn(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    messages: list[ChatTurn]


def _api_key() -> str | None:
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _country_rows(db: Session) -> list[dict]:
    companies = {company.id: company.name for company in db.query(models.Company).all()}
    return [
        {
            'country_id': country.id,
            'country': country.name,
            'company_id': country.company_id,
            'company': companies.get(country.company_id, ''),
            'has_profile': (PROFILES_DIR / f'{country.id}.md').exists(),
        }
        for country in db.query(models.CommercialCountry).all()
    ]


def _run_tool(db: Session, name: str, args: dict, sources: dict, actions: list) -> str:
    if name == 'search_knowledge_base':
        query = str(args.get('query', '')).strip()
        if not query:
            return 'Empty query.'
        hits = rag.search(_knowledge_base_document_ids(db), query, 6)
        if not hits:
            return 'No matching passages. The knowledge base may be empty, or nothing in it covers this.'
        for hit in hits:
            sources[hit['doc_name']] = sources.get(hit['doc_name'], 0) + 1
        return '\n\n'.join(f'[{hit["doc_name"]} — part {hit["chunk_index"] + 1}]\n{hit["text"]}' for hit in hits)

    if name == 'list_countries':
        return json.dumps(_country_rows(db)) or '[]'

    if name == 'build_country_profile':
        country = next((row for row in _country_rows(db) if row['country_id'] == args.get('country_id')), None)
        if not country:
            return 'No such country id. Call list_countries first.'
        actions.append(
            {
                'type': 'build_country_profile',
                'company_id': country['company_id'],
                'country_id': country['country_id'],
                'country_name': country['country'],
            }
        )
        return f'Build started for {country["country"]} ({country["company"]}). It takes a couple of minutes.'

    if name == 'build_competitiveness_analysis':
        target = next((row for row in _country_rows(db) if row['country_id'] == args.get('target_country_id')), None)
        source_name = str(args.get('source_country_name', '')).strip()
        if not target:
            return 'No such target country id. Call list_countries first.'
        if not target['has_profile']:
            return f'{target["country"]} has no Country Commercial Profile yet — it needs one before it can be a benchmark target.'
        available = _countries_with_product_data(db)
        if source_name.lower() not in available:
            return (
                f'No product data exists for "{source_name}". Countries with product data: '
                + ', '.join(sorted(name.title() for name in available))
                + '. More can be added in Settings > Product analysis sources.'
            )
        actions.append(
            {
                'type': 'build_competitiveness',
                'company_id': target['company_id'],
                'target_country_id': target['country_id'],
                'target_country_name': target['country'],
                'source_country_name': source_name,
            }
        )
        return f'Analysis started: {source_name} → {target["country"]}. It takes a couple of minutes.'

    if name == 'list_product_sources':
        rows = db.query(models.ProductSource).order_by(models.ProductSource.country_name, models.ProductSource.created_at).all()
        return json.dumps([product_sources._serialize(row) for row in rows]) or '[]'

    if name == 'refresh_product_source':
        source_id = str(args.get('source_id', '')).strip()
        row = db.query(models.ProductSource).filter_by(id=source_id).first()
        if not row:
            return 'No such product source id. Call list_product_sources first.'
        if not row.url:
            return f'"{row.name}" has no web address, so it can only be updated by loading a file in Settings — not from here.'
        product_sources._analyze(db, row)
        db.commit()
        if row.status == 'ok':
            return f'Refreshed "{row.name}" ({row.country_name}): {row.product_count} products. {row.status_message or ""}'.strip()
        return f'Could not refresh "{row.name}" ({row.country_name}): {row.status_message}'

    return f'Unknown tool {name}.'


def _clean_history(turns: list[ChatTurn]) -> list[dict]:
    """Claude wants strictly alternating turns starting with the user; the
    chat log also holds background-job notices (assistant-side) that can sit
    back to back, so merge same-role neighbours and drop a leading assistant
    message."""
    merged: list[dict] = []
    for turn in turns[-MAX_HISTORY:]:
        role = 'user' if turn.role == 'user' else 'assistant'
        text = turn.text.strip()
        if not text:
            continue
        if merged and merged[-1]['role'] == role:
            merged[-1]['content'] += f'\n\n{text}'
        else:
            merged.append({'role': role, 'content': text})
    while merged and merged[0]['role'] != 'user':
        merged.pop(0)
    return merged


@router.post('/assistant/chat')
def assistant_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    api_key = _api_key()
    if not api_key:
        raise HTTPException(status_code=502, detail='No Claude API key is configured on the server (CLAUDE_API_KEY).')

    messages = _clean_history(payload.messages)
    if not messages or messages[-1]['role'] != 'user':
        raise HTTPException(status_code=400, detail='Send a message first.')

    sources: dict[str, int] = {}
    actions: list[dict] = []
    headers = {'x-api-key': api_key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'}

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = httpx.post(
                ANTHROPIC_API_URL,
                headers=headers,
                json={'model': MODEL, 'max_tokens': MAX_TOKENS, 'system': SYSTEM_PROMPT, 'tools': TOOLS, 'messages': messages},
                timeout=90,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f'The Claude API request failed: {error}') from error

        content = response.json().get('content', [])
        tool_calls = [block for block in content if block.get('type') == 'tool_use']
        if not tool_calls:
            reply = '\n\n'.join(block.get('text', '').strip() for block in content if block.get('type') == 'text').strip()
            return {'reply': reply or 'I had nothing to add.', 'sources': list(sources), 'actions': actions}

        messages.append({'role': 'assistant', 'content': content})
        results = [
            {
                'type': 'tool_result',
                'tool_use_id': call['id'],
                'content': _run_tool(db, call['name'], call.get('input') or {}, sources, actions),
            }
            for call in tool_calls
        ]
        messages.append({'role': 'user', 'content': results})

    return {
        'reply': 'That took more steps than I can do in one go — try asking a narrower question.',
        'sources': list(sources),
        'actions': actions,
    }
