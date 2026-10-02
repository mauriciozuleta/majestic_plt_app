def weights(item, divisor):
    volume = item.l * item.w * item.h / divisor
    return dict(actual_kg=item.kg, volume_kg=volume, chargeable_kg=max(item.kg, volume),
                volume_m3=item.l*item.w*item.h/1e6)


def totals(boxes):
    return dict(boxes=len(boxes), **{key: sum(b[key] for b in boxes) for key in
                                   ('actual_kg', 'volume_kg', 'chargeable_kg', 'volume_m3')})
