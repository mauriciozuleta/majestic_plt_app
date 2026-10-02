import unittest
from io import BytesIO
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.database import get_db
from backend.routers.packer import router
from backend.packer.tables import AircraftRecord, PlanRecord, BoxSlot, ReleaseEvent
from backend.packer.models import Plan
from backend.packer.ai_draft import parse_draft
from backend.packer.suggest import SuggestRequest
import pdfplumber


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        for table in [AircraftRecord,PlanRecord,BoxSlot,ReleaseEvent]:
            table.__table__.create(self.engine)
        self.session = sessionmaker(bind=self.engine)
        def db():
            with self.session() as session:
                yield session
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = db
        self.client = TestClient(app)
        self.plan = Plan(company_id='test',box_types=[dict(name='Produce',l=60,w=40,h=25,kg=14)],alloc={'main':{'P1':{'0':{'on':True,'qty':5}}}}).model_dump(mode='json')

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def save(self,plan=None):
        response = self.client.post('/api/packer/plans',json=plan or self.plan)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_save_release_exports(self):
        barcode = self.client.post('/api/packer/barcodes',json={'ids':['BOX-0001']})
        self.assertEqual(barcode.status_code,200)
        self.assertIn('<svg',barcode.json()['BOX-0001'])
        saved = self.save()
        plan_id = saved['id']
        with self.session() as db:
            self.assertEqual(list(db.scalars(select(BoxSlot))),[])
        self.assertEqual(self.client.get(f'/api/packer/plans/{plan_id}/workorder.pdf').status_code,422)
        saved['manifest']['leader'] = 'Test Leader'
        saved = self.save(saved)
        for format in ['letter10','a4-8','4x6']:
            pdf = self.client.get(f'/api/packer/plans/{plan_id}/labels.pdf?format={format}')
            self.assertEqual(pdf.status_code,200)
            self.assertTrue(pdf.content.startswith(b'%PDF'))
        pdf = self.client.get(f'/api/packer/plans/{plan_id}/workorder.pdf')
        with pdfplumber.open(BytesIO(pdf.content)) as doc:
            self.assertEqual(len(doc.pages),2)
            self.assertIn('Test Leader',doc.pages[0].extract_text())
            self.assertIn('BOX-0001',doc.pages[1].extract_text())
        csv = self.client.get(f'/api/packer/plans/{plan_id}/boxes.csv')
        self.assertIn('BOX-0001',csv.text)
        release = self.client.post(f'/api/packer/plans/{plan_id}/release',json={})
        self.assertEqual(release.status_code,200,release.text)
        self.assertEqual(self.client.get('/api/packer/boxes/BOX-0001').json()['position'],'P1')
        self.assertEqual(self.client.post(f'/api/packer/plans/{plan_id}/release',json={}).json()['box_ids'],release.json()['box_ids'])
        self.assertEqual(len(self.client.get('/api/packer/events').json()),2)
        saved['alloc']['main']['P1']['0']['qty'] = 3
        saved = self.save(saved)
        self.assertEqual(self.client.get('/api/packer/boxes/BOX-0005').status_code,200)
        response = self.client.post(f'/api/packer/plans/{plan_id}/release',json={})
        self.assertEqual(response.status_code,409)
        self.assertIn('reprint',response.text)
        self.assertEqual(self.client.post(f'/api/packer/plans/{plan_id}/release',json={'confirm_reassign':True}).status_code,200)
        self.assertEqual(self.client.get('/api/packer/boxes/BOX-0005').status_code,404)

    def test_invalid_input_conflicts_and_scopes(self):
        self.client.get('/api/packer/aircraft')
        self.assertEqual(self.client.delete('/api/packer/aircraft/a321p2f').status_code,422)
        saved = self.save()
        stale = dict(saved)
        self.save(saved)
        self.assertEqual(self.client.post('/api/packer/plans',json=stale).status_code,409)
        self.assertEqual(self.client.get(f"/api/packer/plans/{saved['id']}/labels.pdf?scope=position").status_code,422)
        self.assertEqual(self.client.post(f"/api/packer/plans/{saved['id']}/release",json={}).status_code,200)
        other = self.save()
        self.assertEqual(self.client.post(f"/api/packer/plans/{other['id']}/release",json={}).status_code,409)
        self.plan['box_types'][0]['l'] = 0
        self.assertEqual(self.client.post('/api/packer/pack',json=self.plan).status_code,422)

    def test_suggest_and_ai_parse(self):
        body = dict(plan=self.plan,deck='main',position='P1',l={'minimum':60,'maximum':60},w={'minimum':40,'maximum':40},h={'minimum':25,'maximum':25},density=200,max_kg=25)
        response = self.client.post('/api/packer/suggest',json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()[0]['l'],60)
        body.update(step=.1,l={'minimum':5,'maximum':1000})
        body['w']['maximum'] = 1000
        self.assertEqual(self.client.post('/api/packer/suggest',json=body).status_code,422)
        raw = dict(name='Draft',notes='Estimate',maxPayloadKg=1000,lemacM='unknown',main=dict(uld='Test',kind='pallet',positionLengthCm=150,
                   contour=[[100,80],['bad',2],[20,120]],positions=[dict(id='P1',armM=None,maxKg=500)]),lower=None)
        draft = parse_draft(raw,'Test aircraft')
        self.assertEqual(draft.decks['main'].contours['draft'].points[0],(0,120))
        self.assertIsNone(draft.wb.lemac_m)
        self.assertTrue(draft.notes.startswith("Drafted by AI for 'Test aircraft'"))

    def test_inline_aircraft_is_not_published(self):
        aircraft = self.client.get('/api/packer/aircraft').json()[0]
        aircraft.update(id='private-aircraft',name='Reviewed draft',builtin=False)
        self.plan.update(aircraft_id=aircraft['id'],aircraft=aircraft)
        saved = self.save()
        self.assertEqual(saved['aircraft_id'],'private-aircraft')
        self.assertNotIn('private-aircraft',[a['id'] for a in self.client.get('/api/packer/aircraft').json()])
        self.assertEqual(self.client.put('/api/packer/aircraft/private-aircraft',json=aircraft).status_code,200)
        self.assertIn('private-aircraft',[a['id'] for a in self.client.get('/api/packer/aircraft').json()])


if __name__ == '__main__':
    unittest.main()
