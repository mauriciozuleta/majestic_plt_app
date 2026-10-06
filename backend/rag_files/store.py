"""Per-country document folders for the RAG Files module.

Each country gets a folder named after it under documents/rag_files/:

    <Country>/source/<file>            the files as added (any supported format)
    <Country>/json/<name>.json         "Load": each file converted to JSON (convert.py)
    <Country>/<Country>.rag.json       "Bake": every loaded document chunked and
                                       embedded into the country's one RAG file
    <Country>/state.json               bookkeeping (hashes, load errors)

A file is **uploaded** until it is loaded, **loaded** once its JSON exists, and
**baked** once its JSON is in the country's RAG file. Baking is incremental:
documents already baked (same JSON) keep their chunks and embeddings; new or
changed ones are embedded; removed ones are dropped.

The RAG file has the shape of the knowledge base's own (`doc_id`, `name`,
`chunks[{index, text, embedding}]`, see knowledge_base/rag.py), plus
`documents` and, per chunk, the `document` and `section` it came from — so
knowledge_base.rag.search can query it directly.
"""

import hashlib
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..knowledge_base import embed, rag
from .convert import SUPPORTED_EXTENSIONS, UNSUPPORTED_HINTS, ConversionError, convert_file, file_sha256

ROOT = Path(__file__).resolve().parent.parent / 'documents' / 'rag_files'
MAX_FILE_BYTES = 50 * 1024 * 1024
_STATE_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(text: str) -> str:
    """A file or folder name that is safe on Windows: no path separators or
    reserved characters, no trailing dots/spaces."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip().strip('.')
    return cleaned or 'file'


def country_dir(country: str) -> Path:
    return ROOT / safe_name(country)


def source_dir(country: str) -> Path:
    return country_dir(country) / 'source'


def json_dir(country: str) -> Path:
    return country_dir(country) / 'json'


def baked_path(country: str) -> Path:
    return country_dir(country) / f'{safe_name(country)}.rag.json'


def _state_path(country: str) -> Path:
    return country_dir(country) / 'state.json'


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, **({} if compact else {'indent': 2})), encoding='utf-8')
    temp.replace(path)


def _state(country: str) -> dict:
    state = _read_json(_state_path(country), {})
    for key in ('files', 'loaded', 'errors'):
        state.setdefault(key, {})
    return state


def _save_state(country: str, state: dict) -> None:
    _write_json(_state_path(country), state)


def _sync_files(country: str, state: dict) -> None:
    """Registers files that were put in the source folder by hand and
    forgets ones that are gone."""
    folder = source_dir(country)
    present = {path.name: path for path in folder.iterdir() if path.is_file()} if folder.exists() else {}
    for name in list(state['files']):
        if name not in present:
            del state['files'][name]
            state['loaded'].pop(name, None)
            state['errors'].pop(name, None)
    for name, path in present.items():
        info = state['files'].get(name)
        if info is None or info.get('size') != path.stat().st_size:
            state['files'][name] = {'sha256': file_sha256(path), 'size': path.stat().st_size, 'uploaded_at': _now()}


# ---------------------------------------------------------------- status


def _meta_path(country: str) -> Path:
    return country_dir(country) / 'bake.json'


def baked_meta(country: str) -> dict:
    """{baked_at, embedding_model, chunk_count, documents[]} of the country's RAG
    file, from the small `bake.json` written at every bake. A RAG file baked
    before that existed is read once and its sidecar created."""
    meta = _read_json(_meta_path(country), None)
    if meta is not None:
        return meta
    path = baked_path(country)
    if not path.exists():
        return {}
    data = _read_json(path, {})
    meta = {
        'baked_at': data.get('baked_at'),
        'embedding_model': data.get('embedding_model'),
        'chunk_count': len(data.get('chunks', [])),
        'documents': data.get('documents', []),
    }
    _write_json(_meta_path(country), meta)
    return meta


def _baked_documents(country: str) -> dict:
    return {doc['file']: doc for doc in baked_meta(country).get('documents', [])}


def file_status(name: str, state: dict, baked: dict) -> str:
    info = state['files'].get(name, {})
    loaded = state['loaded'].get(name)
    if loaded and loaded.get('source_sha256') == info.get('sha256'):
        baked_doc = baked.get(name)
        return 'baked' if baked_doc and baked_doc.get('json_sha256') == loaded.get('json_sha256') else 'loaded'
    if name in state['errors'] and state['errors'][name].get('source_sha256') == info.get('sha256'):
        return 'error'
    return 'uploaded'


def country_summary(country: str, with_files: bool = False) -> dict:
    """Counts for the country's card (and, with `with_files`, each file)."""
    with _STATE_LOCK:
        state = _state(country) if country_dir(country).exists() else {'files': {}, 'loaded': {}, 'errors': {}}
        if country_dir(country).exists():
            _sync_files(country, state)
            _save_state(country, state)
    baked = _baked_documents(country)
    files = []
    for name, info in sorted(state['files'].items(), key=lambda item: item[0].lower()):
        status = file_status(name, state, baked)
        loaded = state['loaded'].get(name, {}) if status in ('loaded', 'baked') else {}
        files.append(
            {
                'name': name,
                'format': Path(name).suffix.lower().lstrip('.'),
                'size_bytes': info.get('size', 0),
                'uploaded_at': info.get('uploaded_at'),
                'status': status,
                'error': state['errors'].get(name, {}).get('error') if status == 'error' else None,
                'sections': loaded.get('sections'),
                'characters': loaded.get('characters'),
                'loaded_at': loaded.get('loaded_at'),
                'warnings': loaded.get('warnings', []),
            }
        )
    counts = {key: sum(1 for item in files if item['status'] == key) for key in ('uploaded', 'loaded', 'baked', 'error')}
    stale = [name for name in baked if name not in state['files'] or file_status(name, state, baked) not in ('baked',)]
    meta = baked_meta(country)
    summary = {
        'country': country,
        'files': len(files),
        **counts,
        # something loaded isn't in the RAG file yet, or a baked document was removed/changed
        'needs_bake': counts['loaded'] > 0 or bool(stale),
        'baked_at': meta.get('baked_at'),
        'chunk_count': meta.get('chunk_count', 0),
        'embedded': bool(meta.get('embedding_model')),
    }
    if with_files:
        summary['file_list'] = files
    return summary


# ---------------------------------------------------------------- files


def validate_filename(filename: str) -> str:
    name = safe_name(Path(filename).name)
    suffix = Path(name).suffix.lower()
    if suffix in UNSUPPORTED_HINTS:
        raise ConversionError(UNSUPPORTED_HINTS[suffix])
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ConversionError('Use PDF, Word (.docx), Excel (.xlsx/.xls), CSV, Markdown or text files.')
    return name


def save_upload(country: str, filename: str, data: bytes) -> dict:
    name = validate_filename(filename)
    if not data:
        raise ConversionError('The file is empty.')
    if len(data) > MAX_FILE_BYTES:
        raise ConversionError(f'Files are limited to {MAX_FILE_BYTES // (1024 * 1024)} MB.')
    folder = source_dir(country)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    with _STATE_LOCK:
        state = _state(country)
        previous = state['files'].get(name)
        if previous is None or previous.get('sha256') != sha:
            # new content: it must be loaded (and baked) again
            state['loaded'].pop(name, None)
            state['errors'].pop(name, None)
        state['files'][name] = {'sha256': sha, 'size': len(data), 'uploaded_at': _now()}
        _save_state(country, state)
    return {'name': name}


def delete_file(country: str, name: str) -> bool:
    name = safe_name(Path(name).name)
    path = source_dir(country) / name
    existed = path.exists()
    path.unlink(missing_ok=True)
    with _STATE_LOCK:
        state = _state(country)
        loaded = state['loaded'].pop(name, None)
        state['files'].pop(name, None)
        state['errors'].pop(name, None)
        _save_state(country, state)
    if loaded and loaded.get('json'):
        (json_dir(country) / loaded['json']).unlink(missing_ok=True)
    return existed


def read_document(country: str, name: str) -> dict | None:
    state = _state(country)
    loaded = state['loaded'].get(safe_name(Path(name).name))
    if not loaded:
        return None
    return _read_json(json_dir(country) / loaded['json'], None)


# ---------------------------------------------------------------- queue
#
# Every Load and Bake goes through one queue with one worker thread, so any
# number of countries can be queued and they run one after another. Running
# them side by side would not be faster (the embedding model already uses
# several cores) and made the whole app crawl.

MAX_FINISHED_JOBS = 40
EMBED_BATCH = 32

_QUEUE = threading.Condition()
_JOBS: list[dict] = []  # oldest first: queued, running and recently finished
_worker_started = False


class Cancelled(Exception):
    """Raised inside a job when the user cancels it."""


def _active(job: dict) -> bool:
    return job['status'] in ('queued', 'running')


def _public(job: dict, queue: list[dict] | None = None) -> dict:
    waiting = [other for other in (queue if queue is not None else _JOBS) if other['status'] == 'queued']
    public = {key: job[key] for key in ('id', 'country', 'kind', 'status', 'message', 'done', 'total', 'error', 'queued_at', 'started_at', 'finished_at')}
    public['position'] = (waiting.index(job) + 1) if job in waiting else 0  # 0 = running or finished; n = n-th in line
    return public


def enqueue(country: str, kind: str) -> dict:
    """Queues a 'load' or 'bake' for the country. If the same job is already
    queued or running it is returned instead of a second one."""
    global _worker_started
    with _QUEUE:
        for job in _JOBS:
            if job['country'] == country and job['kind'] == kind and _active(job):
                return _public(job)
        job = {
            'id': uuid.uuid4().hex, 'country': country, 'kind': kind, 'status': 'queued', 'message': 'Waiting in the queue…',
            'done': 0, 'total': 0, 'error': None, 'queued_at': _now(), 'started_at': None, 'finished_at': None, 'cancel': threading.Event(),
        }
        _JOBS.append(job)
        finished = [other for other in _JOBS if not _active(other)]
        for stale in finished[: max(0, len(finished) - MAX_FINISHED_JOBS)]:
            _JOBS.remove(stale)
        if not _worker_started:
            _worker_started = True
            threading.Thread(target=_worker, name='rag-files-worker', daemon=True).start()
        _QUEUE.notify()
        return _public(job)


def _worker() -> None:
    while True:
        with _QUEUE:
            job = next((item for item in _JOBS if item['status'] == 'queued'), None)
            while job is None:
                _QUEUE.wait()
                job = next((item for item in _JOBS if item['status'] == 'queued'), None)
            job.update(status='running', started_at=_now(), message='Starting…')

        def progress(done: int, total: int, message: str, job=job) -> None:
            job.update(done=done, total=total, message=message)

        try:
            work = load_country if job['kind'] == 'load' else bake_country
            message = work(job['country'], progress, job['cancel'])
            job.update(status='done', message=message or 'Done.')
        except Cancelled:
            job.update(status='cancelled', message='Cancelled.')
        except Exception as error:  # reported through the job, never kills the worker
            job.update(status='failed', error=str(error), message=str(error))
        job['finished_at'] = _now()


def cancel_job(job_id: str) -> dict | None:
    """A queued job is dropped at once; a running one stops at its next step."""
    with _QUEUE:
        for job in _JOBS:
            if job['id'] == job_id and _active(job):
                if job['status'] == 'queued':
                    job.update(status='cancelled', message='Cancelled.', finished_at=_now())
                else:
                    job['cancel'].set()
                    job['message'] = 'Cancelling…'
                return _public(job)
    return None


def queue_snapshot() -> dict:
    """The running and queued jobs (running first, in line order) plus the most recent finished ones."""
    with _QUEUE:
        active = [job for job in _JOBS if _active(job)]
        active.sort(key=lambda job: (job['status'] != 'running', job['queued_at']))
        recent = [job for job in reversed(_JOBS) if not _active(job)][:8]
        return {'active': [_public(job) for job in active], 'recent': [_public(job) for job in recent]}


def job_status(country: str) -> dict | None:
    """The country's current job (running, else queued), else its latest finished one."""
    with _QUEUE:
        mine = [job for job in _JOBS if job['country'] == country]
        for wanted in ('running', 'queued'):
            job = next((item for item in mine if item['status'] == wanted), None)
            if job:
                return _public(job)
        return _public(mine[-1]) if mine else None


# ---------------------------------------------------------------- load


def _json_name(country: str, name: str, state: dict) -> str:
    stem = Path(name).stem
    taken = {info.get('json') for other, info in state['loaded'].items() if other != name}
    candidate = f'{stem}.json'
    return candidate if candidate not in taken else f'{stem}-{Path(name).suffix.lstrip(".").lower()}.json'


def load_country(country: str, progress, cancel) -> str:
    """Converts every file that isn't loaded yet into JSON in the country's json folder."""
    with _STATE_LOCK:
        state = _state(country)
        _sync_files(country, state)
        _save_state(country, state)
    baked = _baked_documents(country)
    todo = [name for name in state['files'] if file_status(name, state, baked) in ('uploaded', 'error')]
    if not todo:
        return 'Nothing to load — every file is already converted.'
    converted = failed = 0
    for index, name in enumerate(todo, start=1):
        if cancel.is_set():
            raise Cancelled()
        progress(index - 1, len(todo), f'Converting {name} ({index} of {len(todo)})…')
        path = source_dir(country) / name
        try:
            document = convert_file(path, country)
            with _STATE_LOCK:
                state = _state(country)
                json_name = _json_name(country, name, state)
                _write_json(json_dir(country) / json_name, document)
                state['loaded'][name] = {
                    'json': json_name,
                    'source_sha256': state['files'][name]['sha256'],
                    'json_sha256': file_sha256(json_dir(country) / json_name),
                    'sections': document['stats']['sections'],
                    'characters': document['stats']['characters'],
                    'warnings': document['warnings'],
                    'loaded_at': _now(),
                }
                state['errors'].pop(name, None)
                _save_state(country, state)
            converted += 1
        except ConversionError as error:
            failed += 1
            with _STATE_LOCK:
                state = _state(country)
                state['errors'][name] = {'error': str(error), 'source_sha256': state['files'].get(name, {}).get('sha256'), 'at': _now()}
                state['loaded'].pop(name, None)
                _save_state(country, state)
        except Exception as error:
            failed += 1
            with _STATE_LOCK:
                state = _state(country)
                state['errors'][name] = {'error': f'Unexpected error: {error}', 'source_sha256': state['files'].get(name, {}).get('sha256'), 'at': _now()}
                _save_state(country, state)
    progress(len(todo), len(todo), 'Done.')
    return f'Converted {converted} file{"" if converted == 1 else "s"}' + (f'; {failed} could not be converted.' if failed else '.')


# ---------------------------------------------------------------- bake


def _document_chunks(document: dict, file_name: str) -> list[dict]:
    chunks = []
    for section in document.get('sections', []):
        heading = section.get('path') or section.get('title') or ''
        for piece in rag.chunk_text(section.get('content', '')):
            chunks.append({'text': f'{heading}\n\n{piece}' if heading else piece, 'document': file_name, 'section': heading})
    return chunks


def _commit_bake(country: str, documents: list[dict], chunks: list[dict], embedded: bool) -> None:
    """Writes the RAG file and its sidecar. Done after every document, so a
    cancelled or interrupted bake keeps what it already finished."""
    for number, chunk in enumerate(chunks):
        chunk['index'] = number
    baked_at = _now()
    model = embed.MODEL_ID if embedded and all(chunk.get('embedding') for chunk in chunks) else None
    _write_json(
        baked_path(country),
        {
            'doc_id': f'rag-files:{safe_name(country).lower()}',
            'name': f'{country} documents',
            'source': 'rag_files',
            'country': country,
            'baked_at': baked_at,
            'embedding_model': model,
            'documents': documents,
            'chunks': chunks,
        },
        compact=True,
    )
    _write_json(_meta_path(country), {'baked_at': baked_at, 'embedding_model': model, 'chunk_count': len(chunks), 'documents': documents})


def _duration(seconds: float) -> str:
    if seconds < 90:
        return f'{max(1, round(seconds))} s'
    return f'{round(seconds / 60)} min'


def bake_country(country: str, progress, cancel) -> str:
    """Updates the country's RAG file with the loaded documents it doesn't
    contain yet (and drops the ones that were removed or changed). Embeds in
    batches, reporting chunk progress and an estimate, and commits after each
    document."""
    with _STATE_LOCK:
        state = _state(country)
        _sync_files(country, state)
        _save_state(country, state)
    existing = _read_json(baked_path(country), {})
    baked_docs = {doc['file']: doc for doc in existing.get('documents', [])}
    wanted = {name: state['loaded'][name] for name in state['files'] if state['loaded'].get(name, {}).get('source_sha256') == state['files'][name]['sha256']}

    keep = {name for name, doc in baked_docs.items() if name in wanted and doc.get('json_sha256') == wanted[name].get('json_sha256')}
    chunks = [chunk for chunk in existing.get('chunks', []) if chunk.get('document') in keep]
    documents = [doc for name, doc in baked_docs.items() if name in keep]
    todo = [name for name in wanted if name not in keep]
    removed = [name for name in baked_docs if name not in wanted]
    embedding_ok = embed.is_available()
    # chunks from an earlier bake without the embedding model get their vectors now
    repair = [chunk for chunk in chunks if embedding_ok and not chunk.get('embedding')]
    if not todo and not removed and not repair:
        return 'The RAG file is already up to date.'

    pending = []
    for name in todo:
        document = _read_json(json_dir(country) / wanted[name]['json'], None)
        if document:
            pending.append((name, _document_chunks(document, name)))
    total = sum(len(new) for _, new in pending) + len(repair)
    done = 0
    started = time.monotonic()

    def embed_batches(items: list[dict], label: str) -> None:
        nonlocal done
        for start in range(0, len(items), EMBED_BATCH):
            if cancel.is_set():
                raise Cancelled()
            batch = items[start: start + EMBED_BATCH]
            for chunk, vector in zip(batch, embed.embed_texts([chunk['text'] for chunk in batch])):
                chunk['embedding'] = embed.encode_vector(vector)
            done += len(batch)
            elapsed = time.monotonic() - started
            left = (total - done) * elapsed / done if done else 0
            progress(done, total, f'{label} — {done:,} of {total:,} chunks' + (f' · about {_duration(left)} left' if left > 5 else ''))

    if repair:
        embed_batches(repair, 'Embedding earlier chunks')
    for name, new_chunks in pending:
        if embedding_ok:
            embed_batches(new_chunks, f'Embedding {name}')
        else:
            done += len(new_chunks)
        documents.append({'file': name, 'json': wanted[name]['json'], 'json_sha256': wanted[name]['json_sha256'], 'chunks': len(new_chunks), 'baked_at': _now()})
        chunks.extend(new_chunks)
        _commit_bake(country, documents, chunks, embedding_ok)
    if not pending:
        _commit_bake(country, documents, chunks, embedding_ok)
    progress(total, total, 'Done.')
    added = f'added {len(pending)} document{"" if len(pending) == 1 else "s"}' if pending else ''
    dropped = f'removed {len(removed)}' if removed else ''
    note = '' if embedding_ok else ' (embedding model unavailable — keyword search only)'
    return f'Baked {len(chunks):,} chunks: {", ".join(part for part in (added, dropped) if part) or "refreshed"}.{note}'


def search_country(country: str, query: str, top_k: int = 6) -> list[dict]:
    path = baked_path(country)
    if not path.exists():
        return []
    results = rag.search([path], query, top_k=top_k)
    chunks = {chunk['index']: chunk for chunk in _read_json(path, {}).get('chunks', [])}
    for result in results:
        chunk = chunks.get(result['chunk_index'], {})
        result['document'] = chunk.get('document')
        result['section'] = chunk.get('section')
    return results
