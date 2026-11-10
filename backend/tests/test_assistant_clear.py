import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models, modification_reports
from backend.database import Base, get_db
from backend.routers import assistant, knowledge_base


class ClearAssistantChatTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        reports = Path(self.tmp.name) / 'reports'
        for patch in [
            mock.patch.object(modification_reports, 'REPORTS_DIR', reports),
            mock.patch.object(knowledge_base, 'MODIFICATION_REPORTS_DIR', reports),
            mock.patch.object(knowledge_base.rag, 'KNOWLEDGE_BASE_DIR', Path(self.tmp.name) / 'kb'),
            mock.patch.object(knowledge_base.rag, 'rag_path', lambda doc_id: Path(self.tmp.name) / 'kb' / f'{doc_id}.rag.json'),
        ]:
            patch.start()
            self.addCleanup(patch.stop)
        self.reports = reports
        with self.Session() as db:
            db.add(models.AssistantMessage(id='m1', sender='user', text='Which countries are active?', sources_json=None, created_at='2026-11-09T10:00:00+00:00'))
            db.add(models.AssistantMessage(id='m2', sender='bot', text='Jamaica\nand Colombia', sources_json='["Business plan.pdf"]', created_at='2026-11-09T10:00:05+00:00'))
            db.commit()
        app = FastAPI()
        app.include_router(assistant.router)

        def override():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

    def test_clearing_saves_the_whole_conversation_as_a_report_and_empties_the_log(self):
        result = self.client.post('/assistant/messages/clear', json={'cleared_by': 'Ana'}).json()
        self.assertEqual(result['removed'], 2)
        self.assertEqual(self.client.get('/assistant/messages').json(), [])
        report = (self.reports / result['report']).read_text(encoding='utf-8')
        self.assertIn('Done by:** Ana', report)
        self.assertIn('> Which countries are active?', report)
        self.assertIn('> Jamaica', report)
        self.assertIn('> and Colombia', report)
        self.assertIn('Business plan.pdf', report)
        with self.Session() as db:
            documents = db.query(models.KnowledgeDocument).all()
        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0].report_key.startswith('modification_report:'))
        self.assertIn('chat cleared (2 messages)', documents[0].name)

    def test_an_empty_chat_is_refused_and_writes_nothing(self):
        self.client.post('/assistant/messages/clear', json={})
        self.assertEqual(self.client.post('/assistant/messages/clear', json={}).status_code, 400)
        self.assertEqual(len(list(self.reports.glob('*.md'))), 1)


if __name__ == '__main__':
    unittest.main()
