"""Saves what the JavaScript logic produces today, as the reference the Python port must reproduce (Phase 0 of the move to the backend).

  python -m backend.tests.js_parity.capture [--refresh-inputs] [--compare] [--add-ai-variant]

  --add-ai-variant  adds to outputs.json the comparison made with a stand-in AI judge (every source product matched to the first candidate of its group), keeping the rest.
                    It runs the JavaScript engine, so it only works while that engine is still in src/services/marketOpportunities.js.

  --compare  runs the CURRENT front end on the frozen inputs and checks it against the saved outputs.json instead of overwriting it (use it after changing the JavaScript
             or moving more of it to the backend: the screens must still receive exactly what the original JavaScript produced).

1. inputs.json  — a frozen slice of the real data (read-only export; written only with --refresh-inputs or when missing)
2. a throwaway backend + Vite dev server over a database built from those inputs
3. a headless browser imports the real modules and saves their output to outputs.json:
     portfolio, category coverage, the Colombia two-source merge with its translations, and the Market Opportunities comparison Colombia -> Jamaica
   (The Market Opportunities comparison was captured from the original JavaScript engine before it moved to backend/market_opportunities/; it is kept, not re-captured.)
   Paid and external calls are stubbed so the output is repeatable: exchange rates are fixed, the AI product matcher answers an error (the engine then falls back to
   shared-HS-code pairing, as it does without credits), the item-weight research answers "nothing to do".
Needs Playwright (the project's .venv has it) and the dev dependencies of the front end."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from backend.tests.js_parity import inputs as parity  # noqa: E402

BACKEND_PORT, VITE_PORT = 8013, 5199
RATES = {'COP': 4000.0, 'JMD': 160.0, 'USD': 1.0, 'XCD': 2.7, 'TTD': 6.8, 'BSD': 1.0, 'BBD': 2.0}
OUTPUTS_FILE = parity.FIXTURES / 'outputs.json'

JS = """
async () => {
  const portfolio = await import('/src/services/productPortfolio.js')
  const fetchers = await import('/src/components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers.js')
  const data = await import('/src/components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData.js')
  const translations = await import('/src/components/company/tabs/OperationsTab/MarketAnalysis/productTranslations.js')
  const opportunities = await import('/src/services/marketOpportunities.js')
  const out = {}
  out.portfolio = await portfolio.buildProductPortfolio()
  out.coverage = await portfolio.buildCategoryCoverage()
  const snapshots = await fetchers.fetchPriceComparisonSnapshot()
  const bySource = Object.fromEntries(snapshots.map((s) => [s.source, s.products]))
  const overrides = Object.fromEntries((await fetchers.fetchTranslationOverrides()).map((row) => [row.product_key, row.translation_en]))
  out.colombia_merged = data.mergeSources(bySource.la_mayorista || [], bySource.corabastos || []).map((row) => ({
    ...row, _translation: translations.translateProductName(row.nameEs, overrides),
  }))
  // the comparison engine moved to the server (Phase 2): the saved 'opportunity' / 'opportunity_ai' outputs come from the ORIGINAL JavaScript engine and are kept as they are
  if (typeof opportunities.computeMarketOpportunity === 'function') out.opportunity = await opportunities.computeMarketOpportunity('Colombia', ['Jamaica'])
  return out
}
"""


JS_AI = """
async () => {
  const opportunities = await import('/src/services/marketOpportunities.js')
  return await opportunities.computeMarketOpportunity('Colombia', ['Jamaica'])
}
"""


def stand_in_judge(route):
    """A deterministic AI judge: every source product of a group is judged to be the group's FIRST candidate, with a fixed note. Python's test uses the same rule."""
    body = json.loads(route.request.post_data)
    results = {}
    for group in body['groups']:
        for source in group['sources']:
            results[source['key']] = {'matches': group['candidates'][:1], 'note': 'stand-in judge', 'cached': False}
    route.fulfill(json={'results': results, 'errors': [], 'cache_hit_count': 0, 'cache_miss_count': len(results)})


def wait_for(url: str, seconds: int = 120) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f'{url} did not answer in {seconds}s')


def kill_tree(process: subprocess.Popen) -> None:
    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)


def _differences(actual, expected, path='') -> list[str]:
    """JSON-level differences; a key the JavaScript left out equals null; floats compare closely."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key in expected:
            out += _differences(actual.get(key), expected[key], f'{path}.{key}')
        out += [f'{path}.{key}: extra value' for key in set(actual) - set(expected) if actual[key] is not None]
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            return [f'{path}: {len(actual)} items != {len(expected)}']
        return [d for a, e in zip(actual, expected) for d in _differences(a, e, path + '[]')]
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and not isinstance(expected, bool):
        return [] if abs(actual - expected) <= 1e-9 * max(1, abs(expected)) else [f'{path}: {actual} != {expected}']
    return [] if actual == expected else [f'{path}: {actual!r} != {expected!r}']


def compare(outputs: dict) -> None:
    saved = json.loads(OUTPUTS_FILE.read_text(encoding='utf-8'))
    key = lambda row: (row['country'], row['name'].lower())  # noqa: E731 — the directory's order may differ slightly (the sort is case-insensitive on the server)
    results = {
        'portfolio': _differences(sorted(outputs['portfolio'], key=key), sorted(saved['portfolio'], key=key)),
        'coverage': _differences(outputs['coverage'], saved['coverage']),
        'colombia_merged': _differences(outputs['colombia_merged'], saved['colombia_merged']),
    }
    if 'opportunity' in outputs:  # only while the JavaScript engine still exists
        results['opportunity'] = _differences(outputs['opportunity'], saved['opportunity'])
    for name, problems in results.items():
        print(f"{name:16}", 'MATCH' if not problems else f'{len(problems)} differences, first: {problems[:3]}')
    if any(results.values()):
        raise SystemExit(1)


def main() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import backend.models
    real_db = ROOT / 'majestic_plt.db'
    if '--refresh-inputs' in sys.argv or not parity.INPUTS_FILE.exists():
        parity.FIXTURES.mkdir(parents=True, exist_ok=True)
        parity.INPUTS_FILE.write_text(json.dumps(parity.export_inputs(real_db), ensure_ascii=False, indent=1), encoding='utf-8')
        print('inputs written', parity.INPUTS_FILE)
    inputs = parity.read_inputs()

    work = Path(tempfile.mkdtemp(prefix='js_parity_'))
    # a copy of the real database FILE (so the schema is complete) whose five relevant tables are replaced by the frozen rows — the real file is only read
    shutil.copy(real_db, work / 'parity.db')
    engine = create_engine(f'sqlite:///{(work / "parity.db").as_posix()}')
    with sessionmaker(bind=engine)() as session:
        for model in (backend.models.PriceComparisonSnapshot, backend.models.ProductSource, backend.models.CountryReferenceCatalog, backend.models.ProductTranslationOverride,
                      backend.models.BuiltInProductSourceOverride):
            session.query(model).delete()
        session.commit()
        parity.load_inputs(session, inputs)
    engine.dispose()

    env = {**os.environ, 'PYTHONPATH': str(ROOT)}
    backend = subprocess.Popen([sys.executable, '-m', 'backend.tests.js_parity.serve', str(work / 'parity.db'), str(work / 'history.db'), str(BACKEND_PORT)], cwd=ROOT, env=env)
    vite = subprocess.Popen(f'npx vite --host 127.0.0.1 --port {VITE_PORT} --strictPort', cwd=ROOT, shell=True,
                            env={**env, 'VITE_API_BASE_URL': f'http://127.0.0.1:{BACKEND_PORT}'}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for(f'http://127.0.0.1:{BACKEND_PORT}/product-sources')
        wait_for(f'http://127.0.0.1:{VITE_PORT}/')
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_default_timeout(300000)  # the first request makes Vite compile the whole module graph

            def rate(route):
                code = route.request.url.split('from=')[-1].split('&')[0]
                route.fulfill(json={'rate': RATES.get(code), 'date': '2026-11-10', 'from': code, 'available': code in RATES})

            page.route('**/api/market-opportunities/exchange-rate*', rate)
            page.route('**/api/product-matches', lambda route: route.fulfill(status=502, json={'detail': 'stubbed in the parity capture'}))
            page.route('**/api/catalog-normalization/research', lambda route: route.fulfill(json={'status': 'nothing_to_do'}))
            page.goto(f'http://127.0.0.1:{VITE_PORT}/', wait_until='domcontentloaded')
            if '--add-ai-variant' in sys.argv:
                page.unroute('**/api/product-matches')
                page.route('**/api/product-matches', stand_in_judge)
                variant = page.evaluate(JS_AI)
                browser.close()
                saved = json.loads(OUTPUTS_FILE.read_text(encoding='utf-8'))
                saved['opportunity_ai'] = variant
                OUTPUTS_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
                print('ai variant added:', len(variant['rows']), 'rows; tiers', sorted({row['match_tier'] for row in variant['rows']}), '; errors', variant['aiMatchErrors'])
                return
            outputs = page.evaluate(JS)
            browser.close()
        if '--compare' in sys.argv:
            compare(outputs)
            return
        previous = json.loads(OUTPUTS_FILE.read_text(encoding='utf-8')) if OUTPUTS_FILE.exists() else {}
        for kept in ('opportunity', 'opportunity_ai'):  # captured from the original JavaScript engine, which is gone: never overwritten
            if kept not in outputs and kept in previous:
                outputs[kept] = previous[kept]
        outputs['_meta'] = {'rates': RATES, 'captured_at': time.strftime('%Y-%m-%d'), 'note': 'JavaScript output on the frozen inputs; AI matching stubbed to an error, research to nothing_to_do'}
        OUTPUTS_FILE.write_text(json.dumps(outputs, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
        print('outputs written', OUTPUTS_FILE, {key: (len(value) if hasattr(value, '__len__') else value) for key, value in outputs.items()})
    finally:
        kill_tree(vite)
        kill_tree(backend)
        time.sleep(1)
        shutil.rmtree(work, ignore_errors=True)  # the copy holds real business data: never leave it behind


if __name__ == '__main__':
    main()
