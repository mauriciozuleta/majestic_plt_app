from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime, ForeignKey, Float
from datetime import datetime, timezone
from ..database import Base


def now():
    return datetime.now(timezone.utc)


class AircraftRecord(Base):
    __tablename__ = 'packer_aircraft'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    notes = Column(String)
    decks = Column(JSON, nullable=False)
    wb = Column(JSON, nullable=False)
    builtin = Column(Boolean, default=False)
    # Inline aircraft are stored for FK integrity, but only explicit aircraft saves publish them to the catalogue.
    hidden = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now)


class PlanRecord(Base):
    __tablename__ = 'packer_plans'
    id = Column(String, primary_key=True)
    company_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    aircraft_id = Column(String, ForeignKey('packer_aircraft.id'), nullable=False)
    aircraft = Column(JSON)
    box_types = Column(JSON)
    alloc = Column(JSON)
    settings = Column(JSON)
    manifest = Column(JSON)
    version = Column(Integer, default=1)
    released_result = Column(JSON)
    released_plan = Column(JSON)
    updated_at = Column(DateTime, default=now, onupdate=now)


class BoxSlot(Base):
    __tablename__ = 'packer_box_slots'
    box_id = Column(String, primary_key=True)
    plan_id = Column(String, ForeignKey('packer_plans.id'), index=True, nullable=False)
    deck = Column(String)
    position = Column(String)
    layer = Column(Integer)
    slot = Column(Integer)
    box_type = Column(String)
    x = Column(Float)
    y = Column(Float)
    z = Column(Float)
    dx = Column(Float)
    dy = Column(Float)
    dz = Column(Float)
    actual_kg = Column(Float)
    volume_kg = Column(Float)
    chargeable_kg = Column(Float)
    leans = Column(Boolean)
    created_at = Column(DateTime, default=now)


class ReleaseEvent(Base):
    """Durable integration outbox, readable by consumers after a release."""
    __tablename__ = 'packer_release_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=now)
