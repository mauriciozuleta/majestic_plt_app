import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, ValidationError
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from ..database import get_db
from ..packer.models import Aircraft, Plan, Model
from ..packer.tables import AircraftRecord, PlanRecord, BoxSlot, ReleaseEvent
from ..packer.repository import ensure_seed, get_aircraft, resolve_aircraft, plan_record, read_plan
from ..packer.plan import pack_plan
from ..packer.suggest import SuggestRequest, suggest_sizes
from ..packer.ai_draft import draft_aircraft
from ..packer.exports import boxes_csv
from ..packer.pdf_labels import labels_pdf
from ..packer.pdf_workorder import workorder_pdf
from ..packer.workorder import build_steps
from reportlab.graphics.barcode import createBarcodeDrawing
from typing import Annotated

router = APIRouter(prefix='/api/packer',tags=['Cargo load operations'])


class BarcodeRequest(Model):
    ids: list[Annotated[str, Field(min_length=1,max_length=45,pattern=r'^[A-Za-z0-9_-]+$')]] = Field(max_length=6)


@router.post('/barcodes')
def barcode_preview(body: BarcodeRequest):
    return {value:createBarcodeDrawing('Code128',value=value,barHeight=30,humanReadable=True).asString('svg') for value in body.ids}


@router.get('/aircraft')
def aircraft_list(db: Session = Depends(get_db)):
    ensure_seed(db)
    return [get_aircraft(db,row.id) for row in db.scalars(select(AircraftRecord).where(AircraftRecord.hidden==False))]


class DraftRequest(Model):
    query: str = Field(min_length=3,max_length=500)


@router.post('/aircraft/draft')
def aircraft_draft(request: DraftRequest):
    try:
        return draft_aircraft(request.query)
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        raise HTTPException(422,'AI returned incomplete or invalid geometry; refine the query and try again.') from exc
    except Exception as exc:
        raise HTTPException(502,'AI drafting request failed. Check backend connectivity.') from exc


@router.get('/aircraft/{aircraft_id}')
def aircraft_get(aircraft_id: str, db: Session = Depends(get_db)):
    return get_aircraft(db,aircraft_id)


@router.put('/aircraft/{aircraft_id}')
def aircraft_save(aircraft_id: str, body: Aircraft, db: Session = Depends(get_db)):
    if body.id != aircraft_id:
        raise HTTPException(422,'Aircraft id mismatch')
    body.builtin = aircraft_id == 'a321p2f'
    db.merge(AircraftRecord(**body.model_dump(mode='json'),hidden=False))
    db.commit()
    return body


@router.delete('/aircraft/{aircraft_id}')
def aircraft_delete(aircraft_id: str, db: Session = Depends(get_db)):
    if aircraft_id == 'a321p2f':
        raise HTTPException(422,'Built-in aircraft cannot be deleted')
    if db.scalar(select(PlanRecord.id).where(PlanRecord.aircraft_id==aircraft_id)):
        raise HTTPException(409,'Aircraft is used by a saved plan')
    get_aircraft(db,aircraft_id)
    db.execute(delete(AircraftRecord).where(AircraftRecord.id==aircraft_id))
    db.commit()
    return {'deleted':True}


@router.get('/plans')
def plans_list(company_id: str, db: Session = Depends(get_db)):
    return [dict(id=r.id,name=r.name,version=r.version) for r in db.scalars(select(PlanRecord).where(PlanRecord.company_id==company_id).order_by(PlanRecord.updated_at.desc()))]


@router.get('/plans/{plan_id}')
def plan_get(plan_id: str, db: Session = Depends(get_db)):
    return read_plan(plan_record(db,plan_id))


@router.post('/plans')
def plan_save(body: Plan, db: Session = Depends(get_db)):
    aircraft = resolve_aircraft(db,body)
    existing = db.get(PlanRecord,body.id) if body.id else None
    if existing and existing.company_id != body.company_id:
        raise HTTPException(409,'Plan belongs to another company')
    if existing and existing.version != body.version:
        raise HTTPException(409,'Plan changed in another window. Reload before saving.')
    if not db.get(AircraftRecord,aircraft.id):
        db.add(AircraftRecord(**aircraft.model_dump(mode='json'),hidden=True))
        db.flush()
    body.id = body.id or str(uuid.uuid4())
    body.version = (existing.version if existing else 0)+1
    body.aircraft = aircraft
    values = body.model_dump(mode='json')
    record = existing or PlanRecord()
    for key,value in values.items():
        setattr(record,key,value)
    db.add(record)
    db.commit()
    return read_plan(record)


@router.post('/plans/{plan_id}')
def plan_update(plan_id: str, body: Plan, db: Session = Depends(get_db)):
    if body.id != plan_id:
        raise HTTPException(422,'Plan id mismatch')
    return plan_save(body,db)


@router.post('/pack')
def pack(body: Plan, db: Session = Depends(get_db)):
    return pack_plan(body,resolve_aircraft(db,body))


@router.post('/suggest')
def suggest(body: SuggestRequest, db: Session = Depends(get_db)):
    try:
        return suggest_sizes(body,resolve_aircraft(db,body.plan))
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


class ReleaseRequest(Model):
    confirm_reassign: bool = False


def layout(result):
    return [{k:b[k] for k in ('box_id','deck','position','layer','slot','type_index','dims_cm','upright','actual_kg','volume_kg','x','y','z','dx','dy','dz')} for b in result['boxes']]


@router.post('/plans/{plan_id}/release')
def release(plan_id: str, body: ReleaseRequest, db: Session = Depends(get_db)):
    record = plan_record(db,plan_id)
    plan = read_plan(record)
    result = pack_plan(plan,resolve_aircraft(db,plan))
    changed = record.released_result is not None and layout(record.released_result) != layout(result)
    if changed and not body.confirm_reassign:
        raise HTTPException(409,'Box IDs will be reassigned; reprint labels for affected positions.')
    ids = [b['box_id'] for b in result['boxes']]
    # Query in batches to remain below SQLite parameter limits.
    for start in range(0,len(ids),500):
        collision = db.scalar(select(BoxSlot.box_id).where(BoxSlot.box_id.in_(ids[start:start+500]),BoxSlot.plan_id!=plan_id))
        if collision:
            raise HTTPException(409,f'Box ID {collision} belongs to another released plan. Choose a unique ID prefix in Packing rules.')
    db.execute(delete(BoxSlot).where(BoxSlot.plan_id==plan_id))
    keys = set(BoxSlot.__table__.columns.keys())-{'created_at','plan_id'}
    db.add_all([BoxSlot(plan_id=plan_id,**{k:b[k] for k in keys}) for b in result['boxes']])
    record.released_result = result
    record.released_plan = plan.model_dump(mode='json')
    event = dict(plan_id=plan_id,box_ids=ids)
    db.add(ReleaseEvent(payload=event))
    db.commit()
    return dict(event,changed=changed)


@router.get('/events')
def events(after: int = 0, db: Session = Depends(get_db)):
    return [dict(id=r.id,**r.payload) for r in db.scalars(select(ReleaseEvent).where(ReleaseEvent.id>after).order_by(ReleaseEvent.id).limit(100))]


@router.get('/boxes/{box_id}')
def box_get(box_id: str, db: Session = Depends(get_db)):
    record = db.get(BoxSlot,box_id)
    if not record:
        raise HTTPException(404,'Released box slot not found')
    return {c.name:getattr(record,c.name) for c in BoxSlot.__table__.columns}


def export_data(db,plan_id,scope,deck,position):
    record = plan_record(db,plan_id)
    plan = read_plan(record)
    result = pack_plan(plan,resolve_aircraft(db,plan))
    if scope != 'aircraft' and deck not in ('main','lower'):
        raise HTTPException(422,'Select a deck for this scope')
    if scope == 'position' and not any(p['deck']==deck and p['position']==position for p in result['positions']):
        raise HTTPException(422,'Select a valid position')
    positions = [p for p in result['positions'] if p['boxes'] and (scope=='aircraft' or p['deck']==deck) and (scope!='position' or p['position']==position)]
    return plan,result,positions,[b for p in positions for b in p['boxes']]


Scope = Literal['aircraft','deck','position']


@router.get('/plans/{plan_id}/labels.pdf')
def labels(plan_id: str, scope: Scope = 'aircraft', deck: str | None = None, position: str | None = None,
           format: Literal['letter10','a4-8','4x6'] = 'letter10', db: Session = Depends(get_db)):
    plan,_,_,boxes = export_data(db,plan_id,scope,deck,position)
    return Response(labels_pdf(plan,boxes,format),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="cargo-labels.pdf"'})


@router.get('/plans/{plan_id}/workorder.pdf')
def workorder(plan_id: str, scope: Scope = 'aircraft', deck: str | None = None, position: str | None = None, db: Session = Depends(get_db)):
    plan,result,positions,_ = export_data(db,plan_id,scope,deck,position)
    if not plan.manifest.leader.strip():
        raise HTTPException(422,'Loader team leader name is required for a work order')
    return Response(workorder_pdf(plan,result,positions),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="cargo-workorder.pdf"'})


@router.get('/plans/{plan_id}/boxes.csv')
def csv_export(plan_id: str, scope: Scope = 'aircraft', deck: str | None = None, position: str | None = None, db: Session = Depends(get_db)):
    _,_,_,boxes = export_data(db,plan_id,scope,deck,position)
    return Response(boxes_csv(boxes),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="cargo-boxes.csv"'})


@router.post('/workorder/preview')
def preview(body: Plan, db: Session = Depends(get_db)):
    result = pack_plan(body,resolve_aircraft(db,body))
    return [dict(deck=p['deck'],position=p['position'],steps=build_steps(p)) for p in result['positions'] if p['boxes']]
