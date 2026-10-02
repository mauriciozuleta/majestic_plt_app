import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.models import Company, LogisticsAircraft, CharterProvider
from backend.aircraft_catalog import migrate_aircraft_to_cargo
from backend.routers.air_logistics import AircraftIn, CharterProviderIn, create_aircraft, create_charter_provider, list_aircraft, delete_aircraft, FleetSelectionIn, add_to_fleet


class FleetCatalogueTests(unittest.TestCase):
    def test_move_preserves_provider_links_and_company_scope(self):
        engine = create_engine('sqlite://')
        for model in (Company, LogisticsAircraft, CharterProvider):
            model.__table__.create(engine)
        with Session(engine) as db:
            for id, name in [('fresh', 'FRESH24'), ('cargo', 'Majestic Cargo'), ('other', 'FRESH24-Colombia')]:
                db.add(Company(id=id, name=name, company_type='test', company_dependency='test', accent_from='#000', accent_to='#000'))
            payload = AircraftIn(manufacturer='Test', model='A1', short_name='A1', mtow_kg=1000,
                                 empty_weight_kg=400, max_payload_kg=300, zero_fuel_kg=700,
                                 fuel_capacity_gal=100, fuel_burn_gal_hr=20, cargo_positions_main_deck=2,
                                 cargo_positions_lower_deck=0, cruise_speed_kt=200)
            db.add(LogisticsAircraft(id='legacy', company_id='fresh', created_at='test', in_fleet=True, **payload.model_dump()))
            db.add(CharterProvider(id='existing-provider',company_id='fresh',created_at='test',name='Existing',
                                  country_name='US',main_base_iata='MIA',aircraft_id='legacy',block_hour_cost=100,provider_type='charter'))
            db.commit()
        with engine.begin() as connection:
            migrate_aircraft_to_cargo(connection)
            migrate_aircraft_to_cargo(connection)
        with Session(engine) as db:
            self.assertEqual(db.get(LogisticsAircraft, 'legacy').company_id, 'cargo')
            self.assertEqual(db.get(CharterProvider, 'existing-provider').aircraft_id, 'legacy')
            self.assertEqual([a.id for a in list_aircraft('fresh',db)], ['legacy'])
            self.assertEqual([a.id for a in list_aircraft('cargo',db)], ['legacy'])
            self.assertEqual(list_aircraft('other',db), [])
            aircraft = create_aircraft('cargo',payload,db)
            add_to_fleet('cargo',FleetSelectionIn(aircraft_ids=[aircraft.id]),db)
            provider = CharterProviderIn(name='New',country_name='US',main_base_iata='MIA',aircraft_id=aircraft.id,block_hour_cost=100,provider_type='charter')
            create_charter_provider('fresh',provider,db)
            with self.assertRaises(HTTPException) as error:
                create_charter_provider('other',provider,db)
            self.assertEqual(error.exception.status_code,400)
            with self.assertRaises(HTTPException) as error:
                delete_aircraft('cargo',aircraft.id,db)
            self.assertEqual(error.exception.status_code,400)
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
