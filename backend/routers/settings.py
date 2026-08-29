from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()
FICTITIOUS_EPOCH = date(1, 1, 1)


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
    return {
        'calendar_mode': settings.calendar_mode,
        'projection_years': max(5, min(10, settings.projection_years or 5)),
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