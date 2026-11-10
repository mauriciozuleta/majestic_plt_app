"""Shipments API (backend/shipments/): what the route table and the shipment cards show, the Shipment builder's candidates, and how the kilos are shared. Moved from the browser;
the numbers equal what the JavaScript gave (backend/tests/test_shipments_parity.py). The built shipments themselves are saved by the existing revenue-stream route endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..shipments import allocation, service

router = APIRouter(prefix='/api/shipments', tags=['shipments'])


@router.get('/route-finance')
def route_finance(route_id: str = Query(...), db: Session = Depends(get_db)):
    """Tier R. For one revenue route and each of its legs: the air fare per kg, revenue / COS / profit, and for a built shipment each product's cost chain (FCA, DAP, taxes, DDP),
    market level and suggested sale price with the totals. `comparison.stale` says whether the saved comparison it is priced from is out of date."""
    result = service.route_finance(db, route_id)
    if result is None:
        raise HTTPException(status_code=404, detail='No such route.')
    return result


@router.get('/airfares')
def airfares(source_country: str = Query(...), target_countries: str = Query(...), db: Session = Depends(get_db)):
    """Tier R. Has a shipment been built for source -> target, and what is that route's air fare per kg? {target: {airfarePerKg, note, routeName}}."""
    return {'airfares': service.built_shipment_airfares(db, source_country, [name for name in target_countries.split(',') if name])}


@router.get('/pair-pricing')
def pair_pricing(source_country: str = Query(...), target_countries: str = Query(...), db: Session = Depends(get_db)):
    """Tier R. What Market Opportunities shows beside each product of a pair that has a built shipment: DDP price, Market Level and suggested sell price, for the products of the saved
    comparison (`rows`) and the portfolio products with no match (`unmatched`); keys `target|product name lowercased`."""
    return service.pair_pricing(db, source_country, [name for name in target_countries.split(',') if name])


@router.get('/candidates')
def candidates(source_country: str = Query(...), target_country: str = Query(...), airfare_per_kg: float | None = None, db: Session = Depends(get_db)):
    """Tier R. The products a shipment of source -> target can be built from (the priority list, looked up in the SAVED comparison), grouped by rating, each with Country SAM,
    market level, cargo cap and margin. `status`: no_priority | no_comparison (compute it first) | ready."""
    return service.candidates(db, source_country, target_country, airfare_per_kg)


class AllocateIn(BaseModel):
    products: list[dict]  # the candidates picked, as /candidates returned them
    capacity_kg: float
    fixed_kg: dict[str, float] = {}  # product key -> weight typed by hand, kept as it is


@router.post('/allocate')
def allocate(payload: AllocateIn):
    """Tier S (saves nothing). Shares the aircraft's capacity over the picked products: wholesalers first, premium second, niche last; manual weights kept; whole kg."""
    return allocation.allocate_shipment(payload.products, payload.capacity_kg, payload.fixed_kg)
