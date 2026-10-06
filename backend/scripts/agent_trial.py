import sys, threading, time
import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend.local_models import agent
from backend.rag_files import store

model = sys.argv[1]
question = sys.argv[2]
countries = sys.argv[3].split(',')
start = time.time()


def show(step):
    arg = ', '.join(f'{k}={str(v)[:70]!r}' for k, v in step['args'].items())
    out = step.get('result') or ('ERROR ' + step.get('error', ''))
    print(f"  [{time.time() - start:5.0f}s] {step['tool']}({arg}) -> {out[:230]!r}", flush=True)


result = agent.run(model, question, countries, threading.Event(), show)
print(f'\nfinished={result["finished"]} steps={len(result["steps"])} time={time.time() - start:.0f}s')
print(result['answer'])
