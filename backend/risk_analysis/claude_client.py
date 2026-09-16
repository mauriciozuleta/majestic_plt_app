"""Generate Plan — turns a category's well-managed risks (see
risk_scoring.py for what "well managed" means) into an investor-friendly
narrative: how each risk could affect the company, and how the mechanisms
already in place compensate for it. Deliberately excludes any risk that
isn't well managed yet — the point of this document is to show investors
risk is being handled, not to air every gap. No web search needed here (this
writes from data already in the database, not live research), so this is a
plain single-turn completion, unlike country_profile's web-search-backed
client.

The API key is read server-side only, from CLAUDE_API_KEY (or the
lowercase `claude_api_key`, however it's actually named in .env).
"""

import os
import re

import httpx

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-5'
MAX_TOKENS = 4000


def _get_api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _build_prompt(company_name, category_name, risks):
    risk_blocks = []
    for risk in risks:
        mechanisms_text = '\n'.join(
            f'  - {m["name"]}: {m["description"] or "(no further detail on file)"}' for m in risk['mechanisms']
        )
        risk_blocks.append(
            f'- Risk: {risk["name"]}\n'
            f'  Why it matters: {risk["description"] or "(no further detail on file)"}\n'
            f'  Mechanisms in place:\n{mechanisms_text}'
        )
    risks_text = '\n'.join(risk_blocks)

    return f"""You are writing a short section of an investor-facing risk report for {company_name}, covering \
its "{category_name}" risk category. The risks below have already been assessed internally and confirmed as \
well-managed — every one of them has real mitigation mechanisms in place. Your job is to explain this clearly \
to someone outside the company (an investor, a lender, a board member) who has no internal context.

For each risk, in plain business language (no internal jargon, no reference to internal scoring scales or \
letter grades):
1. Explain what the risk is and how it could affect the company if left unmanaged.
2. Explain how the mechanisms already in place compensate for it, and why that's credible.

Be specific and grounded in the details given — do not invent facts beyond what's provided, but you may explain \
their business implications in plain terms. Keep an confident, factual tone; this is meant to build trust, not \
oversell.

Write a Markdown document titled "# {category_name} Risk Management — {company_name}" with one "## " subsection \
per risk (using the risk's own name as the heading), each 2-4 short paragraphs. Do not include a preamble, \
introduction, or closing summary — output only the title and the per-risk sections.

Risks and their mechanisms:
{risks_text}
"""


def _join_text_blocks(content_blocks):
    pieces = []
    for block in content_blocks:
        if block.get('type') != 'text':
            continue
        text = block.get('text', '').strip()
        if text:
            pieces.append(text)
    return '\n\n'.join(pieces).strip()


def _strip_preamble(body):
    match = re.search(r'^# .+$', body, re.MULTILINE)
    return body[match.start():] if match else body


def generate_risk_plan(company_name, category_name, risks):
    """risks: list of {name, description, mechanisms: [{name, description}]}
    — already filtered to well-managed ones by the caller."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'messages': [{'role': 'user', 'content': _build_prompt(company_name, category_name, risks)}],
    }
    headers = {
        'x-api-key': api_key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }

    response = httpx.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    data = response.json()
    if data.get('stop_reason') == 'max_tokens':
        raise RuntimeError("Claude's response was cut off before finishing. Try again with fewer risks, or raise the token budget.")

    body = _join_text_blocks(data.get('content', []))
    body = _strip_preamble(body)
    if not body:
        raise RuntimeError('Claude returned no text content for the plan')
    return body
