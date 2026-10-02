from .orient import fits_door
from .packer import pack_position
from .weights import weights, totals
from .geometry import area
from .wb import summary
from .models import Plan, Aircraft


def pack_plan(plan: Plan, aircraft: Aircraft) -> dict:
    results, all_boxes, deck_totals = [], [], {}
    settings = plan.settings
    number = 0
    for deck_name in ('main', 'lower'):
        deck = aircraft.decks[deck_name]
        rules = getattr(settings, deck_name)
        deck_boxes = []
        for position in deck.positions:
            contour = deck.contours[position.contour or deck.default_contour]
            items, messages = [], []
            allocation = plan.alloc.get(deck_name, {}).get(position.id, {})
            for index, box_type in enumerate(plan.box_types):
                alloc = allocation.get(str(index))
                if not alloc or not alloc.on:
                    continue
                item = dict(box_type.model_dump(), type_index=index, qty=alloc.qty)
                if not fits_door(item, deck.door):
                    messages.append(f'{box_type.name} excluded: does not fit the {deck_name} deck door.')
                else:
                    items.append(item)
            opts = dict(L=deck.position_length_cm, side_clearance=rules.side_clearance,
                        end_clearance=rules.end_clearance, max_kg=position.max_kg,
                        min_support=settings.min_support/100, interlock=settings.interlock,
                        order=settings.order, strict=settings.strict_density,
                        lean=deck.kind == 'container' and rules.lean, lean_min=rules.lean_min_support/100,
                        container=deck.kind == 'container')
            packed = pack_position(items, opts, contour.points)
            slots = {}
            packed['boxes'].sort(key=lambda b: (b['layer'], b['y'], b['x']))
            for box in packed['boxes']:
                number += 1
                slots[box['layer']] = slots.get(box['layer'], 0)+1
                bt = plan.box_types[box['type_index']]
                box.update(weights(bt, settings.divisor))
                box.update(box_id=f'{settings.id_prefix}{number:0{settings.id_digits}d}',
                           deck=deck_name, position=position.id, slot=slots[box['layer']],
                           box_type=bt.name, dims_cm=f'{bt.l:g} × {bt.w:g} × {bt.h:g}', upright=bt.upright,
                           aircraft=aircraft.name, uld=deck.uld)
            packed.update(deck=deck_name, position=position.id, uld=deck.uld, kind=deck.kind,
                          arm=position.arm, max_kg=position.max_kg, contour=contour.model_dump(),
                          length=deck.position_length_cm, messages=messages,
                          contour_m3=area(contour.points)*deck.position_length_cm/1e6,
                          totals=totals(packed['boxes']))
            results.append(packed)
            all_boxes.extend(packed['boxes'])
            deck_boxes.extend(packed['boxes'])
        deck_totals[deck_name] = totals(deck_boxes)
    return dict(positions=results, boxes=all_boxes, totals=totals(all_boxes), decks=deck_totals,
                wb=summary(aircraft, results), type_weights=[weights(b, settings.divisor) for b in plan.box_types])
