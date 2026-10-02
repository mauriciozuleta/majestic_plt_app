"""Provider boundary. Credentials remain in the server environment."""
import json
import math
import os
import uuid
from typing import Protocol
import httpx
from .models import Aircraft

PROMPT = '''You are helping configure an air cargo load-planning tool. Give your best estimate, from public information, of the cargo configuration of: {query}, for BOTH the main deck and the lower deck. Units: centimetres for geometry, metres for balance arms from the aircraft datum, kilograms for weight. Reply with only a JSON object: {{"name","notes","maxPayloadKg","lemacM","macM","cgFwdPctMac","cgAftPctMac","confidence","main":DECK,"lower":DECK or null}} where DECK = {{"uld","kind":"pallet|container","positionLengthCm","doorWidthCm","doorHeightCm","contour":[[height,width],...],"positions":[{{"id","armM","maxKg"}}]}}. Contours list [height above the ULD floor, full usable width] from 0 to the maximum build height; heights increase; widths may grow or shrink. Use null for anything you cannot estimate responsibly. List positions forward to aft.'''


class DraftProvider(Protocol):
    def draft(self, query: str) -> dict: ...


class AnthropicProvider:
    def draft(self, query):
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise RuntimeError('AI drafting is unavailable: configure ANTHROPIC_API_KEY on the backend.')
        response = httpx.post('https://api.anthropic.com/v1/messages',timeout=90,
                              headers={'x-api-key':key,'anthropic-version':'2023-06-01'},
                              json={'model':os.environ.get('ANTHROPIC_MODEL','claude-sonnet-5-5'),
                                    'max_tokens':6000,'messages':[{'role':'user','content':PROMPT.format(query=json.dumps(query))}]})
        if response.status_code != 200:
            raise RuntimeError(f'AI provider returned status {response.status_code}. Check the backend model configuration.')
        text = ''.join(c.get('text','') for c in response.json().get('content',[]))
        start, end = text.find('{'), text.rfind('}')
        return json.loads(text[start:end+1])


def numeric(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else None


def parse_draft(raw, query):
    decks = {}
    for name in ['main','lower']:
        d = raw.get(name)
        if not d:
            decks[name] = dict(uld='Unconfigured (review required)',kind='container' if name=='lower' else 'pallet',
                               position_length_cm=1,door=None,contours={'draft':{'name':'Unconfigured — no positions','points':[[0,1],[1,1]]}},default_contour='draft',positions=[])
            continue
        points = sorted([p for p in d.get('contour',[]) if isinstance(p,list) and len(p)==2 and all(numeric(n) is not None and n>=0 for n in p)],key=lambda p:p[0])
        if points and points[0][0] != 0:
            points.insert(0,[0,points[0][1]])
        dw, dh = numeric(d.get('doorWidthCm')),numeric(d.get('doorHeightCm'))
        decks[name] = dict(uld=d.get('uld') or 'Review ULD',kind=d.get('kind','pallet'),position_length_cm=d.get('positionLengthCm'),
                           door={'width':dw,'height':dh} if dw and dh else None,
                           contours={'draft':{'name':'AI contour (estimate)','points':points}},default_contour='draft',
                           positions=[dict(id=str(p.get('id') or i+1),arm=numeric(p.get('armM')),max_kg=numeric(p.get('maxKg'))) for i,p in enumerate(d.get('positions',[])[:60])])
    wb = {target:numeric(raw.get(source)) for target,source in [('max_payload_kg','maxPayloadKg'),('lemac_m','lemacM'),('mac_m','macM'),('fwd_limit_pct_mac','cgFwdPctMac'),('aft_limit_pct_mac','cgAftPctMac')]}
    return Aircraft.model_validate(dict(id=str(uuid.uuid4()),name=raw.get('name') or query,
                                        notes=f"Drafted by AI for '{query}'; values are estimates. "+str(raw.get('notes') or ''),decks=decks,wb=wb))


def draft_aircraft(query, provider: DraftProvider | None = None):
    return parse_draft((provider or AnthropicProvider()).draft(query),query)
