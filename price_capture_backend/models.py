from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .database import Base


class Capture(Base):
    __tablename__ = 'captures'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    domain = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    price = Column(String, nullable=False)
    unit = Column(String, nullable=True)
    country = Column(String, nullable=False)
    supermarket_name = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    captured_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
