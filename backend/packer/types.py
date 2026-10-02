"""Engine-only types: no Pydantic, database or HTTP dependencies."""
from typing import Literal, TypedDict, NotRequired

ContourPoints = list[tuple[float, float]] | list[list[float]]


class PackItem(TypedDict):
    type_index: int
    l: float
    w: float
    h: float
    kg: float
    upright: bool
    max_layers: int
    qty: int | None


class PackOptions(TypedDict):
    L: float
    side_clearance: float
    end_clearance: float
    max_kg: float
    min_support: float
    interlock: bool
    order: Literal['heavy', 'space']
    strict: bool
    lean: NotRequired[bool]
    lean_min: NotRequired[float]
    container: NotRequired[bool]


class PlacedBox(TypedDict):
    type_index: int
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float
    layer: int
    kind: Literal['main', 'fill']
    leans: bool


class Fill(TypedDict):
    where: str
    boxes: list[PlacedBox]


class Layer(TypedDict):
    no: int
    z: float
    h: float
    type_index: int
    main: list[PlacedBox]
    fills: list[Fill]


class PackResult(TypedDict):
    boxes: list[PlacedBox]
    layers: list[Layer]
    kg: float
    height: float
