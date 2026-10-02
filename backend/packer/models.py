from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .geometry import validate

Positive = Annotated[float, Field(gt=0, le=10000)]
Nonnegative = Annotated[float, Field(ge=0)]


class Model(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')


class Contour(Model):
    name: str = 'Contour (estimate)'
    points: list[tuple[Nonnegative, Nonnegative]] = Field(min_length=2, max_length=100)

    @model_validator(mode='after')
    def valid(self):
        validate(self.points)
        return self


class Position(Model):
    id: str = Field(min_length=1, max_length=30)
    arm: float | None = None
    max_kg: Nonnegative = 1134
    contour: str | None = None


class Door(Model):
    width: Positive
    height: Positive


class Deck(Model):
    uld: str
    kind: Literal['pallet', 'container']
    position_length_cm: Positive
    door: Door | None = None
    contours: dict[str, Contour]
    default_contour: str
    positions: list[Position] = Field(default_factory=list, max_length=60)

    @model_validator(mode='after')
    def valid(self):
        if self.default_contour not in self.contours:
            raise ValueError('Default contour must exist')
        ids = [p.id for p in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate position ids')
        if any(p.contour and p.contour not in self.contours for p in self.positions):
            raise ValueError('Position contour override must exist')
        return self


class Wb(Model):
    max_payload_kg: Nonnegative = 28000
    dow_kg: Nonnegative | None = None
    dow_arm_m: float | None = None
    lemac_m: float | None = None
    mac_m: Positive | None = None
    fwd_limit_pct_mac: float | None = None
    aft_limit_pct_mac: float | None = None

    @model_validator(mode='after')
    def limits(self):
        if self.fwd_limit_pct_mac is not None and self.aft_limit_pct_mac is not None and self.fwd_limit_pct_mac > self.aft_limit_pct_mac:
            raise ValueError('Forward CG limit must not exceed aft limit')
        return self


class Aircraft(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    notes: str = ''
    decks: dict[Literal['main', 'lower'], Deck]
    wb: Wb = Field(default_factory=Wb)
    builtin: bool = False

    @model_validator(mode='after')
    def both_decks(self):
        if set(self.decks) != {'main', 'lower'}:
            raise ValueError('Aircraft must define main and lower decks (positions may be empty)')
        return self


class BoxType(Model):
    name: str = Field(min_length=1, max_length=100)
    l: Annotated[float, Field(ge=5, le=1000)]
    w: Annotated[float, Field(ge=5, le=1000)]
    h: Annotated[float, Field(ge=5, le=1000)]
    kg: Nonnegative
    max_layers: int = Field(default=30, ge=1, le=300)
    upright: bool = True


class Allocation(Model):
    on: bool = False
    qty: int | None = Field(default=None, ge=0, le=100000)


class DeckSettings(Model):
    side_clearance: Nonnegative = 2.5
    end_clearance: Nonnegative = 1
    lean: bool = False
    lean_min_support: float = Field(default=50, ge=0, le=100)


class Settings(Model):
    divisor: Positive = 6000
    min_support: float = Field(default=80, ge=1, le=100)
    interlock: bool = True
    order: Literal['heavy', 'space'] = 'heavy'
    strict_density: bool = True
    id_prefix: str = Field(default='BOX-', min_length=1, max_length=30, pattern=r'^[A-Za-z0-9_-]+$')
    id_digits: int = Field(default=4, ge=1, le=10)
    label_format: Literal['letter10', 'a4-8', '4x6'] = 'letter10'
    main: DeckSettings = Field(default_factory=DeckSettings)
    lower: DeckSettings = Field(default_factory=lambda: DeckSettings(side_clearance=3, end_clearance=3, lean=True))


class Manifest(Model):
    leader: str = ''
    flight: str = ''
    registration: str = ''
    date: str = ''
    notes: str = ''


class Plan(Model):
    id: str | None = None
    company_id: str
    name: str = Field(default='New load plan', min_length=1, max_length=200)
    aircraft_id: str = 'a321p2f'
    aircraft: Aircraft | None = None
    box_types: list[BoxType] = Field(default_factory=list, max_length=50)
    alloc: dict[Literal['main', 'lower'], dict[str, dict[str, Allocation]]] = Field(default_factory=dict)
    settings: Settings = Field(default_factory=Settings)
    manifest: Manifest = Field(default_factory=Manifest)
    version: int = 0
