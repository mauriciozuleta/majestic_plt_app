import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .payroll import _apply_growth_rate_to_record, _get_projection_years_limit

router = APIRouter()
FICTITIOUS_EPOCH = date(1, 1, 1)

# "location" on a position is free text from wherever it was entered/
# imported (e.g. "USA" from the payroll import template), not the
# commercial structure's own country name ("United States") — so matching
# it needs a small alias set rather than an exact-name comparison.
USA_LOCATION_ALIASES = {'usa', 'us', 'united states', 'united states of america'}


def _is_usa_location(location):
    return (location or '').strip().lower() in USA_LOCATION_ALIASES


TAX_OBLIGATIONS_SCHEDULE_OPTIONS = {'next_business_day', '2', '3', '4', '5', '6', '7', 'end_of_month'}


def _get_or_create_settings(db: Session):
    settings = db.query(models.PortfolioSettings).filter_by(id='singleton').first()
    if not settings:
        settings = models.PortfolioSettings(id='singleton', calendar_mode='real', projection_years=5)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    elif not settings.projection_years:
        settings.projection_years = 5
        db.commit()
        db.refresh(settings)
    return settings


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=f'Invalid {field_name}. Expected YYYY-MM-DD') from error


def _convert_real_to_simulation(db: Session, real_start: date):
    def shift(iso_date_str):
        stored = date.fromisoformat(iso_date_str)
        elapsed_days = (stored - real_start).days
        return (FICTITIOUS_EPOCH + timedelta(days=elapsed_days)).isoformat()

    tasks = db.query(models.RoadmapTask).all()
    for task in tasks:
        task.start = shift(task.start)
        task.end = shift(task.end)

    records = db.query(models.PayrollRecord).all()
    for record in records:
        record.start_date = shift(record.start_date)

    return len(tasks), len(records)


def _convert_simulation_to_real(db: Session, real_start: date):
    def shift(iso_date_str):
        stored = date.fromisoformat(iso_date_str)
        elapsed_days = (stored - FICTITIOUS_EPOCH).days
        return (real_start + timedelta(days=elapsed_days)).isoformat()

    tasks = db.query(models.RoadmapTask).all()
    for task in tasks:
        task.start = shift(task.start)
        task.end = shift(task.end)

    records = db.query(models.PayrollRecord).all()
    for record in records:
        record.start_date = shift(record.start_date)

    return len(tasks), len(records)


@router.get('/settings')
def get_settings(db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)
    try:
        enabled_benefits = json.loads(settings.enabled_benefits_json or '[]')
    except (TypeError, ValueError):
        enabled_benefits = []
    return {
        'calendar_mode': settings.calendar_mode,
        'projection_years': max(5, min(10, settings.projection_years or 5)),
        'enabled_benefits': enabled_benefits,
        'inflation_pct': settings.inflation_pct or 0.0,
        'payroll_schedule_type': settings.payroll_schedule_type,
        'payroll_schedule_monthly_day': settings.payroll_schedule_monthly_day,
        'payroll_schedule_biweekly_day1': settings.payroll_schedule_biweekly_day1,
        'payroll_schedule_biweekly_day2': settings.payroll_schedule_biweekly_day2,
        'tax_obligations_schedule': settings.tax_obligations_schedule,
        'colombia_projected_cop_per_usd': settings.colombia_projected_cop_per_usd,
        'colombia_smmlv_cop': settings.colombia_smmlv_cop,
        'colombia_uvt_cop': settings.colombia_uvt_cop,
    }


@router.patch('/settings/colombia-exchange-rate')
def set_colombia_exchange_rate(payload: dict, db: Session = Depends(get_db)):
    """Persists a locked-in COP-per-USD rate for Colombia payroll tax
    calculations, so those numbers don't shift every time the live FX rate
    moves — the live rate is still shown for reference, but only this
    saved value is actually used in the calculator."""
    settings = _get_or_create_settings(db)
    cop_per_usd = payload.get('cop_per_usd')
    if not isinstance(cop_per_usd, (int, float)) or cop_per_usd <= 0:
        raise HTTPException(status_code=400, detail='cop_per_usd must be a positive number')

    settings.colombia_projected_cop_per_usd = cop_per_usd
    db.commit()
    return {'colombia_projected_cop_per_usd': settings.colombia_projected_cop_per_usd}


@router.patch('/settings/colombia-reference-figures')
def set_colombia_reference_figures(payload: dict, db: Session = Depends(get_db)):
    """Persists the SMMLV (minimum wage) and UVT figures the Colombia
    calculator uses — these are indexed annually by the Colombian
    government, so letting the user update them directly avoids waiting on
    a code change every January."""
    settings = _get_or_create_settings(db)
    smmlv_cop = payload.get('smmlv_cop')
    uvt_cop = payload.get('uvt_cop')

    if not isinstance(smmlv_cop, (int, float)) or smmlv_cop <= 0:
        raise HTTPException(status_code=400, detail='smmlv_cop must be a positive number')
    if not isinstance(uvt_cop, (int, float)) or uvt_cop <= 0:
        raise HTTPException(status_code=400, detail='uvt_cop must be a positive number')

    settings.colombia_smmlv_cop = smmlv_cop
    settings.colombia_uvt_cop = uvt_cop
    db.commit()
    return {'colombia_smmlv_cop': settings.colombia_smmlv_cop, 'colombia_uvt_cop': settings.colombia_uvt_cop}


@router.patch('/settings/enabled-benefits')
def set_enabled_benefits(payload: dict, db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)
    benefit_keys = payload.get('benefit_keys')
    if not isinstance(benefit_keys, list) or not all(isinstance(key, str) for key in benefit_keys):
        raise HTTPException(status_code=400, detail='benefit_keys must be a list of strings')

    settings.enabled_benefits_json = json.dumps(benefit_keys)
    db.commit()
    return {'enabled_benefits': benefit_keys}


@router.patch('/settings/inflation')
def set_inflation(payload: dict, db: Session = Depends(get_db)):
    """Sets the (US) inflation rate and re-derives Year 2..N salary from it,
    compounding year over year, for every position actually located in the
    USA — the same mechanism the old per-visit "Apply to all" raise button
    used (see payroll.py's _apply_growth_rate_to_record), just driven by
    this one persisted setting instead of a manual action, and now scoped
    to the positions this rate actually describes."""
    settings = _get_or_create_settings(db)
    inflation_pct = payload.get('inflation_pct')
    if not isinstance(inflation_pct, (int, float)):
        raise HTTPException(status_code=400, detail='inflation_pct must be a number')

    if settings.inflation_pct == inflation_pct:
        return {'inflation_pct': inflation_pct, 'positions_updated': 0}

    settings.inflation_pct = inflation_pct
    projection_years_limit = _get_projection_years_limit(db)

    usa_node_ids = [node.id for node in db.query(models.OrgChartNode).all() if _is_usa_location(node.location)]
    records = (
        db.query(models.PayrollRecord).filter(models.PayrollRecord.org_chart_node_id.in_(usa_node_ids)).all()
        if usa_node_ids
        else []
    )

    for target_year in range(2, projection_years_limit + 1):
        for record in records:
            _apply_growth_rate_to_record(db, record, inflation_pct, target_year)
        # Flushed per year, not just committed once at the end — the next
        # year's computation reads the previous year's salary via a plain
        # query (autoflush is off for this session), so an update to an
        # already-existing year row (as opposed to a newly-created one,
        # which flushes itself) would otherwise still look stale.
        db.flush()

    db.commit()
    return {'inflation_pct': inflation_pct, 'positions_updated': len(records)}


@router.patch('/settings/payroll-schedule')
def set_payroll_schedule(payload: dict, db: Session = Depends(get_db)):
    """Persists the payroll-run and tax-remittance schedule selections —
    not wired to any actual date computation yet, just saved so the
    Settings panel remembers what was picked."""
    settings = _get_or_create_settings(db)

    schedule_type = payload.get('payroll_schedule_type')
    if schedule_type is not None and schedule_type not in ('monthly', 'biweekly'):
        raise HTTPException(status_code=400, detail="payroll_schedule_type must be 'monthly' or 'biweekly'")

    def _validate_day(value, field_name):
        if value is None:
            return None
        if not isinstance(value, int) or value < 1 or value > 30:
            raise HTTPException(status_code=400, detail=f'{field_name} must be an integer between 1 and 30')
        return value

    monthly_day = _validate_day(payload.get('payroll_schedule_monthly_day'), 'payroll_schedule_monthly_day')
    biweekly_day1 = _validate_day(payload.get('payroll_schedule_biweekly_day1'), 'payroll_schedule_biweekly_day1')
    biweekly_day2 = _validate_day(payload.get('payroll_schedule_biweekly_day2'), 'payroll_schedule_biweekly_day2')

    tax_obligations_schedule = payload.get('tax_obligations_schedule')
    if tax_obligations_schedule is not None and tax_obligations_schedule not in TAX_OBLIGATIONS_SCHEDULE_OPTIONS:
        raise HTTPException(status_code=400, detail=f'tax_obligations_schedule must be one of {sorted(TAX_OBLIGATIONS_SCHEDULE_OPTIONS)}')

    settings.payroll_schedule_type = schedule_type
    settings.payroll_schedule_monthly_day = monthly_day
    settings.payroll_schedule_biweekly_day1 = biweekly_day1
    settings.payroll_schedule_biweekly_day2 = biweekly_day2
    settings.tax_obligations_schedule = tax_obligations_schedule
    db.commit()

    return {
        'payroll_schedule_type': settings.payroll_schedule_type,
        'payroll_schedule_monthly_day': settings.payroll_schedule_monthly_day,
        'payroll_schedule_biweekly_day1': settings.payroll_schedule_biweekly_day1,
        'payroll_schedule_biweekly_day2': settings.payroll_schedule_biweekly_day2,
        'tax_obligations_schedule': settings.tax_obligations_schedule,
    }


@router.patch('/settings/time-projection')
def set_time_projection(payload: dict, db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)
    projection_years = payload.get('projection_years')

    if not isinstance(projection_years, int):
        raise HTTPException(status_code=400, detail='projection_years must be an integer')
    if projection_years < 5 or projection_years > 10:
        raise HTTPException(status_code=400, detail='projection_years must be between 5 and 10')

    settings.projection_years = projection_years
    db.commit()

    return {
        'calendar_mode': settings.calendar_mode,
        'projection_years': settings.projection_years,
    }


@router.patch('/settings/calendar-mode')
def set_calendar_mode(payload: dict, db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)
    mode = payload.get('mode')
    if mode not in ('real', 'simulation'):
        raise HTTPException(status_code=400, detail="mode must be 'real' or 'simulation'")

    if mode == settings.calendar_mode:
        return {'calendar_mode': settings.calendar_mode, 'tasks_converted': 0, 'payroll_records_converted': 0}

    real_start = _parse_iso_date(payload.get('real_start_date'), 'real_start_date')

    if mode == 'simulation':
        tasks_count, records_count = _convert_real_to_simulation(db, real_start)
    else:
        tasks_count, records_count = _convert_simulation_to_real(db, real_start)

    settings.calendar_mode = mode
    db.commit()
    return {
        'calendar_mode': settings.calendar_mode,
        'tasks_converted': tasks_count,
        'payroll_records_converted': records_count,
    }


@router.post('/settings/assign-start-date')
def assign_start_date(payload: dict, db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)
    if settings.calendar_mode != 'simulation':
        raise HTTPException(status_code=400, detail='Project is not in Simulation mode')

    real_start = _parse_iso_date(payload.get('real_start_date'), 'real_start_date')
    tasks_count, records_count = _convert_simulation_to_real(db, real_start)

    settings.calendar_mode = 'real'
    db.commit()
    return {'tasks_converted': tasks_count, 'payroll_records_converted': records_count}