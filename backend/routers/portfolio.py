"""Product portfolio API (backend/portfolio/): the directory of every country's products with their HS codes, the category coverage (which HS chapters, headings and
subheadings have products, in which countries, wholesale or retail) and the merged Colombia table. All read-only (tier R), derived from the stored catalogs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import portfolio
from ..database import get_db

router = APIRouter(prefix='/api/portfolio', tags=['portfolio'])


@router.get('/directory')
def get_directory(country: str | None = None, db: Session = Depends(get_db)):
    """One row per country and product: {code, name, category, country, countries, hs, label}. Optional ?country= filter."""
    rows = portfolio.directory(db)
    if country:
        rows = [row for row in rows if row['country'].lower() == country.strip().lower()]
    return {'rows': rows}


@router.get('/category-coverage')
def get_category_coverage(db: Session = Depends(get_db)):
    """{chapter: {wholesaler, retail, productCount, countries, headings: {...}}} — the keys are the chapters SAM and TAM cover."""
    return portfolio.category_coverage(db)


@router.get('/qualifying-chapters')
def get_qualifying_chapters(db: Session = Depends(get_db)):
    return {'chapters': portfolio.qualifying_chapters(db)}


@router.get('/products')
def get_products(country: str, db: Session = Depends(get_db)):
    """The products of one country with their English names and HS blocks: [{name, category, source_ids, hs}]."""
    for group in portfolio.country_products(db):
        if group['country'].lower() == country.strip().lower():
            return {'country': group['country'], 'products': group['products']}
    raise HTTPException(status_code=404, detail=f'No products are stored for {country}.')


@router.get('/colombia')
def get_colombia(db: Session = Depends(get_db)):
    """The Colombia table: La Mayorista and Corabastos merged by product id, each row with its English name (`name_en`, `translated`, `translation_tier`) and the
    comparison fields (`matched`, `comparable`, `diffPct`, `cheaperAt` ...)."""
    return {'rows': portfolio.colombia_merged(db)}
