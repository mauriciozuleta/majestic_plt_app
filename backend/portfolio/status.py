"""Market Analysis status columns, worked out on the server (moved from src/services/marketAnalysisStatus.js, which joined seven endpoints in the browser): for every
country, whether it has a built profile, which competitiveness analyses involve it, how many products still lack an item weight or an HS code, and whether it has product
data. Read-only; it reuses the handlers of the endpoints the browser used to call, so the numbers are the same."""

from .. import models
from ..catalog_normalization import hs_store
from ..catalog_normalization import scope_store
from ..snapshot_store import list_snapshots
from .service import USA_SOURCES

COLOMBIA_SOURCES = ('la_mayorista', 'corabastos')


def _has_products(db, sources) -> bool:
    return any(isinstance(snapshot['products'], list) and len(snapshot['products']) > 0 for snapshot in list_snapshots(db, list(sources)))


def _custom_source_countries(db) -> set[str]:
    """Lower-cased country names that have a custom product source with stored products."""
    names = set()
    for source in db.query(models.ProductSource).filter(models.ProductSource.product_count > 0):
        if list_snapshots(db, [f'custom_{source.id}']):
            names.add(source.country_name.strip().lower())
    return names


def market_analysis_status(db) -> dict:
    """{country_id: {profile: {country_id, country_name, generated_at} | None, analyses: [...], missingCount, hsMissingCount, discardedCount, hasProductData}} for every commercial country."""
    from ..routers.catalog_normalization import missing_summary
    from ..routers.competitiveness import list_competitiveness_analyses
    from ..routers.country_profile import list_country_profiles

    countries = db.query(models.CommercialCountry).all()
    company_ids = sorted({country.company_id for country in countries})
    profiles = {row['country_id']: row for company_id in company_ids for row in list_country_profiles(company_id, db)}
    # An analysis is filed under its TARGET's company, but its SOURCE can be a country of any company: matching by name across every company's list finds it either way.
    analyses = [row for company_id in company_ids for row in list_competitiveness_analyses(company_id, db)]
    missing = missing_summary(db)['countries']
    hs = hs_store.status(db).get('countries', {})
    discarded: dict[str, int] = {}
    for source in scope_store.summary(db)['sources']:
        discarded[source['country']] = discarded.get(source['country'], 0) + source['secondary']
    has_colombia, has_usa, custom = _has_products(db, COLOMBIA_SOURCES), _has_products(db, USA_SOURCES), _custom_source_countries(db)
    status = {}
    for country in countries:
        name = country.name.strip().lower()
        counts = hs.get(country.name) or {}
        status[country.id] = {
            'profile': profiles.get(country.id),
            'analyses': [row for row in analyses if (row.get('source_country_name') or '').strip().lower() == name or row['target_country_id'] == country.id],
            'missingCount': missing.get(country.name, 0),
            'hsMissingCount': (counts.get('no_code') or 0) + (counts.get('heading_only') or 0) + (counts.get('obsolete') or 0),
            'discardedCount': discarded.get(country.name, 0),  # downloaded products kept out of the main catalog (catalog_normalization/scope.py)
            'hasProductData': (name == 'colombia' and has_colombia) or (name == 'united states' and has_usa) or name in custom,
        }
    return status
