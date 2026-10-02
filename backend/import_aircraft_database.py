"""Read-only AI_FRESH24 import located through graphify-out/graph.json.

Graph nodes: main_models_aircraft, main_forms_aircraftform,
main_views_routes_api_add_aircraft. Source table: main_aircraft.
"""
import argparse
from contextlib import closing
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from .models import Company, LogisticsAircraft
from .routers.air_logistics import AircraftIn, _clean_aircraft

RENAMED = {
    'fuel_burn_gal_hr': 'fuel_burn_gal',
    'cruise_speed_kt': 'cruise_speed',
    'max_range_at_max_payload_nm': 'max_range_at_max_payload',
    'max_range_with_max_fuel_nm': 'max_range_with_max_fuel',
}


def read_source(path: Path) -> list[dict]:
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as source:
        source.row_factory = sqlite3.Row
        return [dict(row) for row in source.execute('SELECT * FROM main_aircraft ORDER BY id')]


def import_aircraft(db: Session, source_path: Path, company_id: str) -> dict:
    if not db.get(Company,company_id):
        raise ValueError('Destination company does not exist')
    rows = read_source(source_path)
    imported, skipped = [], []
    for row in rows:
        source_id = f"AI_FRESH24:{row['aircraft_id']}"
        existing = db.query(LogisticsAircraft).filter_by(company_id=company_id,source_aircraft_id=source_id).first()
        if existing:
            skipped.append(existing.id)
            continue
        payload = AircraftIn.model_validate({key:row[RENAMED.get(key,key)] for key in AircraftIn.model_fields})
        record = LogisticsAircraft(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{company_id}/{source_id}')),
            company_id=company_id,in_fleet=False,source_aircraft_id=source_id,
            source_data={'database':str(source_path.resolve()),'table':'main_aircraft','record':row},
            created_at=datetime.now(timezone.utc).isoformat(),**_clean_aircraft(payload))
        db.add(record)
        imported.append(record.id)
    db.flush()
    return {'source_count':len(rows),'imported':imported,'skipped':skipped}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--company-id',required=True)
    args = parser.parse_args()
    from .database import SessionLocal
    with SessionLocal.begin() as session:
        result = import_aircraft(session,args.source,args.company_id)
    print(f"Imported {len(result['imported'])} aircraft; skipped {len(result['skipped'])} existing imports. No aircraft auto-selected.")
