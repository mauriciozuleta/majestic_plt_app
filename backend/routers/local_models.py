"""Local models (Ollama) in the chat window — for building reports from a
country's baked RAG files, and nothing else. See local_models/reports.py."""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..local_models import ollama_client, reports, tax_report
from ..rag_files import store
from .rag_files import _country

router = APIRouter()


class ReportIn(BaseModel):
    model: str
    country: str
    request: str


class SavedReportIn(BaseModel):
    country: str
    model: str
    request: str
    text: str


@router.get('/local-models')
def list_local_models(refresh: bool = False):
    """The installed Ollama models that can write text, or why none are available."""
    try:
        return {'available': True, 'base_url': ollama_client.base_url(), 'models': ollama_client.list_models(force=refresh), 'detail': None}
    except ollama_client.OllamaError as error:
        return {'available': False, 'base_url': ollama_client.base_url(), 'models': [], 'detail': str(error)}


@router.post('/local-models/report')
def start_report(payload: ReportIn, db: Session = Depends(get_db)):
    if not payload.request.strip():
        raise HTTPException(status_code=400, detail='Describe the report you want.')
    country = _country(db, payload.country)
    if not store.baked_path(country).exists():
        raise HTTPException(status_code=400, detail=f'{country} has no baked documents yet — Load and Bake its files in RAG Files first.')
    try:
        installed = {model['name'] for model in ollama_client.list_models()}
    except ollama_client.OllamaError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if payload.model not in installed:
        raise HTTPException(status_code=400, detail=f'The model "{payload.model}" is not installed in Ollama.')
    return reports.start_report(payload.model, country, payload.request)


@router.post('/local-models/reports/save')
def save_report(payload: SavedReportIn, db: Session = Depends(get_db)):
    """Saves a built report as a Markdown file in the country's `reports`
    folder (next to its `source`, `json` and RAG file — not among the
    documents it is built from)."""
    country = _country(db, payload.country)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='There is no report to save.')
    folder = store.country_dir(country) / 'reports'
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    slug = re.sub(r'[^a-z0-9]+', '-', payload.request.lower()).strip('-')[:40] or 'report'
    path = folder / f'{now:%Y-%m-%d_%H%M%S} {slug}.md'
    request_line = ' '.join(payload.request.split())[:300]
    header = f'<!-- Built by {payload.model} on {now:%Y-%m-%d %H:%M} UTC from the baked documents of {country}. Request: {request_line} -->\n\n'
    path.write_text(header + text + '\n', encoding='utf-8')
    return {'file': path.name, 'folder': f'backend/documents/rag_files/{folder.parent.name}/reports'}


@router.get('/local-models/report/{job_id}')
def get_report(job_id: str):
    job = reports.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Report not found (the server restarted?).')
    return reports.snapshot(job)


@router.post('/local-models/report/{job_id}/cancel')
def cancel_report(job_id: str):
    job = reports.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Report not found.')
    return reports.snapshot(job)


class TaxReportIn(BaseModel):
    model: str
    country: str
    rating: str = 'Very High'
    limit: int | None = None


@router.post('/local-models/tax-report')
def start_tax_report(payload: TaxReportIn, db: Session = Depends(get_db)):
    """Starts the tax-cost PDF for a country's opportunities of one rating (see local_models/tax_report.py)."""
    country = _country(db, payload.country)
    if not store.baked_path(country).exists():
        raise HTTPException(status_code=400, detail=f'{country} has no baked documents yet — Load and Bake its files in RAG Files first.')
    try:
        installed = {model['name'] for model in ollama_client.list_models()}
    except ollama_client.OllamaError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if payload.model not in installed:
        raise HTTPException(status_code=400, detail=f'The model "{payload.model}" is not installed in Ollama.')
    return tax_report.start(payload.model, country, payload.rating, payload.limit)


@router.get('/local-models/tax-report/{job_id}')
def get_tax_report(job_id: str):
    job = tax_report.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Report not found (the server restarted?).')
    return tax_report.snapshot(job)


@router.post('/local-models/tax-report/{job_id}/cancel')
def cancel_tax_report(job_id: str):
    job = tax_report.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Report not found.')
    return tax_report.snapshot(job)


@router.get('/local-models/tax-report/{job_id}/pdf')
def tax_report_pdf(job_id: str):
    job = tax_report.get_job(job_id)
    if not job or job['status'] != 'done' or not job['file']:
        raise HTTPException(status_code=404, detail='The PDF is not ready.')
    path = store.country_dir(job['country']) / 'reports' / job['file']
    if not path.exists():
        raise HTTPException(status_code=404, detail='The PDF file is no longer in the reports folder.')
    return FileResponse(path, media_type='application/pdf', filename=path.name)


@router.get('/local-models/reports/file')
def report_file(country: str, file: str, db: Session = Depends(get_db)):
    """A saved report (PDF or Markdown) from the country's `reports` folder."""
    country = _country(db, country)
    folder = (store.country_dir(country) / 'reports').resolve()
    path = (folder / file).resolve()
    if path.parent != folder or path.suffix.lower() not in ('.pdf', '.md') or not path.exists():
        raise HTTPException(status_code=404, detail='That report is no longer in the reports folder.')
    return FileResponse(path, media_type='application/pdf' if path.suffix.lower() == '.pdf' else 'text/markdown', filename=path.name)
