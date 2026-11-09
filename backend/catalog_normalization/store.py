"""Where researched item weights are kept. `ItemWeightStore` is the small interface the service needs; `MemoryStore` serves tests and one-off runs,
`DbStore` persists to models.CatalogItemWeight so a product is researched once for the whole app."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ItemWeight:
    product: str
    count_unit: str  # 'each' | 'bunch' | 'head' | 'sleeve' | 'dozen' | 'pack'
    item_kg: float | None  # typical weight of ONE item
    item_kg_min: float | None = None
    item_kg_max: float | None = None
    std_pack_kg: float | None = None
    std_pack_items: float | None = None
    confidence: str | None = None
    note: str = ''
    sources: list[str] = field(default_factory=list)
    researched_at: str = ''


def product_key(name: str) -> str:
    """Canonical product name used as the cache key: lowercase, no accents, no brand/size noise in parentheses, single spaces."""
    text = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'[^a-z0-9, ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


PRICED_UNIT = 'priced_unit'  # the weight of the WHOLE priced unit of one exact catalog row ("Pimento (S)" sold as a 100's bag), keyed by the exact name


def signature(name: str, count_unit: str) -> str:
    if count_unit == PRICED_UNIT:
        return f"{(name or '').strip().lower()}|{PRICED_UNIT}"  # parentheses are part of the name: "(s)" and "(20lb)" are different packs
    return f'{product_key(name)}|{count_unit}'


class MemoryStore:
    def __init__(self):
        self.rows: dict[str, ItemWeight] = {}

    def get(self, name: str, count_unit: str) -> ItemWeight | None:
        return self.rows.get(signature(name, count_unit))

    def put(self, weight: ItemWeight) -> None:
        if not weight.researched_at:
            weight.researched_at = datetime.now(timezone.utc).isoformat()
        self.rows[signature(weight.product, weight.count_unit)] = weight


class DbStore:
    """Backed by models.CatalogItemWeight; `session` is a SQLAlchemy session (the caller commits through it)."""

    def __init__(self, session):
        self.session = session

    def get(self, name: str, count_unit: str) -> ItemWeight | None:
        from .. import models

        row = self.session.query(models.CatalogItemWeight).filter_by(signature=signature(name, count_unit)).first()
        if row is None:
            return None
        return ItemWeight(row.product, row.count_unit, row.item_kg, row.item_kg_min, row.item_kg_max, row.std_pack_kg, row.std_pack_items, row.confidence,
                          row.note or '', json.loads(row.sources_json or '[]'), row.researched_at)

    def put(self, weight: ItemWeight) -> None:
        from .. import models

        weight.researched_at = weight.researched_at or datetime.now(timezone.utc).isoformat()
        sig = signature(weight.product, weight.count_unit)
        row = self.session.query(models.CatalogItemWeight).filter_by(signature=sig).first() or models.CatalogItemWeight(signature=sig)
        row.product, row.count_unit = (weight.product.strip().lower() if weight.count_unit == PRICED_UNIT else product_key(weight.product)), weight.count_unit
        row.item_kg, row.item_kg_min, row.item_kg_max = weight.item_kg, weight.item_kg_min, weight.item_kg_max
        row.std_pack_kg, row.std_pack_items = weight.std_pack_kg, weight.std_pack_items
        row.confidence, row.note, row.sources_json, row.researched_at = weight.confidence, weight.note, json.dumps(weight.sources), weight.researched_at
        self.session.add(row)
        self.session.commit()
