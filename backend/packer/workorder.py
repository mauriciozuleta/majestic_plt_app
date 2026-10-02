from collections import Counter
import re


def ids(boxes):
    ordered = [b['box_id'] for b in sorted(boxes, key=lambda b: b['slot'])]
    groups = []
    for value in ordered:
        number = re.search(r'(\d+)$', value)
        previous = re.search(r'(\d+)$', groups[-1][-1]) if groups else None
        if previous and number and value[:number.start()] == groups[-1][-1][:previous.start()] and int(number[0]) == int(previous[0])+1:
            groups[-1].append(value)
        else:
            groups.append([value])
    return ', '.join(g[0] if len(g)==1 else f'{g[0]} to {g[-1]}' for g in groups)


def orientation_text(boxes):
    return '; '.join(f'{n} with the {across:g} cm side across' for across, n in Counter(b['dx'] for b in boxes).items())


def build_steps(position):
    p = position
    container = p['kind'] == 'container'
    base, length = p['contour']['points'][0][1], p['length']
    if container:
        steps = [f"Use the {p['uld']} for {p['deck']} position {p['position']}. Its floor is {base:g} cm across and {length:g} cm deep. Load from the back wall toward the door; left and right are seen from the door."]
    else:
        steps = [f"Use the {p['uld']}, {length:g} cm along by {base:g} cm across, for {p['deck']} position {p['position']}. Mark its forward edge; left and right are seen looking forward."]
    for layer in p['layers']:
        boxes = layer['main']
        start, direction = ('back wall', 'toward the door') if container else ('forward edge', 'aft')
        steps.append(f"Layer {layer['no']}, {layer['z']:g} to {layer['z']+layer['h']:g} cm: place {len(boxes)} × {boxes[0]['box_type']} ({boxes[0]['dims_cm']} cm), {orientation_text(boxes)}. Centre the block, start at the {start}, work {direction}, left to right. IDs {ids(boxes)}.")
        for fill in layer['fills']:
            bs = fill['boxes']
            steps.append(f"Still in layer {layer['no']}, fill the {fill['where']}: {len(bs)} × {bs[0]['box_type']}, {orientation_text(bs)}. IDs {ids(bs)}.")
        lean = [b for b in p['boxes'] if b['layer'] == layer['no'] and b['leans']]
        if lean:
            steps.append(f"In layer {layer['no']}, {len(lean)} boxes rest partly on the sloped side wall (IDs {ids(lean)}). Push them flush against the wall so the wall carries the overhang.")
    steps.append('Check that nothing touches the walls or roof and the door closes freely.' if container else
                 f"Check the build with the contour gauge ({p['contour']['name']}). Top of stack {p['height']:g} cm; no box may touch or cross the contour line.")
    steps.append(('Close and secure the container door' if container else 'Fit the net and tension it evenly') +
                 f". Expected cargo weight {p['kg']:g} kg actual, {p['totals']['chargeable_kg']:g} kg chargeable, before ULD tare; position limit {p['max_kg']:g} kg.")
    steps.append('Scan every label as the box goes in. A box whose ID does not match its slot must be moved, not relabelled.')
    return steps
