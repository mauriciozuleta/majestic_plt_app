import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from .. import schemas

router = APIRouter()


def _ensure_company_sort_indexes(db: Session, company_id: str):
    tasks = db.query(models.RoadmapTask).filter_by(company_id=company_id).order_by(models.RoadmapTask.sort_index.asc(), models.RoadmapTask.id.asc()).all()
    if not tasks:
        return

    seen = set()
    has_duplicate_or_missing = False
    for task in tasks:
        key = float(task.sort_index or 0.0)
        if key in seen:
            has_duplicate_or_missing = True
            break
        seen.add(key)

    if not has_duplicate_or_missing:
        return

    for index, task in enumerate(tasks, start=1):
        task.sort_index = float(index)
    db.flush()


@router.get('/companies/{company_id}/roadmap-tasks', response_model=list[schemas.RoadmapTaskOut])
def list_tasks(company_id: str, db: Session = Depends(get_db)):
    _ensure_company_sort_indexes(db, company_id)
    db.commit()
    return db.query(models.RoadmapTask).filter_by(company_id=company_id).order_by(models.RoadmapTask.sort_index.asc(), models.RoadmapTask.id.asc()).all()


@router.post('/companies/{company_id}/roadmap-tasks', response_model=schemas.RoadmapTaskOut)
def create_task(company_id: str, task: schemas.RoadmapTaskCreate, db: Session = Depends(get_db)):
    payload = task.model_dump()
    requested_sort_index = payload.get('sort_index', 0.0)
    if requested_sort_index == 0.0:
        max_sort_index = db.query(models.RoadmapTask.sort_index).filter_by(company_id=company_id).order_by(models.RoadmapTask.sort_index.desc()).first()
        payload['sort_index'] = (max_sort_index[0] + 1.0) if max_sort_index and max_sort_index[0] is not None else 1.0

    db_task = models.RoadmapTask(id=str(uuid.uuid4()), company_id=company_id, **payload)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@router.patch('/roadmap-tasks/{task_id}', response_model=schemas.RoadmapTaskOut)
def update_task(task_id: str, updates: schemas.RoadmapTaskUpdate, db: Session = Depends(get_db)):
    db_task = db.query(models.RoadmapTask).filter_by(id=task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail='Task not found')

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_task, field, value)

    db.commit()
    db.refresh(db_task)
    return db_task


@router.delete('/roadmap-tasks/{task_id}')
def delete_task(task_id: str, db: Session = Depends(get_db)):
    db_task = db.query(models.RoadmapTask).filter_by(id=task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail='Task not found')

    db.delete(db_task)
    db.commit()
    return {'ok': True}
