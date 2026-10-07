"""The cache of DIAN lookups, in the app's own SQLite database (models.DianTariffCache / DianCodeAlias).

What is stored: the normalized result of a successful lookup, keyed `DIAN:{resolvedHsCode}:{consultationDate}:v{schemaVersion}`, plus an alias
from the typed code to the resolved one. What is NEVER stored: errors, `selection_required`, and results whose parsing produced warnings.
`ivaStatus: "not_listed"` is stored only when the provider marked the result cacheable (the page was recognized and the Gravamen was found).
"""

import json
import os
from datetime import datetime, timedelta, timezone

from .dian_types import SCHEMA_VERSION

# how long a cached result may be served; DIAN changes rates rarely, but not never
DEFAULT_TTL_HOURS = 24


def ttl_hours() -> float:
    try:
        return float(os.environ.get('DIAN_CACHE_TTL_HOURS', DEFAULT_TTL_HOURS))
    except ValueError:
        return DEFAULT_TTL_HOURS


def cache_key(resolved_hs_code: str, consultation_date: str, schema_version: int = SCHEMA_VERSION) -> str:
    return f'DIAN:{resolved_hs_code}:{consultation_date}:v{schema_version}'


def is_cacheable(result: dict, parse_warnings: int = 0) -> bool:
    """Only a clean success is cached."""
    return result.get('status') == 'ok' and parse_warnings == 0


class TariffCache:
    def __init__(self, session_factory=None):
        if session_factory is None:
            from ... import models
            from ...database import Base, SessionLocal, engine

            # the cache tables are created with the rest at backend start; make sure they exist for scripts and tests too
            Base.metadata.create_all(bind=engine, tables=[models.DianTariffCache.__table__, models.DianCodeAlias.__table__])
            session_factory = SessionLocal
        self._session_factory = session_factory

    def _models(self):
        from ... import models

        return models

    def get(self, resolved_hs_code: str, consultation_date: str, now: datetime | None = None) -> dict | None:
        models = self._models()
        with self._session_factory() as db:
            row = db.get(models.DianTariffCache, cache_key(resolved_hs_code, consultation_date))
            if row is None:
                return None
            now = now or datetime.now(timezone.utc)
            if datetime.fromisoformat(row.retrieved_at) + timedelta(hours=ttl_hours()) < now:
                return None
            return json.loads(row.payload_json)

    def resolve_alias(self, input_hs_code: str, consultation_date: str) -> str | None:
        models = self._models()
        with self._session_factory() as db:
            row = db.get(models.DianCodeAlias, (input_hs_code, consultation_date, SCHEMA_VERSION))
            return row.resolved_hs_code if row else None

    def put(self, input_hs_code: str, result: dict, now: datetime | None = None) -> None:
        models = self._models()
        resolved = result['query']['resolvedHsCode']
        date = result['query']['consultationDate']
        retrieved = (now or datetime.now(timezone.utc)).isoformat()
        with self._session_factory() as db:
            db.merge(
                models.DianTariffCache(
                    cache_key=cache_key(resolved, date),
                    resolved_hs_code=resolved,
                    consultation_date=date,
                    schema_version=SCHEMA_VERSION,
                    payload_json=json.dumps(result, ensure_ascii=False),
                    source_url=(result.get('source') or {}).get('mainPageUrl'),
                    retrieved_at=retrieved,
                )
            )
            db.merge(models.DianCodeAlias(input_hs_code=input_hs_code, consultation_date=date, schema_version=SCHEMA_VERSION, resolved_hs_code=resolved))
            if input_hs_code != resolved:
                db.merge(models.DianCodeAlias(input_hs_code=resolved, consultation_date=date, schema_version=SCHEMA_VERSION, resolved_hs_code=resolved))
            db.commit()

    def clear(self) -> None:
        models = self._models()
        with self._session_factory() as db:
            db.query(models.DianTariffCache).delete()
            db.query(models.DianCodeAlias).delete()
            db.commit()
