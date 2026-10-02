from bisect import bisect_right
from .types import ContourPoints


def validate(points: ContourPoints) -> ContourPoints:
    if len(points) < 2 or points[0][0] != 0:
        raise ValueError('Contour needs at least two points and must start at height 0')
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError('Contour heights must strictly increase')
    if any(w < 0 for _, w in points) or not any(w > 0 for _, w in points):
        raise ValueError('Contour widths must be nonnegative with a positive width')
    return points


def width_at(points: ContourPoints, z: float) -> float:
    if z > points[-1][0]:
        return 0.0
    if z <= 0:
        return points[0][1]
    i = min(bisect_right([p[0] for p in points], z), len(points) - 1)
    (h0, w0), (h1, w1) = points[i - 1:i + 1]
    return w0 + (w1 - w0) * (z - h0) / (h1 - h0)


def min_width(points: ContourPoints, z0: float, z1: float) -> float:
    return min([width_at(points, z0), width_at(points, z1)] +
               [w for z, w in points if z0 < z < z1])


def area(points: ContourPoints) -> float:
    return sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(points, points[1:]))
