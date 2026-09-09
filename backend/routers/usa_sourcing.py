"""Seven independent endpoints (one per USDA AMS report), same pattern as
the Colombia price-comparison module: each source fetches/parses/persists
independently, so one report being down never blocks the others (the
frontend calls all seven via Promise.allSettled). No Seafood endpoint here —
the spec found no confirmed, directly-fetchable primary source for it this
session; that stays an explicit "not yet available" gap in the UI rather
than a placeholder built on a secondary citation.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..snapshot_store import list_snapshots, save_snapshot
from ..usa_sources.beef import fetch_beef_products
from ..usa_sources.eggs import fetch_egg_products
from ..usa_sources.grains import fetch_grain_products
from ..usa_sources.pork import fetch_pork_products
from ..usa_sources.poultry import fetch_poultry_products
from ..usa_sources.produce_ca import fetch_produce_ca_products
from ..usa_sources.produce_fl import fetch_produce_fl_products

router = APIRouter()

_SNAPSHOT_SOURCES = [
    'usa_beef',
    'usa_pork',
    'usa_poultry',
    'usa_eggs',
    'usa_grains',
    'usa_produce_fl',
    'usa_produce_ca',
]


def _endpoint(source_key, fetch_fn, label):
    def handler(db: Session = Depends(get_db)):
        try:
            products = fetch_fn()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f'{label} fetch failed: {exc}') from exc
        save_snapshot(db, source_key, products)
        return products

    return handler


router.add_api_route('/market-analysis/usa/beef', _endpoint('usa_beef', fetch_beef_products, 'Beef'), methods=['GET'])
router.add_api_route('/market-analysis/usa/pork', _endpoint('usa_pork', fetch_pork_products, 'Pork'), methods=['GET'])
router.add_api_route(
    '/market-analysis/usa/poultry', _endpoint('usa_poultry', fetch_poultry_products, 'Poultry'), methods=['GET']
)
router.add_api_route('/market-analysis/usa/eggs', _endpoint('usa_eggs', fetch_egg_products, 'Eggs'), methods=['GET'])
router.add_api_route(
    '/market-analysis/usa/grains', _endpoint('usa_grains', fetch_grain_products, 'Grains'), methods=['GET']
)
router.add_api_route(
    '/market-analysis/usa/produce-fl',
    _endpoint('usa_produce_fl', fetch_produce_fl_products, 'Produce (FL)'),
    methods=['GET'],
)
router.add_api_route(
    '/market-analysis/usa/produce-ca',
    _endpoint('usa_produce_ca', fetch_produce_ca_products, 'Produce (CA)'),
    methods=['GET'],
)


@router.get('/market-analysis/usa/snapshot', response_model=list[schemas.PriceComparisonSnapshotOut])
def get_usa_sourcing_snapshot(db: Session = Depends(get_db)):
    return list_snapshots(db, _SNAPSHOT_SOURCES)
