"""Deterministic layer packing, independent of HTTP and persistence."""
from math import floor, inf
from .blocks import variants, cells_of, extent
from .geometry import min_width, width_at
from .orient import orientations
from .types import PackItem, PackOptions, PackResult, ContourPoints


def density(item: PackItem) -> float:
    return item['kg'] * 1e6 / (item['l'] * item['w'] * item['h'])


def support(cell, z, tops, points, opts):
    if z == 0:
        return True, False
    overlap = sum(max(0, min(cell['x']+cell['dx'], b['x']+b['dx'])-max(cell['x'], b['x'])) *
                  max(0, min(cell['y']+cell['dy'], b['y']+b['dy'])-max(cell['y'], b['y']))
                  for b in tops.get(round(z, 2), []))
    ratio = overlap / (cell['dx'] * cell['dy'])
    if ratio + 1e-9 >= opts['min_support']:
        return True, False
    hw = width_at(points, z)/2 - opts['side_clearance']
    leans = (opts.get('lean', False) and ratio + 1e-9 >= opts.get('lean_min', .5) and
             width_at(points, z) > width_at(points, max(0, z-2)) + .05 and
             (cell['x'] <= -hw+3 or cell['x']+cell['dx'] >= hw-3))
    return leans, leans


def arrangements(vs, width, length, a, b, sup_w, z, layer, opts):
    choices = [(vs[0], False)]
    if z > 0 and sup_w < width - .5:
        narrow = variants(sup_w, length, a, b)
        if narrow:
            choices += [(narrow[0], False), (narrow[0], True)]
    if opts['interlock'] and layer % 2:
        choices.insert(0, (vs[0], True))
        alt = next((v for v in vs if v['k'] != vs[0]['k'] and v['count'] >= .95*vs[0]['count']), None)
        if alt:
            choices = [(alt, False), (alt, True)] + choices
    result = []
    for v, mirrored in choices:
        cells = cells_of(v)
        ew, el = extent(cells)
        if mirrored:
            cells = [dict(c, x=ew-c['x']-c['dx'], y=el-c['y']-c['dy']) for c in cells]
        result.append((cells, ew, el))
    if opts.get('lean') and z > 0:
        result += [([dict(c, x=c['x'] + (width-ew if c['x']+c['dx']/2 > ew/2 else 0)) for c in cells], width, el)
                   for cells, ew, el in result.copy()]
    return result


def pack_position(items: list[PackItem], opts: PackOptions, contour: ContourPoints) -> PackResult:
    length = opts['L'] - 2 * opts['end_clearance']
    boxes, layers, tops = [], [], {}
    remaining = {i['type_index']: i.get('qty') if i.get('qty') is not None else inf for i in items}
    counts = {i['type_index']: 0 for i in items}
    z, kg, min_below = 0.0, 0.0, inf

    def allow(item):
        n = remaining[item['type_index']]
        return min(n, floor((opts['max_kg'] - kg + 1e-9)/item['kg'])) if item['kg'] else n

    def eligible(item):
        return (allow(item) > 0 and counts[item['type_index']] < item['max_layers'] and
                (not opts['strict'] or density(item) <= min_below * 1.0001))

    def filtered(cells, item):
        accepted = []
        for c in cells:
            ok, lean = support(c, z, tops, contour, opts)
            if ok:
                accepted.append(dict(c, leans=lean))
                if len(accepted) >= allow(item):
                    break
        return accepted

    def place(cells, item, h, kind, layer):
        nonlocal kg
        placed = [dict(c, z=z, dz=h, type_index=item['type_index'], kind=kind, layer=layer) for c in cells]
        kg += len(placed)*item['kg']
        remaining[item['type_index']] -= len(placed)
        boxes.extend(placed)
        return placed

    if length <= 0:
        return dict(boxes=[], layers=[], kg=0, height=0)
    for layer_index in range(300):
        below = tops.get(round(z, 2), [])
        sup_w = 2*max((max(abs(b['x']), abs(b['x']+b['dx'])) for b in below), default=0) if z else inf
        candidates = []
        for item in items:
            if not eligible(item):
                continue
            for a, b, h in orientations(item):
                width = min_width(contour, z, z+h)-2*opts['side_clearance']
                if width <= 0:
                    continue
                vs = variants(width, length, a, b)
                if not vs:
                    continue
                best = None
                for cells, ew, el in arrangements(vs, width, length, a, b, sup_w, z, layer_index, opts):
                    cells = filtered([dict(c, x=c['x']-ew/2, y=c['y']-length/2) for c in cells], item)
                    if cells and (best is None or len(cells) > len(best['cells'])):
                        best = dict(cells=cells, ew=ew, el=el)
                if best:
                    candidates.append(dict(best, item=item, h=h, width=width,
                                           fill=len(best['cells'])*a*b/(width*length), volume=len(best['cells'])*a*b*h))
        if not candidates:
            break
        if opts['order'] == 'heavy':
            threshold = max(c['fill'] for c in candidates)*.85
            chosen = max((c for c in candidates if c['fill'] >= threshold), key=lambda c: (density(c['item']), c['fill'], c['volume']))
        else:
            chosen = max(candidates, key=lambda c: (c['fill'], c['volume']))
        h, width, ew, el = (chosen[k] for k in ('h', 'width', 'ew', 'el'))
        no = layer_index+1
        main = place(chosen['cells'], chosen['item'], h, 'main', no)
        layer = dict(no=no, z=z, h=h, type_index=chosen['item']['type_index'], main=main, fills=[])
        placed_layer = main.copy()
        strips = [('left edge strip', -width/2, -length/2, (width-ew)/2, length, False),
                  ('right edge strip', ew/2, -length/2, (width-ew)/2, length, True),
                  ('door end strip' if opts.get('container') else 'aft end strip', -ew/2, -length/2+el, ew, length-el, False)]
        for where, sx, sy, sw, sl, right in strips:
            if sw <= 0 or sl <= 0:
                continue
            best_fill = None
            for item in items:
                if not eligible(item):
                    continue
                for a, b, fh in orientations(item):
                    if fh > h:
                        continue
                    vs = variants(sw, sl, a, b)
                    if not vs:
                        continue
                    cells = filtered([dict(c, x=sx+(sw-c['x']-c['dx'] if right else c['x']), y=sy+c['y']) for c in cells_of(vs[0])], item)
                    volume = len(cells)*a*b*fh
                    if cells and (best_fill is None or volume > best_fill['volume']):
                        best_fill = dict(cells=cells, item=item, h=fh, volume=volume)
            if best_fill:
                fill = place(best_fill['cells'], best_fill['item'], best_fill['h'], 'fill', no)
                layer['fills'].append(dict(where=where, boxes=fill))
                placed_layer.extend(fill)
        for box in placed_layer:
            tops.setdefault(round(box['z']+box['dz'], 2), []).append(box)
        touched = {box['type_index'] for box in placed_layer}
        for item in items:
            if item['type_index'] in touched:
                counts[item['type_index']] += 1
                min_below = min(min_below, density(item))
        layers.append(layer)
        z += h
    return dict(boxes=boxes, layers=layers, kg=kg, height=z)
