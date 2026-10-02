from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import Aircraft, Plan
from .seed import seed_aircraft
from .tables import AircraftRecord, PlanRecord


def ensure_seed(db: Session):
    if db.get(AircraftRecord,'a321p2f') is None:
        db.add(AircraftRecord(**seed_aircraft().model_dump(mode='json')))
        db.commit()


def get_aircraft(db, aircraft_id):
    ensure_seed(db)
    record = db.get(AircraftRecord,aircraft_id)
    if not record:
        raise HTTPException(404,'Aircraft not found')
    return Aircraft.model_validate({k:getattr(record,k) for k in Aircraft.model_fields})


def resolve_aircraft(db, plan):
    aircraft = plan.aircraft or get_aircraft(db,plan.aircraft_id)
    if aircraft.id != plan.aircraft_id:
        raise HTTPException(422,'Inline aircraft id does not match aircraft_id')
    for deck, positions in plan.alloc.items():
        known = {p.id for p in aircraft.decks[deck].positions}
        if any(pos not in known for pos in positions):
            raise HTTPException(422,f'Unknown {deck} deck allocation position')
        for alloc in positions.values():
            if any(not key.isdigit() or int(key)>=len(plan.box_types) for key in alloc):
                raise HTTPException(422,'Allocation refers to an unknown box type')
    return aircraft


def plan_record(db, plan_id):
    record = db.get(PlanRecord,plan_id)
    if not record:
        raise HTTPException(404,'Plan not found')
    return record


def read_plan(record):
    return Plan.model_validate({k:getattr(record,k) for k in Plan.model_fields})
