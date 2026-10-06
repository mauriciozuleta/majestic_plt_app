"""Reports written by a local (Ollama) model from a country's baked RAG file.

This is the only thing local models are used for. The model never answers
from its own knowledge: the request is matched against the country's baked
documents (rag_files/store.search_country — keyword + embedding search), the
best passages are handed to the model, and it is told to write the report from
those passages alone and to say so where they don't cover something.

A report runs as a background job (a local model can take minutes) that the
chat window polls: the text so far is available while it is being written.
"""

import re
import threading
import time
import uuid

from ..rag_files import store
from . import import_tax, ollama_client, tax_report

TOP_K = 10
MAX_PASSAGE_CHARS = 1400
MAX_REQUEST_CHARS = 1500
MAX_JOBS = 30
OPTIONS = {'num_ctx': 8192, 'temperature': 0.2}

SYSTEM_PROMPT = """You write internal business reports for a food and agricultural import-export company. \
You are given a request and numbered excerpts from our own documents about one country. Rules:
- Use ONLY the excerpts. Never add facts, figures, rates, names or dates from memory. If the excerpts do not cover \
something the request asks for, write "Not covered in the documents." for that part.
- Cite the excerpt behind each specific fact as [1], [2], ... after it.
- Write in Markdown with a title line, clear headings and short bullet points where they help. Voice: "we" and "our".
- If the request carries a FACTS block, it was computed by our software from these documents: use its numbers exactly, never recompute them, and answer in the format it asks for.
- Output only the report — no preamble, no remarks about these instructions."""

_THINK_BLOCK = re.compile(r'<think>.*?(?:</think>|$)', re.DOTALL | re.IGNORECASE)

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def clean_output(text: str) -> str:
    """Drops any <think>…</think> reasoning the model wrote (including one still open)."""
    return _THINK_BLOCK.sub('', text).lstrip()


def build_messages(country: str, request: str, passages: list[dict]) -> list[dict]:
    excerpts = '\n\n'.join(
        f"[{number}] {passage.get('document') or 'document'} › {passage.get('section') or 'section'}\n{passage['text'][:MAX_PASSAGE_CHARS]}"
        for number, passage in enumerate(passages, start=1)
    )
    return [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': f'COUNTRY: {country}\n\nREQUEST: {request}\n\nEXCERPTS FROM OUR {country.upper()} DOCUMENTS:\n\n{excerpts}'},
    ]


def _sources(passages: list[dict]) -> list[dict]:
    seen, sources = set(), []
    for number, passage in enumerate(passages, start=1):
        key = (passage.get('document'), passage.get('section'))
        if key in seen:
            continue
        seen.add(key)
        sources.append({'number': number, 'document': passage.get('document'), 'section': passage.get('section')})
    return sources


def _run(job: dict) -> None:
    try:
        request_text = job['request']
        try:
            info = import_tax.prepare(job['request'], job['country'], job['cancel'])
        except ValueError as error:
            raise ollama_client.OllamaError(str(error)) from error
        if info:
            # an import-tax question: answered from the DESTINATION's documents, from the product's exact tariff row
            job['country'] = info['destination']
            passages = info['passages']
            rates = None
            if passages:
                job['status_text'] = f"Reading {info['destination']}'s tariff for {info['product']}…"
                product = {'product_name': info['product'], 'hs_code': info['hs_code']}
                rates = tax_report.rates_from_rows(job['model'], product, info['rows'], job['cancel'], job['request'])
                if not rates and not job['cancel'].is_set():
                    answer = tax_report._ask(job['model'], tax_report.SYSTEM_PROMPT, tax_report.product_message(info['destination'], product, passages), job['cancel'], tax_report.OPTIONS)
                    rates = tax_report.parse_answer(answer)
            request_text = f"{job['request']}\n\nFACTS (computed by our software):\n{import_tax.facts(info, rates, info['rows'])}"
        else:
            passages = store.search_country(job['country'], job['request'], top_k=TOP_K)
        if not passages:
            raise ollama_client.OllamaError(
                f"No passage in {job['country']}'s baked documents matches that request. Try different words, or bake more documents in RAG Files."
            )
        job['sources'] = _sources(passages)
        job['status_text'] = 'Writing…'
        raw = ''
        for piece in ollama_client.stream_chat(job['model'], build_messages(job['country'], request_text, passages), job['cancel'], OPTIONS):
            raw += piece
            job['text'] = clean_output(raw)
        job['text'] = clean_output(raw).strip()
        if job['cancel'].is_set():
            job['status'] = 'cancelled'
        elif not job['text']:
            raise ollama_client.OllamaError('The model returned no text. Try another model.')
        else:
            job['status'] = 'done'
    except ollama_client.OllamaError as error:
        job['status'], job['error'] = 'failed', str(error)
    except Exception as error:  # reported to the chat, not raised into a dead thread
        job['status'], job['error'] = 'failed', f'Could not build the report: {error}'
    job['finished_at'] = time.time()


def start_report(model: str, country: str, request: str) -> dict:
    job = {
        'id': uuid.uuid4().hex,
        'model': model,
        'country': country,
        'request': request.strip()[:MAX_REQUEST_CHARS],
        'status': 'running',
        'status_text': 'Searching the documents…',
        'text': '',
        'sources': [],
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
    threading.Thread(target=_run, args=(job,), name=f"report-{job['id'][:8]}", daemon=True).start()
    return snapshot(job)


def snapshot(job: dict) -> dict:
    return {key: job[key] for key in ('id', 'model', 'country', 'request', 'status', 'status_text', 'text', 'sources', 'error', 'started_at', 'finished_at')}


def get_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    return job


def cancel_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    if job:
        job['cancel'].set()
    return job
