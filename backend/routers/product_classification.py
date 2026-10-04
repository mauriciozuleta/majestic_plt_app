"""Assigns our own wholesale products a real UN Comtrade HS code — what the
General Portfolio Directory's product code is built from (see
backend/comtrade/product_classification.py for how). Global, not scoped to
Global Trade Data's own UI, but built on that module's classification
reference — the same official code and description a product gets here is
exactly what Global Trade Data itself would show for that HS code.

Same "runs as a real background task, tracked via a marker file" pattern as
weight_research.py — classifying a batch of new product names means several
sequential Claude calls (grounded to each product's own shortlist) and can
take minutes; tying that to the request/response cycle timed out a plain
client in testing (5+ minutes for ~500 new names) well before it finished,
and would do the same to the browser. GET is always instant (a table read);
POST only ever starts the slow work in the background.
"""

import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends
from sqlalchemy.orm import Session

from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..comtrade.product_classification import get_cached, run_classification_job
from ..database import SessionLocal, get_db

router = APIRouter()

JOB_MARKER_PATH = Path(__file__).resolve().parent.parent / 'comtrade' / '_classification_job.marker'
# Checking for a running job and claiming the marker happen together, so two
# callers can't both start one.
_start_lock = threading.Lock()
WAIT_SECONDS = 5
WAIT_LIMIT_SECONDS = 30 * 60


def _run(items: list[dict]) -> None:
    try:
        run_classification_job(items)
    except Exception as exc:
        mark_error(JOB_MARKER_PATH, str(exc))
    finally:
        clear_building(JOB_MARKER_PATH)


@router.get('/api/product-hs-codes')
def list_product_hs_codes(db: Session = Depends(get_db)):
    """Every product classified so far — {key: {hs_code, description} |
    null} — plus whether a classification job is currently running. Always
    instant; never waits on Claude."""
    return {'building': is_building(JOB_MARKER_PATH), 'error': get_error(JOB_MARKER_PATH), 'results': get_cached(db)}


@router.post('/api/product-hs-codes')
def start_product_classification(
    products: list[dict] = Body(..., description="[{key, name}] — key is the caller's own lookup key, name is what to classify."),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Starts classifying whatever in `products` isn't already cached, in
    the background — returns immediately either way. Callers that need the
    result should GET afterward (immediately for what's already cached, or
    once `building` goes back to false for what was just queued) rather
    than wait on this call."""
    with _start_lock:
        if is_building(JOB_MARKER_PATH):
            return {'status': 'already_building'}
        cached = get_cached(db)
        to_classify = [p for p in products if p['key'] not in cached]
        if not to_classify:
            return {'status': 'no_items'}
        mark_building(JOB_MARKER_PATH)
    background_tasks.add_task(_run, to_classify)
    return {'status': 'started', 'item_count': len(to_classify)}


def classify_source_products_in_background(products: list[dict], country: str) -> None:
    """Queues a product source's products ({name, category}) for HS
    classification as soon as they're stored (a supermarket catalog, a file,
    a web page), so their real HS-based portfolio codes are ready before
    anyone opens the portfolio — instead of the portfolio's placeholder codes
    until it's opened and classification catches up. Same key and context
    the portfolio itself sends (productPortfolio.js): the lowercased name,
    and "<category>; sold in <country>". Waits for a classification job
    that's already running rather than skipping these products."""
    items = {}
    for product in products:
        name = (product.get('name') or '').strip()
        if name:
            items.setdefault(name.lower(), {'key': name.lower(), 'name': name, 'context': f"{product.get('category') or 'Uncategorized'}; sold in {country}"})
    if items:
        threading.Thread(target=_classify_when_free, args=(list(items.values()),), name='hs-classify-source', daemon=True).start()


def _classify_when_free(items: list[dict]) -> None:
    deadline = time.monotonic() + WAIT_LIMIT_SECONDS
    while True:
        with _start_lock:
            if not is_building(JOB_MARKER_PATH):
                db = SessionLocal()
                try:
                    cached = get_cached(db)
                finally:
                    db.close()
                to_classify = [item for item in items if item['key'] not in cached]
                if not to_classify:
                    return
                mark_building(JOB_MARKER_PATH)
                break
        if time.monotonic() > deadline:
            return  # the portfolio will still queue them when it's opened
        time.sleep(WAIT_SECONDS)
    _run(to_classify)
