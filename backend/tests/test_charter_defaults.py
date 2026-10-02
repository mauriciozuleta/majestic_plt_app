import unittest
from sqlalchemy import create_engine, text, inspect
from backend.charter_defaults import migrate_provider_fields


class ProviderMigrationTests(unittest.TestCase):
    def test_nullable_migration_preserves_rows_and_indexes(self):
        engine = create_engine('sqlite://')
        with engine.begin() as db:
            db.execute(text('CREATE TABLE charter_providers (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, main_base_iata VARCHAR NOT NULL, block_hour_cost FLOAT NOT NULL)'))
            db.execute(text('CREATE INDEX provider_name ON charter_providers(name)'))
            db.execute(text("INSERT INTO charter_providers VALUES ('existing','Operator','MIA',1234)"))
            migrate_provider_fields(db)
            migrate_provider_fields(db)
            self.assertEqual(tuple(db.execute(text('SELECT id,name,main_base_iata,block_hour_cost FROM charter_providers')).one()),('existing','Operator','MIA',1234))
            db.execute(text("INSERT INTO charter_providers (id,name) VALUES ('new','Majestic Cargo')"))
            self.assertIn('provider_name',[i['name'] for i in inspect(db).get_indexes('charter_providers')])
        engine.dispose()
