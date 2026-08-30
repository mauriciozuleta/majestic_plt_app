import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Capture
from .schemas import CaptureCreate, CaptureRead

Base.metadata.create_all(bind=engine)

app = FastAPI(title='Price Capture API')

# Local-only tool: allow extension origins during development.
# This should be restricted before any non-local deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.post('/capture', response_model=CaptureRead, status_code=status.HTTP_201_CREATED)
def create_capture(payload: CaptureCreate, db: Session = Depends(get_db)):
    capture = Capture(
        domain=payload.domain,
        product_name=payload.product_name,
        price=str(payload.price),
        unit=payload.unit,
        country=payload.country,
        supermarket_name=payload.supermarket_name,
        currency=payload.currency,
        captured_at=payload.captured_at,
        created_at=datetime.now(timezone.utc),
    )
    db.add(capture)
    db.commit()
    db.refresh(capture)
    return capture


@app.get('/captures', response_model=list[CaptureRead])
def list_captures(
    domain: str | None = None,
    country: str | None = None,
    supermarket_name: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Capture)

    if domain:
        query = query.filter(Capture.domain == domain)
    if country:
        query = query.filter(Capture.country == country)
    if supermarket_name:
        query = query.filter(Capture.supermarket_name == supermarket_name)

    return query.order_by(Capture.created_at.desc()).all()


@app.get('/captures/{capture_id}', response_model=CaptureRead)
def get_capture(capture_id: int, db: Session = Depends(get_db)):
    capture = db.query(Capture).filter(Capture.id == capture_id).first()
    if not capture:
        raise HTTPException(status_code=404, detail='Capture not found')
    return capture


@app.delete('/captures/{capture_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(capture_id: int, db: Session = Depends(get_db)):
    capture = db.query(Capture).filter(Capture.id == capture_id).first()
    if not capture:
        raise HTTPException(status_code=404, detail='Capture not found')

    db.delete(capture)
    db.commit()
    return None


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    import uvicorn

    uvicorn.run('price_capture_backend.main:app', host='0.0.0.0', port=port, reload=True)
