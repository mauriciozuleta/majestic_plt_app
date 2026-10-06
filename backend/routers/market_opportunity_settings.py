"""Settings ▸ Market Opportunity settings: the opportunity-rating margin scale (Market opportunity margin) and
the Destination Market categories. The scale used to be hardcoded in market_opportunities.py; it is now read from
here (`margin_tiers`), and saving it re-rates every saved comparison from its stored diff_pct."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter()

# diff_pct = source price as a % of the target price: a LOW value is a big margin. A tier covers min <= diff_pct < max;
# the last tier has no upper limit.
DEFAULT_MARGIN_TIERS = [
    {'rating': 'Very High', 'min': 0, 'max': 20},
    {'rating': 'High', 'min': 20, 'max': 30},
    {'rating': 'Challenging', 'min': 30, 'max': 50},
    {'rating': 'Complex', 'min': 50, 'max': 65},
    {'rating': 'Difficult', 'min': 65, 'max': 100},
    {'rating': 'Not Viable', 'min': 100, 'max': None},
]
DEFAULT_DESTINATION_MARKETS = [
    {'key': 'premium', 'label': 'Premium Market', 'min': None, 'max': None},
    {'key': 'niche', 'label': 'Niche Markets', 'min': None, 'max': None},
    {'key': 'wholesalers', 'label': 'Wholesalers', 'min': None, 'max': None},
]


def _row(db: Session) -> models.MarketOpportunitySettings:
    row = db.query(models.MarketOpportunitySettings).filter_by(id='singleton').first()
    if not row:
        row = models.MarketOpportunitySettings(id='singleton')
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_margin_tiers(db: Session) -> list[dict]:
    row = db.query(models.MarketOpportunitySettings).filter_by(id='singleton').first()
    if row and row.margin_tiers_json:
        try:
            return json.loads(row.margin_tiers_json)
        except ValueError:
            pass
    return DEFAULT_MARGIN_TIERS


def rating_for(diff_pct: float, tiers: list[dict]) -> str:
    for tier in tiers:
        if tier['max'] is None or diff_pct < tier['max']:
            return tier['rating']
    return tiers[-1]['rating']


def _settings_out(db: Session) -> dict:
    row = _row(db)
    destination = json.loads(row.destination_markets_json) if row.destination_markets_json else DEFAULT_DESTINATION_MARKETS
    return {'margin_tiers': get_margin_tiers(db), 'destination_markets': destination}


class TierIn(BaseModel):
    rating: str
    min: float
    max: float | None = None


class DestinationMarketIn(BaseModel):
    key: str
    label: str
    min: float | None = None
    max: float | None = None


class MarketOpportunitySettingsIn(BaseModel):
    margin_tiers: list[TierIn]
    destination_markets: list[DestinationMarketIn]


@router.get('/market-opportunity-settings')
def read_settings(db: Session = Depends(get_db)):
    return _settings_out(db)


@router.put('/market-opportunity-settings')
def save_settings(payload: MarketOpportunitySettingsIn, db: Session = Depends(get_db)):
    tiers = payload.margin_tiers
    if [tier.rating for tier in tiers] != [tier['rating'] for tier in DEFAULT_MARGIN_TIERS]:
        raise HTTPException(status_code=400, detail='The margin scale must keep its six ratings, in order.')
    if tiers[0].min != 0:
        raise HTTPException(status_code=400, detail='The first margin range starts at 0%.')
    for index, tier in enumerate(tiers):
        last = index == len(tiers) - 1
        if last:
            if tier.max is not None:
                raise HTTPException(status_code=400, detail=f'{tier.rating} has no upper limit.')
        elif tier.max is None or tier.max <= tier.min:
            raise HTTPException(status_code=400, detail=f'{tier.rating}: the upper value must be above the lower one.')
        if index and tier.min != tiers[index - 1].max:
            raise HTTPException(status_code=400, detail=f'{tier.rating} must start where {tiers[index - 1].rating} ends.')
    for market in payload.destination_markets:
        if market.min is not None and market.max is not None and market.max < market.min:
            raise HTTPException(status_code=400, detail=f'{market.label}: the upper value cannot be below the lower one.')

    row = _row(db)
    tier_dicts = [tier.model_dump() for tier in tiers]
    row.margin_tiers_json = json.dumps(tier_dicts)
    row.destination_markets_json = json.dumps([market.model_dump() for market in payload.destination_markets])
    # The rating is stored with each saved comparison: re-rate them under the new scale.
    for comparison in db.query(models.MarketOpportunityComparison).filter(models.MarketOpportunityComparison.diff_pct.isnot(None)):
        comparison.opportunity_rating = rating_for(comparison.diff_pct, tier_dicts)
    db.commit()
    return _settings_out(db)
