"""Import-tax calculators per country (backend/tax_calc/): find a tariff line, calculate the taxes of an import."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, tax_calc
from ..database import get_db
from ..tax_calc import Inputs, mapping
from ..tax_calc.colombia_dian import import_taxes as dian_import_taxes
from ..tax_calc.colombia_dian.dian_types import TaxLookupRequest
from ..tax_calc.colombia_dian.service import jobs as dian_jobs
from ..tax_calc.colombia_dian.service import service as dian_service

router = APIRouter()


class CalculateIn(BaseModel):
    code: str
    # either the total value of the goods, or price per kg x quantity in kg
    goods_value_usd: float | None = Field(default=None, ge=0)
    price_per_kg_usd: float | None = Field(default=None, ge=0)
    quantity_kg: float | None = Field(default=None, gt=0)
    quantity_units: float | None = Field(default=None, gt=0)  # in the tariff line's own unit, when its duty is per unit
    freight_usd: float = Field(default=0, ge=0)
    insurance_usd: float = Field(default=0, ge=0)
    origin: str | None = None
    transport: str = 'air'
    commercial_importer: bool = False


def _calculator(country: str):
    calculator = tax_calc.get(country)
    if calculator is None:
        raise HTTPException(status_code=404, detail=f'No tax calculator for {country} yet. Available: {", ".join(tax_calc.CALCULATORS)}.')
    return calculator


@router.get('/tax-calc/countries')
def list_countries():
    """The countries that have a calculator, with their tariff data status."""
    return {'countries': [calculator.info() for calculator in tax_calc.CALCULATORS.values()]}


@router.get('/tax-calc/{country}/search')
def search_lines(country: str, q: str, limit: int = 30):
    """Tariff lines matching a product name (words) or a code (digits, any prefix)."""
    calculator = _calculator(country)
    if not calculator.info()['ready']:
        raise HTTPException(status_code=409, detail=f'The {country} tariff data is not loaded yet. Use "Update tariff data".')
    return {'lines': calculator.search(q, min(max(limit, 1), 100))}


@router.post('/tax-calc/{country}/calculate')
def calculate(country: str, payload: CalculateIn):
    calculator = _calculator(country)
    goods = payload.goods_value_usd
    if goods is None and payload.price_per_kg_usd is not None and payload.quantity_kg is not None:
        goods = payload.price_per_kg_usd * payload.quantity_kg
    if goods is None:
        raise HTTPException(status_code=400, detail='Give the value of the goods (goods_value_usd), or price_per_kg_usd and quantity_kg.')
    if payload.transport not in ('air', 'sea'):
        raise HTTPException(status_code=400, detail='transport must be "air" or "sea".')
    inputs = Inputs(
        goods_value_usd=goods,
        quantity_kg=payload.quantity_kg,
        quantity_units=payload.quantity_units,
        freight_usd=payload.freight_usd,
        insurance_usd=payload.insurance_usd,
        origin=payload.origin,
        transport=payload.transport,
        commercial_importer=payload.commercial_importer,
    )
    try:
        return calculator.calculate(payload.code, inputs).to_dict()
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post('/tax-calc/{country}/refresh')
def refresh(country: str):
    """Re-reads / re-downloads the country's tariff data."""
    calculator = _calculator(country)
    try:
        return calculator.refresh()
    except Exception as error:
        raise HTTPException(status_code=502, detail=f'Could not update the {country} tariff data: {error}') from error


# ---------------------------------------------------------------- multipliers for the products of a portfolio


class MultiplierProductIn(BaseModel):
    name: str
    hs_code: str | None = None
    category: str | None = None
    price_usd_kg: float | None = None  # the product's price per kg in USD, when known


class MultipliersIn(BaseModel):
    destination: str
    origin: str
    products: list[MultiplierProductIn]


def _multiplier_out(row: models.ProductTaxMultiplier) -> dict:
    return {
        'product_key': row.product_key,
        'product_name': row.product_name,
        'category': row.category,
        'hs_code': row.hs_code,
        'price_usd_kg': row.price_usd_kg,
        'tariff_code': row.tariff_code,
        'tariff_path': row.tariff_path,
        'tax_multiplier': row.tax_multiplier,
        'landed_multiplier': row.landed_multiplier,
        'status': row.status,
        'method': row.method,
        'note': row.note,
        'detail': json.loads(row.detail_json or '[]'),
        'computed_at': row.computed_at,
    }


@router.post('/tax-calc/multipliers/compute')
def compute_multipliers(payload: MultipliersIn, db: Session = Depends(get_db)):
    """Computes (and stores) the import-tax multiplier of every given product for origin -> destination: all of a portfolio's
    products, whether or not they match a product in the destination market."""
    calculator = _calculator(payload.destination)
    if not calculator.info()['ready']:
        raise HTTPException(status_code=409, detail=f'The {payload.destination} tariff data is not loaded yet.')
    now = datetime.now(timezone.utc).isoformat()
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for product in payload.products:
        key = product.name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        computed = mapping.multiplier_for(calculator, product.model_dump(), payload.origin)
        counts[computed['status']] = counts.get(computed['status'], 0) + 1
        row = db.get(models.ProductTaxMultiplier, (calculator.name, payload.origin, key)) or models.ProductTaxMultiplier(destination=calculator.name, origin=payload.origin, product_key=key)
        row.product_name = product.name.strip()
        row.category = product.category
        row.hs_code = product.hs_code
        row.price_usd_kg = product.price_usd_kg
        row.tariff_code = computed.get('tariff_code')
        row.tariff_path = computed.get('tariff_path')
        row.tax_multiplier = computed.get('tax_multiplier')
        row.landed_multiplier = computed.get('landed_multiplier')
        row.status = computed['status']
        row.method = computed.get('method')
        row.note = computed.get('note')
        row.detail_json = json.dumps(computed.get('detail') or [])
        row.computed_at = now
        db.add(row)
    db.commit()
    return {'destination': calculator.name, 'origin': payload.origin, 'products': len(seen), 'by_status': counts}


@router.get('/tax-calc/multipliers')
def list_multipliers(destination: str, origin: str, db: Session = Depends(get_db)):
    """The stored multipliers of origin -> destination, by product."""
    calculator = tax_calc.get(destination)
    name = calculator.name if calculator else destination
    rows = db.query(models.ProductTaxMultiplier).filter_by(destination=name, origin=origin).all()
    return {'destination': name, 'origin': origin, 'available': calculator is not None, 'multipliers': [_multiplier_out(row) for row in rows]}


@router.get('/tax-calc/{country}/suggest')
def suggest_line(country: str, name: str, hs_code: str | None = None, origin: str | None = None, price_usd_kg: float | None = None):
    """The destination tariff line a product maps to (the same rule the multipliers use), with the other candidates under its HS code."""
    calculator = _calculator(country)
    product = {'name': name, 'hs_code': hs_code, 'price_usd_kg': price_usd_kg}
    computed = mapping.multiplier_for(calculator, product, origin)
    candidates = [calculator.get(line['code']) for line in mapping.lines_for_hs(calculator, hs_code)][:30]
    chosen = calculator.get(computed['tariff_code']) if computed.get('tariff_code') else None
    return {'line': chosen, 'method': computed.get('method'), 'status': computed['status'], 'note': computed.get('note'), 'candidates': [c for c in candidates if c]}


# ---------------------------------------------------------------- Colombia (DIAN WebArancel): Gravamen + IVA of an HS code
# backend/tax_calc/colombia_dian/ — Playwright reproduces the user workflow on DIAN's tariff consultation. A lookup takes ~5-20 s, so the UI
# starts a job and polls it for progress; the GET variant waits for the answer (scripts, tests). See that folder's README.md.


class DianLookupIn(BaseModel):
    hsCode: str
    date: str | None = None
    forceRefresh: bool = False
    debug: bool = False


class DianBatchIn(BaseModel):
    hsCodes: list[str] = Field(min_length=1, max_length=100)
    date: str | None = None
    concurrency: int = Field(default=1, ge=1, le=2)
    delayMs: int = Field(default=1500, ge=0, le=60000)
    forceRefresh: bool = False


class DianCalculateIn(BaseModel):
    customsValue: float = Field(ge=0)
    gravamen: dict | None = None  # one TaxValue (the row the user chose, or the only valid one)
    iva: dict | None = None
    ivaStatus: str = 'listed'


@router.post('/tax-calc/colombia/dian/lookups')
def start_dian_lookup(payload: DianLookupIn):
    job = dian_jobs.start_lookup('CO', payload.hsCode, payload.date, payload.forceRefresh, payload.debug)
    return {'jobId': job['id'], 'status': job['status']}


@router.post('/tax-calc/colombia/dian/batch')
def start_dian_batch(payload: DianBatchIn):
    job = dian_jobs.start_batch('CO', payload.hsCodes, payload.date, payload.concurrency, payload.delayMs, payload.forceRefresh)
    return {'jobId': job['id'], 'status': job['status']}


@router.get('/tax-calc/colombia/dian/jobs/{job_id}')
def get_dian_job(job_id: str):
    job = dian_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='Unknown or expired lookup job.')
    return job


@router.post('/tax-calc/colombia/dian/calculate')
def calculate_dian_taxes(payload: DianCalculateIn):
    """The pure calculator (no network): customs value + the Gravamen and IVA the user is working with."""
    return dian_import_taxes.calculate_import_taxes(payload.customsValue, payload.gravamen, payload.iva, payload.ivaStatus)


@router.get('/tax-calc/colombia/dian/{hs_code}')
def lookup_dian(hs_code: str, date: str | None = None, forceRefresh: bool = False):
    """Waits for the lookup and returns the TaxLookupResult."""
    return dian_service.lookup(TaxLookupRequest(country='CO', hsCode=hs_code, date=date, forceRefresh=forceRefresh))
