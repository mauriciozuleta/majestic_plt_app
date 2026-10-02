import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.database import get_db
from backend.models import Company, LogisticsAircraft, CharterProvider
from backend.routers.air_logistics import router, AircraftIn
from backend.import_aircraft_database import import_aircraft, RENAMED


class FleetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        for model in (Company,LogisticsAircraft,CharterProvider):
            model.__table__.create(self.engine)
        with Session(self.engine) as db:
            for id,name in [('cargo','Majestic Cargo'),('fresh','FRESH24'),('other','Other')]:
                db.add(Company(id=id,name=name,company_type='test',company_dependency='test',accent_from='#000',accent_to='#000'))
            db.commit()
        def session():
            with Session(self.engine) as db:
                yield db
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = session
        self.client = TestClient(app)
        self.base = '/companies/cargo/air-logistics'
        self.payload = AircraftIn(manufacturer='Test',model='Model',short_name='T1',mtow_kg=1000,
            empty_weight_kg=400,max_payload_kg=300,zero_fuel_kg=700,fuel_capacity_gal=100,
            fuel_burn_gal_hr=20,cargo_positions_main_deck=2,cargo_positions_lower_deck=0,
            cruise_speed_kt=200,max_range_at_max_payload_nm=1234).model_dump()

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def create(self,company='cargo'):
        response = self.client.post(f'/companies/{company}/air-logistics/aircraft',json=self.payload)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_fleet_selection_and_full_catalogue_provider_assignment(self):
        a,b = self.create(),self.create()
        self.assertFalse(a['in_fleet'])
        self.assertEqual(len(self.client.get(self.base+'/aircraft-catalogue').json()),2)
        fresh = '/companies/fresh/air-logistics'
        self.assertEqual(self.client.get(fresh+'/aircraft').json(),[])
        provider = dict(name='Charter',country_name='US',main_base_iata='MIA',aircraft_id=a['id'],block_hour_cost=50,provider_type='charter')
        created = self.client.post(fresh+'/charter-providers',json=provider)
        self.assertEqual(created.status_code,200,created.text)
        self.assertEqual(created.json()['aircraft_id'],a['id'])
        self.assertEqual(self.client.get(fresh+'/aircraft').json(),[])
        self.assertEqual(self.client.delete(fresh+'/charter-providers/'+created.json()['id']).status_code,204)
        response = self.client.post(self.base+'/fleet',json={'aircraft_ids':[a['id'],b['id']]})
        self.assertEqual(response.status_code,200,response.text)
        defaults = self.client.get(fresh+'/charter-providers').json()
        self.assertEqual(len(defaults),2)
        self.assertTrue(all(p['name']=='Majestic Cargo' and p['source_company_id']=='cargo' and p['block_hour_cost'] is None for p in defaults))
        self.assertEqual({x['id'] for x in self.client.get(fresh+'/aircraft').json()},{a['id'],b['id']})
        self.assertEqual(self.client.post(self.base+'/fleet',json={'aircraft_ids':[a['id'],a['id']]}).status_code,200)
        self.assertEqual(len(self.client.get(fresh+'/charter-providers').json()),2)
        self.assertEqual(self.client.post(fresh+'/charter-providers',json=provider).status_code,200)
        self.assertEqual(self.client.delete(self.base+'/fleet/'+a['id']).status_code,409)
        self.assertEqual(self.client.delete(self.base+'/aircraft/'+a['id']).status_code,400)
        self.assertEqual(self.client.delete(self.base+'/fleet/'+b['id']).status_code,409)
        default_b = next(p for p in defaults if p['aircraft_id']==b['id'])
        self.assertEqual(self.client.delete(fresh+'/charter-providers/'+default_b['id']).status_code,204)
        self.assertEqual(self.client.delete(self.base+'/fleet/'+b['id']).status_code,204)
        self.assertEqual(len(self.client.get(self.base+'/aircraft-catalogue').json()),2)
        self.assertEqual([x['id'] for x in self.client.get(fresh+'/aircraft').json()],[a['id']])
        edited = {**self.payload,'short_name':'Updated'}
        self.assertEqual(self.client.put(self.base+'/aircraft/'+a['id'],json=edited).status_code,200)
        self.assertEqual(self.client.get(fresh+'/aircraft').json()[0]['short_name'],'Updated')

    def test_invalid_selection_is_atomic_and_scoped(self):
        own,other = self.create(),self.create('other')
        for ids in [[],[own['id'],'missing'],[own['id'],other['id']]]:
            response = self.client.post(self.base+'/fleet',json={'aircraft_ids':ids})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.client.get(self.base+'/aircraft').json(),[])
        self.assertEqual(self.client.delete(self.base+'/fleet/'+other['id']).status_code,404)

    def test_readonly_import_maps_fields_and_preserves_original_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'db.sqlite3'
            row = {RENAMED.get(k,k):v for k,v in self.payload.items()}
            row.update(id=1,aircraft_id='ACFT01',mtow_lbs=2204.62,fuel_burn_lbs=134)
            with closing(sqlite3.connect(source)) as db:
                db.execute('CREATE TABLE main_aircraft ('+', '.join(row)+')')
                db.execute('INSERT INTO main_aircraft VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
                db.commit()
            before = source.read_bytes()
            with Session(self.engine) as db:
                first = import_aircraft(db,source,'cargo')
                db.commit()
                imported = db.get(LogisticsAircraft,first['imported'][0])
                self.assertEqual(imported.fuel_burn_gal_hr,20)
                self.assertEqual(imported.cruise_speed_kt,200)
                self.assertEqual(imported.max_range_at_max_payload_nm,1234)
                self.assertEqual(imported.source_data['record']['mtow_lbs'],2204.62)
                self.assertFalse(imported.in_fleet)
                imported.short_name='Local edit'
                db.commit()
                second=import_aircraft(db,source,'cargo')
                db.commit()
                self.assertEqual(second['imported'],[])
                self.assertEqual(len(second['skipped']),1)
                self.assertEqual(imported.short_name,'Local edit')
            self.assertEqual(source.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
