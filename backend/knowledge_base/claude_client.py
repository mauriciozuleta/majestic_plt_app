"""Answers a question from retrieved knowledge-base chunks. Same plain
server-side Claude call as risk_analysis/claude_client.py (key from
CLAUDE_API_KEY / claude_api_key in .env, never sent to the browser) — the
model is told to answer only from the numbered sources it's given, so an
answer can always be traced back to a document.
"""

import os

import httpx

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-5'
MAX_TOKENS = 1500


class KnowledgeBaseAnswerError(Exception):
    pass


def _get_api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def answer_question(question: str, sources: list[dict]) -> str:
    api_key = _get_api_key()
    if not api_key:
        raise KnowledgeBaseAnswerError('No Claude API key is configured on the server (CLAUDE_API_KEY).')

    source_blocks = '\n\n'.join(
        f'[{number}] {source["doc_name"]} (part {source["chunk_index"] + 1})\n{source["text"]}'
        for number, source in enumerate(sources, start=1)
    )
    prompt = f"""Answer the question using ONLY the numbered sources below, which come from this company's \
own documents. Cite the sources you used inline as [1], [2], etc. If the sources don't contain the answer, say \
so plainly instead of guessing.

Sources:
{source_blocks}

Question: {question}"""

    try:
        response = httpx.post(
            ANTHROPIC_API_URL,
            headers={'x-api-key': api_key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'},
            json={'model': MODEL, 'max_tokens': MAX_TOKENS, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=90,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise KnowledgeBaseAnswerError(f'The Claude API request failed: {error}') from error

    text = '\n\n'.join(
        block.get('text', '').strip() for block in response.json().get('content', []) if block.get('type') == 'text'
    ).strip()
    if not text:
        raise KnowledgeBaseAnswerError('Claude returned an empty answer.')
    return text
