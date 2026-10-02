from math import floor


def variants(w, length, a, b):
    result = []
    for k in range(floor(w / a + 1e-9) + 1):
        r1 = floor(length / b + 1e-9)
        n2 = floor((w - k * a) / b + 1e-9)
        r2 = floor(length / a + 1e-9)
        count = k * r1 + n2 * r2
        if count:
            result.append(dict(k=k, r1=r1, n2=n2, r2=r2, a=a, b=b, count=count))
    return sorted(result, key=lambda v: -v['count'])


def cells_of(v):
    a, b = v['a'], v['b']
    return ([dict(x=c*a, y=r*b, dx=a, dy=b) for c in range(v['k']) for r in range(v['r1'])] +
            [dict(x=v['k']*a+c*b, y=r*a, dx=b, dy=a) for c in range(v['n2']) for r in range(v['r2'])])


def extent(cells):
    return max(c['x'] + c['dx'] for c in cells), max(c['y'] + c['dy'] for c in cells)
