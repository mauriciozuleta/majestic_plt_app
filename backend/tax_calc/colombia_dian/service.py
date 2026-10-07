"""The tax-calculator service: a registry of country providers behind one `lookup`, with the cache, shared in-flight runs, a batch mode
and background jobs (progress is polled by the UI — the same pattern as the RAG Files queue).

    taxCalculator.lookup(TaxLookupRequest(country="CO", hsCode=…, date=…)) -> routes to the registered provider (DianProvider for CO)
"""

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from .cache import TariffCache, is_cacheable
from .dian_types import DianError, ProgressEvent, TaxLookupRequest
from .parsers import normalize_hs_code
from .provider import DianProvider, today_local

log = logging.getLogger('dian')

MAX_BATCH_CONCURRENCY = 2


class TaxCalculatorService:
    def __init__(self, cache: TariffCache | None = None):
        self._providers: dict[str, object] = {}
        self._cache = cache
        self._inflight: dict[tuple, Future] = {}
        self._lock = threading.Lock()

    @property
    def cache(self) -> TariffCache:
        if self._cache is None:
            self._cache = TariffCache()
        return self._cache

    def register(self, provider) -> None:
        self._providers[provider.countryCode.upper()] = provider

    def provider(self, country: str):
        found = self._providers.get((country or '').strip().upper())
        if found is None:
            raise KeyError(country)
        return found

    # ------------------------------------------------------------------ one lookup

    def lookup(self, req: TaxLookupRequest) -> dict:
        provider = self.provider(req.country)
        try:
            code = normalize_hs_code(req.hsCode)
        except DianError as error:
            return error.to_result()
        today = today_local()
        # DIAN only answers for today: a cached result is valid for today's key
        if not req.forceRefresh:
            hit = self._from_cache(code, today)
            if hit is not None:
                return hit
        key = (req.country.upper(), code, today)
        with self._lock:
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        if not owner:  # an identical lookup is already running: share its answer
            log.info('[DIAN] joining the in-flight lookup of %s', code)
            return future.result()
        try:
            result, parse_warnings = provider.lookup(TaxLookupRequest(country=req.country, hsCode=code, date=req.date, forceRefresh=req.forceRefresh, debug=req.debug, onProgress=req.onProgress))
            if is_cacheable(result, parse_warnings):
                try:
                    self.cache.put(code, result)
                except Exception:  # noqa: BLE001 — a cache failure must not fail the lookup
                    log.exception('[DIAN] could not write the cache')
            future.set_result(result)
            return result
        except BaseException as error:  # noqa: BLE001
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def _from_cache(self, code: str, today: str) -> dict | None:
        try:
            resolved = self.cache.resolve_alias(code, today) or code
            cached = self.cache.get(resolved, today)
        except Exception:  # noqa: BLE001
            log.exception('[DIAN] could not read the cache')
            return None
        if cached is None:
            return None
        log.info('[DIAN] cache hit for %s', code)
        # what was typed THIS time (the cached payload carries the code of the request that filled the cache)
        return {
            **cached,
            'query': {**cached['query'], 'inputHsCode': code},
            'source': {**cached['source'], 'requestedHsCode': code, 'fromCache': True},
        }

    # ------------------------------------------------------------------ batch

    def lookup_batch(self, country: str, hs_codes: list[str], date: str | None = None, concurrency: int = 1, delay_ms: int = 1500, on_progress=None, force_refresh: bool = False) -> list[dict]:
        """Sequential by default (at most 2 at once), a pause between codes, and a per-code failure never aborts the batch.
        -> [{ hsCode, result }] in input order."""
        concurrency = max(1, min(MAX_BATCH_CONCURRENCY, concurrency))
        total = len(hs_codes)
        results: list[dict | None] = [None] * total

        def one(index: int, code: str):
            if on_progress:
                on_progress(ProgressEvent(step='batch', message=f'{index + 1}/{total} Processing {code}', index=index + 1, total=total))
            try:
                outcome = self.lookup(TaxLookupRequest(country=country, hsCode=code, date=date, forceRefresh=force_refresh))
            except Exception as error:  # noqa: BLE001
                log.exception('[DIAN] batch item failed')
                outcome = {'status': 'error', 'error': {'code': 'DIAN_UNAVAILABLE', 'message': str(error)}}
            results[index] = {'hsCode': code, 'result': outcome}

        if concurrency == 1:
            for index, code in enumerate(hs_codes):
                if index and delay_ms:
                    time.sleep(delay_ms / 1000)  # politeness delay between codes (documented, configurable)
                one(index, code)
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = []
                for index, code in enumerate(hs_codes):
                    if index and delay_ms:
                        time.sleep(delay_ms / 1000)
                    futures.append(pool.submit(one, index, code))
                for future in futures:
                    future.result()
        return [item for item in results if item is not None]


# ---------------------------------------------------------------------- background jobs (polled by the UI)


class JobStore:
    """In-memory jobs: a lookup or a batch running in a background thread, with its progress events. A backend restart drops them."""

    def __init__(self, service: TaxCalculatorService, max_kept: int = 50):
        self._service = service
        self._jobs: dict[str, dict] = {}
        self._max_kept = max_kept
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='dian-job')
        self._lock = threading.Lock()

    def _new_job(self, kind: str) -> dict:
        job = {'id': uuid.uuid4().hex, 'kind': kind, 'status': 'running', 'progress': [], 'result': None, 'startedAt': datetime.now(timezone.utc).isoformat(), 'finishedAt': None}
        with self._lock:
            self._jobs[job['id']] = job
            for old in list(self._jobs)[: max(0, len(self._jobs) - self._max_kept)]:
                self._jobs.pop(old, None)
        return job

    def _finish(self, job: dict, result) -> None:
        job['result'] = result
        job['status'] = 'done'
        job['finishedAt'] = datetime.now(timezone.utc).isoformat()

    def start_lookup(self, country: str, hs_code: str, date: str | None, force_refresh: bool, debug: bool) -> dict:
        job = self._new_job('lookup')

        def run():
            try:
                req = TaxLookupRequest(country=country, hsCode=hs_code, date=date, forceRefresh=force_refresh, debug=debug, onProgress=lambda event: job['progress'].append(event.to_dict()))
                self._finish(job, self._service.lookup(req))
            except Exception as error:  # noqa: BLE001
                log.exception('[DIAN] job failed')
                self._finish(job, {'status': 'error', 'error': {'code': 'DIAN_UNAVAILABLE', 'message': str(error)}})

        self._pool.submit(run)
        return job

    def start_batch(self, country: str, hs_codes: list[str], date: str | None, concurrency: int, delay_ms: int, force_refresh: bool) -> dict:
        job = self._new_job('batch')

        def run():
            try:
                results = self._service.lookup_batch(country, hs_codes, date, concurrency, delay_ms, on_progress=lambda event: job['progress'].append(event.to_dict()), force_refresh=force_refresh)
                self._finish(job, {'status': 'ok', 'results': results})
            except Exception as error:  # noqa: BLE001
                log.exception('[DIAN] batch job failed')
                self._finish(job, {'status': 'error', 'error': {'code': 'DIAN_UNAVAILABLE', 'message': str(error)}})

        self._pool.submit(run)
        return job

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)


# ---------------------------------------------------------------------- the shared instances

service = TaxCalculatorService()
service.register(DianProvider())
jobs = JobStore(service)
