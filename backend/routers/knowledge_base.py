"""Documentation uploads and the portfolio-wide knowledge base.

One shared library for the whole portfolio (not per company): a business
plan uploaded once is the basis for every company's commercial profiles and
competitiveness analyses (see knowledge_base/context.py). Two folders under
backend/documents/: uploads/ (files that were only uploaded, for people to
consult/download) and knowledge_base/ (files that were also turned into a
RAG index — see knowledge_base/rag.py — plus every generated report,
mirrored in automatically). Files travel as base64 JSON rather than
multipart so this needs no extra dependency.
"""

import base64
import binascii
import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..knowledge_base import rag
from ..knowledge_base.claude_client import KnowledgeBaseAnswerError, answer_question
from .competitiveness import ANALYSES_DIR, TITLE_LINE
from .country_profile import PROFILES_DIR
from .risk_analysis import PLANS_DIR

router = APIRouter()


class DocumentUpload(BaseModel):
    filename: str
    content_base64: str
    add_to_knowledge_base: bool = False


class KnowledgeQuery(BaseModel):
    query: str
    top_k: int = 6


class KnowledgeQuestion(BaseModel):
    question: str


def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename.replace('\\', '/')).strip()
    name = re.sub(r'[^\w.\- ()]+', '_', name)
    return name or 'document'


def _serialize(document: models.KnowledgeDocument) -> dict:
    return {
        'id': document.id,
        'name': document.name,
        'original_filename': document.original_filename,
        'size_bytes': document.size_bytes,
        'uploaded_at': document.uploaded_at,
        'source': document.source,
        'in_knowledge_base': document.in_knowledge_base,
        'chunk_count': document.chunk_count,
    }


def _stored_path(document: models.KnowledgeDocument) -> Path:
    root = rag.KNOWLEDGE_BASE_DIR if document.in_knowledge_base else rag.UPLOADS_DIR
    return rag.ensure_dir(root) / document.stored_name


def _index(document: models.KnowledgeDocument) -> None:
    """(Re)builds this document's RAG file from its stored copy."""
    text = rag.extract_text(_stored_path(document))
    document.chunk_count = rag.build_rag_file(document.id, document.name, document.source, text)


def _ensure_rag_files(db: Session) -> None:
    """A .rag.json is derived data — if one is missing (deleted by hand, or
    a fresh checkout) it's rebuilt from the stored file instead of leaving
    the document silently unsearchable."""
    changed = False
    for document in db.query(models.KnowledgeDocument).filter_by(in_knowledge_base=True):
        if rag.rag_path(document.id).exists() or not _stored_path(document).exists():
            continue
        try:
            _index(document)
            changed = True
        except ValueError:
            continue
    if changed:
        db.commit()


# ------------------------------------------------------- generated reports


def _report_sources(db: Session):
    """(report_key, display name, owning company id, source path) for every
    generated report in the portfolio. Country reports are keyed by country
    CODE (plus company) rather than country id, so rebuilding the commercial
    structure — which issues new ids — doesn't make a report look brand new."""
    companies = {company.id: company.name for company in db.query(models.Company).all()}
    countries = db.query(models.CommercialCountry).all()
    countries_by_id = {country.id: country for country in countries}

    for country in countries:
        path = PROFILES_DIR / f'{country.id}.md'
        if path.exists():
            owner = companies.get(country.company_id, '')
            key = f'country_profile:{country.company_id}:{country.country_code or country.id}'
            yield key, f'{country.name} — Commercial Profile ({owner})', country.company_id, path

    if ANALYSES_DIR.exists():
        for path in sorted(ANALYSES_DIR.glob('*.md')):
            target = countries_by_id.get(path.stem.split('__', 1)[0])
            if not target:
                continue
            title_match = TITLE_LINE.search(path.read_text(encoding='utf-8'))
            source_slug = path.stem.split('__', 1)[-1]
            source_name = title_match.group(1) if title_match else source_slug
            owner = companies.get(target.company_id, '')
            key = f'competitiveness:{target.company_id}:{target.country_code or target.id}__{source_slug}'
            yield key, f'{source_name} → {target.name} — Competitiveness ({owner})', target.company_id, path

    for category in db.query(models.RiskCategory).all():
        path = PLANS_DIR / f'{category.id}.md'
        if path.exists():
            owner = companies.get(category.company_id, '')
            yield f'risk_plan:{category.id}', f'Risk plan — {category.name} ({owner})', category.company_id, path


def sync_reports(db: Session) -> None:
    """Mirrors every generated report into the knowledge base folder and
    indexes it. Cheap enough to run on every list/search (a handful of small
    markdown files, skipped unless their content changed), which is what
    keeps a report built a minute ago from missing from the knowledge base
    without needing a hook in each report generator."""
    existing = {
        document.report_key: document for document in db.query(models.KnowledgeDocument).filter_by(source='report')
    }
    kb_dir = rag.ensure_dir(rag.KNOWLEDGE_BASE_DIR)
    changed = False

    for report_key, name, owner_id, source_path in _report_sources(db):
        content = source_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        document = existing.get(report_key)

        if document and document.content_hash == content_hash and rag.rag_path(document.id).exists():
            if document.name != name:
                document.name = name
                changed = True
            continue

        if not document:
            doc_id = str(uuid.uuid4())
            document = models.KnowledgeDocument(
                id=doc_id,
                related_company_id=owner_id,
                name=name,
                original_filename=f'{_safe_filename(name)}.md',
                stored_name=f'{doc_id}.md',
                uploaded_at=datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc).isoformat(),
                source='report',
                report_key=report_key,
                in_knowledge_base=True,
            )
            db.add(document)
            existing[report_key] = document
        else:
            document.name = name
            document.uploaded_at = datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc).isoformat()

        (kb_dir / document.stored_name).write_bytes(content)
        document.size_bytes = len(content)
        document.content_hash = content_hash
        document.chunk_count = rag.build_rag_file(document.id, name, 'report', content.decode('utf-8', errors='replace'))
        changed = True

    if changed:
        db.commit()


# ---------------------------------------------------------------- endpoints


@router.get('/documents')
def list_documents(db: Session = Depends(get_db)):
    sync_reports(db)
    _ensure_rag_files(db)
    documents = db.query(models.KnowledgeDocument).order_by(models.KnowledgeDocument.uploaded_at.desc()).all()
    return [_serialize(document) for document in documents]


@router.post('/documents')
def upload_document(payload: DocumentUpload, db: Session = Depends(get_db)):
    safe_name = _safe_filename(payload.filename)
    extension = Path(safe_name).suffix.lower()
    if extension in rag.BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f'"{extension}" files cannot be uploaded.')
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail='The file data was not valid.') from error
    if not content:
        raise HTTPException(status_code=400, detail='The file is empty.')
    if len(content) > rag.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f'Files are limited to {rag.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.')

    doc_id = str(uuid.uuid4())
    document = models.KnowledgeDocument(
        id=doc_id,
        name=Path(safe_name).stem,
        original_filename=safe_name,
        stored_name=f'{doc_id}_{safe_name}',
        size_bytes=len(content),
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        source='upload',
        in_knowledge_base=payload.add_to_knowledge_base,
    )
    path = _stored_path(document)
    path.write_bytes(content)

    if payload.add_to_knowledge_base:
        # Extract before committing anything: a file that can't be read must
        # fail the whole upload with a clear reason rather than land in the
        # knowledge base folder half-indexed.
        try:
            _index(document)
        except ValueError as error:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(error)) from error

    db.add(document)
    db.commit()
    return _serialize(document)


def _get_document(db: Session, document_id: str) -> models.KnowledgeDocument:
    document = db.query(models.KnowledgeDocument).filter_by(id=document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail='Document not found')
    return document


@router.get('/documents/{document_id}/download')
def download_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    path = _stored_path(document)
    if not path.exists():
        raise HTTPException(status_code=404, detail='The stored file is missing.')
    return FileResponse(path, filename=document.original_filename)


@router.post('/documents/{document_id}/add-to-knowledge-base')
def add_to_knowledge_base(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    if document.in_knowledge_base:
        return _serialize(document)

    old_path = _stored_path(document)
    # Read it where it is now; only move it into the knowledge base folder
    # once it's known to be readable.
    try:
        text = rag.extract_text(old_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    document.in_knowledge_base = True
    new_path = _stored_path(document)
    shutil.move(str(old_path), str(new_path))
    document.chunk_count = rag.build_rag_file(document.id, document.name, document.source, text)
    db.commit()
    return _serialize(document)


@router.delete('/documents/{document_id}')
def delete_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    if document.source == 'report':
        raise HTTPException(
            status_code=400,
            detail='Generated reports are added to the knowledge base automatically — delete the report itself instead.',
        )
    _stored_path(document).unlink(missing_ok=True)
    rag.delete_rag_file(document.id)
    db.delete(document)
    db.commit()
    return {'ok': True}


def _knowledge_base_document_ids(db: Session) -> list[str]:
    sync_reports(db)
    _ensure_rag_files(db)
    return [document.id for document in db.query(models.KnowledgeDocument).filter_by(in_knowledge_base=True)]


@router.post('/knowledge-base/search')
def search_knowledge_base(payload: KnowledgeQuery, db: Session = Depends(get_db)):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail='Enter something to search for.')
    return rag.search(_knowledge_base_document_ids(db), payload.query, max(1, min(payload.top_k, 20)))


@router.post('/knowledge-base/ask')
def ask_knowledge_base(payload: KnowledgeQuestion, db: Session = Depends(get_db)):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail='Enter a question.')
    sources = rag.search(_knowledge_base_document_ids(db), payload.question, 6)
    if not sources:
        return {'answer': 'Nothing in the knowledge base matches that question yet.', 'sources': []}
    try:
        answer = answer_question(payload.question, sources)
    except KnowledgeBaseAnswerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        'answer': answer,
        'sources': [
            {'number': number, 'doc_name': source['doc_name'], 'chunk_index': source['chunk_index'], 'text': source['text']}
            for number, source in enumerate(sources, start=1)
        ],
    }
