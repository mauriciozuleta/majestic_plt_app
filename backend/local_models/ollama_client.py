"""Talks to a local Ollama server (https://ollama.com) — the machine's own
language models, run offline. Majestic uses them for one thing only: building
reports from a country's baked RAG files (see reports.py). Nothing here
touches Claude or the internet.

The server address is OLLAMA_HOST (default http://127.0.0.1:11434).
"""

import json
import os
import time

import httpx

TIMEOUT = httpx.Timeout(connect=5, read=300, write=30, pool=5)
MODELS_TTL_SECONDS = 20

_cache: dict = {'at': 0.0, 'models': []}
_capabilities: dict[str, list[str]] = {}


class OllamaError(Exception):
    """A user-presentable reason a local-model call failed."""


def base_url() -> str:
    host = (os.environ.get('OLLAMA_HOST') or 'http://127.0.0.1:11434').strip()
    if not host.startswith(('http://', 'https://')):
        host = 'http://' + host
    return host.replace('0.0.0.0', '127.0.0.1').rstrip('/')


UNAVAILABLE = "Ollama isn't running. Start the Ollama app (or run `ollama serve`), then try again."


def _get(path: str, **kwargs) -> dict:
    try:
        response = httpx.get(f'{base_url()}{path}', timeout=httpx.Timeout(5, read=15), **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError as error:
        raise OllamaError(UNAVAILABLE) from error
    except httpx.HTTPError as error:
        raise OllamaError(f'Ollama returned an error: {error}') from error


def capabilities(model: str) -> list[str]:
    """What a model can do (completion, embedding, thinking, vision, tools),
    cached; an older Ollama that doesn't report it gives []."""
    if model not in _capabilities:
        try:
            response = httpx.post(f'{base_url()}/api/show', json={'model': model}, timeout=httpx.Timeout(5, read=15))
            _capabilities[model] = list(response.json().get('capabilities') or []) if response.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return []
    return _capabilities[model]


def list_models(force: bool = False) -> list[dict]:
    """The installed models that can write text — embedding-only models (e.g.
    nomic-embed-text) are left out. Raises OllamaError if the server is down."""
    if not force and time.monotonic() - _cache['at'] < MODELS_TTL_SECONDS and _cache['models']:
        return _cache['models']
    models = []
    for item in _get('/api/tags').get('models', []):
        name = item.get('name') or item.get('model')
        if not name:
            continue
        caps = capabilities(name)
        if caps and 'completion' not in caps:
            continue
        if not caps and 'embed' in name.lower():
            continue
        details = item.get('details') or {}
        models.append(
            {
                'name': name,
                'size_bytes': item.get('size'),
                'parameter_size': details.get('parameter_size'),
                'family': details.get('family'),
                'quantization': details.get('quantization_level'),
                'vision': 'vision' in caps,
                'thinking': 'thinking' in caps,
            }
        )
    models.sort(key=lambda model: (model['size_bytes'] or 0, model['name']))
    _cache.update(at=time.monotonic(), models=models)
    return models


def stream_chat(model: str, messages: list[dict], cancel, options: dict | None = None, think: bool = False):
    """Yields the reply's text as it is written. `cancel` is a threading.Event
    that stops it. Reasoning models are told not to think out loud (it only
    delays the first word) and any <think> block left in the text is the
    caller's to strip."""
    payload = {'model': model, 'messages': messages, 'stream': True, 'options': options or {}}
    if 'thinking' in capabilities(model):
        payload['think'] = think  # True: the model reasons first (slower); only its final answer is yielded
    try:
        with httpx.stream('POST', f'{base_url()}/api/chat', json=payload, timeout=TIMEOUT) as response:
            if response.status_code != 200:
                body = response.read().decode('utf-8', errors='replace')
                try:
                    detail = json.loads(body).get('error') or body
                except ValueError:
                    detail = body
                if response.status_code == 404:
                    raise OllamaError(f'The model "{model}" is not installed. Run `ollama pull {model}` or pick another one.')
                raise OllamaError(f'Ollama said: {detail.strip()[:300]}')
            for line in response.iter_lines():
                if cancel.is_set():
                    return
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get('error'):
                    raise OllamaError(f"Ollama said: {chunk['error']}")
                piece = (chunk.get('message') or {}).get('content') or ''
                if piece:
                    yield piece
                if chunk.get('done'):
                    return
    except httpx.ConnectError as error:
        raise OllamaError(UNAVAILABLE) from error
    except httpx.ReadTimeout as error:
        raise OllamaError('The model stopped answering (no output for 5 minutes).') from error
    except httpx.HTTPError as error:
        raise OllamaError(f'Could not reach Ollama: {error}') from error
