NOTE = 'Planning estimate only: fuel, crew and bulk hold cargo are not included. The approved load sheet from load control decides.'


def summary(aircraft, positions):
    loaded = [p for p in positions if p['totals']['actual_kg'] > 0]
    payload = sum(p['totals']['actual_kg'] for p in loaded)
    warnings = []
    missing = any(p['arm'] is None for p in loaded)
    if missing:
        warnings.append('A loaded position has no balance arm; centroid and CG are unavailable.')
    moment = sum(p['totals']['actual_kg']*(p['arm'] or 0) for p in loaded)
    centroid = moment/payload if payload and not missing else None
    wb = aircraft.wb
    cg = None
    if not missing and all(x is not None for x in [wb.dow_kg, wb.dow_arm_m, wb.lemac_m, wb.mac_m]) and wb.dow_kg+payload > 0:
        cg = ((wb.dow_kg*wb.dow_arm_m+moment)/(wb.dow_kg+payload)-wb.lemac_m)/wb.mac_m*100
    status = 'Reference data required'
    if cg is not None and wb.fwd_limit_pct_mac is not None and wb.aft_limit_pct_mac is not None:
        status = 'forward of limit' if cg < wb.fwd_limit_pct_mac else 'aft of limit' if cg > wb.aft_limit_pct_mac else 'within limits'
        if status != 'within limits':
            warnings.append(f'Zero-fuel CG is {status}')
    if payload > wb.max_payload_kg:
        warnings.append('Total payload exceeds aircraft maximum')
    warnings += [f"{p['deck']} {p['position']} exceeds position weight limit" for p in loaded if p['totals']['actual_kg'] > p['max_kg']]
    return dict(payload_kg=payload, centroid_m=centroid, cg_pct_mac=cg, status=status, warnings=warnings, note=NOTE)
