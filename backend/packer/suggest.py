from math import floor
from pydantic import Field, model_validator
from .models import Model, Plan, Positive
from .packer import pack_position
from .orient import fits_door
from .geometry import area
from typing import Literal


class SizeRange(Model):
    minimum: float = Field(ge=5, le=1000)
    maximum: float = Field(ge=5, le=1000)

    @model_validator(mode='after')
    def ordered(self):
        if self.minimum > self.maximum:
            raise ValueError('Range minimum exceeds maximum')
        return self


class SuggestRequest(Model):
    plan: Plan
    deck: Literal['main', 'lower']
    position: str
    l: SizeRange
    w: SizeRange
    h: SizeRange
    step: Positive = 10
    density: float = Field(default=200, ge=0, le=10000)
    max_kg: Positive = 25
    upright: bool = True

    @model_validator(mode='after')
    def bounded(self):
        count = 1
        for r in [self.l, self.w, self.h]:
            count *= floor((r.maximum-r.minimum)/self.step+1e-9)+1
        if count > 20000:
            raise ValueError('Size search is capped at 20,000 combinations; increase the step')
        return self


def suggest_sizes(req, aircraft):
    deck = aircraft.decks[req.deck]
    position = next((p for p in deck.positions if p.id == req.position), None)
    if position is None:
        raise ValueError('Unknown position')
    rules = getattr(req.plan.settings, req.deck)
    contour = deck.contours[position.contour or deck.default_contour]
    opts = dict(L=deck.position_length_cm, side_clearance=rules.side_clearance, end_clearance=rules.end_clearance,
                max_kg=position.max_kg, min_support=req.plan.settings.min_support/100,
                interlock=req.plan.settings.interlock, order=req.plan.settings.order, strict=True,
                lean=deck.kind=='container' and rules.lean, lean_min=rules.lean_min_support/100)
    ranges = [[r.minimum+i*req.step for i in range(floor((r.maximum-r.minimum)/req.step+1e-9)+1)] for r in [req.l,req.w,req.h]]
    results = []
    for l in ranges[0]:
        for w in ranges[1]:
            if l < w:
                continue
            for h in ranges[2]:
                kg = l*w*h/1e6*req.density
                item = dict(type_index=0,l=l,w=w,h=h,kg=kg,upright=req.upright,max_layers=300,qty=None)
                if kg > req.max_kg or not fits_door(item,deck.door):
                    continue
                packed = pack_position([item],opts,contour.points)
                count = len(packed['boxes'])
                if count:
                    volume = count*l*w*h/1e6
                    results.append(dict(l=l,w=w,h=h,kg=kg,count=count,volume=volume,
                                        fill_pct=volume/(area(contour.points)*deck.position_length_cm/1e6)*100,
                                        loaded_kg=packed['kg'],weight_limited=kg>0 and position.max_kg-packed['kg'] < kg))
    return sorted(results,key=lambda r: -r['volume'])[:8]
