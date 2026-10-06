"""Runs the agent on several wordings of one question per configuration and scores each answer against the known figures
(Jamaica: tomatoes = 100% duty + 80% stamp duty + 15% GCT + levies; total 196.15% added, 223.3% with GCT on top of duty)."""
import re, sys, threading, time
import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend.local_models import agent

QUESTIONS = [
    'how much will cost to import a kg of tomato from colombia to jamaica, i terms of taxes to be paid at import?',
    'What import taxes would we pay on one kilogram of fresh tomatoes shipped from Colombia into Jamaica?',
    'tomatoes colombia to jamaica: what is the total tax per kg at customs?',
    'If we import tomatoes into Jamaica, what duties and taxes apply per kilo?',
]
COUNTRIES = ['Jamaica', 'United States']


def score(text: str) -> str:
    text = text.replace(',', '')
    parts = all(re.search(rf'(?<![\d.]){n}(\.\d+)?\s*%', text) for n in ('100', '80', '15'))
    total = bool(re.search(r'(?<![\d.])(196(\.\d+)?|223(\.\d+)?|22[0-9]|197)\s*%', text))
    return 'RATES+TOTAL' if parts and total else 'RATES-OK' if parts else 'WRONG'


for config in sys.argv[1:]:
    model, think, review = config.split('|')
    results = []
    for number, question in enumerate(QUESTIONS, start=1):
        start = time.time()
        try:
            result = agent.run(model, question, COUNTRIES, threading.Event(), think=think == 'on', review=review == 'review')
            verdict, used = score(result['answer']), [s['tool'] for s in result['steps']]
        except Exception as error:
            verdict, used, result = f'ERROR {error}', [], {'answer': ''}
        results.append(verdict)
        print(f'{config} q{number}: {verdict:11} {time.time() - start:4.0f}s tools={used}', flush=True)
        print('     ', result['answer'].replace('\n', ' ')[:300], flush=True)
    print(f'== {config}: {results.count("RATES+TOTAL")} rates+total, {results.count("RATES-OK")} rates only, {results.count("WRONG")} wrong of {len(QUESTIONS)}\n', flush=True)
