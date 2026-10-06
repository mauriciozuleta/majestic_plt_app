"""A local model that navigates the baked RAG files by itself.

The harness knows nothing about taxes, tariffs or HS codes. It gives the model four generic tools over the
baked documents and lets it decide what to look for, in which country, and how to compute the answer:

  search(query, country)          meaning-based search (best passages)
  grep(pattern, country)          exact text / regex search over every passage (finds a specific code or word)
  read(country, document, start)  read a document from a passage number onwards
  calc(expression)                arithmetic (small models add badly)

Models that can't call tools natively (gemma3) are driven with a plain protocol: every turn the model writes ONE
JSON object, either {"tool": ..., "args": {...}} or {"answer": "..."}; the harness runs the tool and feeds the
result back. The loop is bounded, every step is recorded (the trace is shown with the answer), and the answer
must come from what the tools returned.
"""

import ast
import json
import operator
import re

from ..rag_files import store
from . import ollama_client

MAX_STEPS = 10
RESULT_CHARS = 3500
OPTIONS = {'num_ctx': 12288, 'temperature': 0, 'num_predict': 700}

SYSTEM_PROMPT = """You answer questions for a food import-export company using ONLY our own documents, which you search with tools. \
Documents are grouped by country; these countries have documents: {countries}. A question can involve several countries \
(for example the country goods come from and the country they are imported into): decide which country's documents hold the answer and search those.

Each turn, reply with ONE JSON object and nothing else. Either call a tool:
{{"tool": "search", "args": {{"query": "...", "country": "..."}}}}   meaning-based search, returns the best passages
{{"tool": "grep", "args": {{"pattern": "...", "country": "..."}}}}    exact text or regex over every passage; use it to find a specific code, name or word (tables are searchable this way)
{{"tool": "read", "args": {{"country": "...", "document": "...", "start": 0}}}}   read passages of a document from a passage number
{{"tool": "calc", "args": {{"expression": "..."}}}}   arithmetic, e.g. "1.51 * (1 + 1 + 0.8)"; always use it for sums and products
or give the final answer:
{{"answer": "..."}}

Rules:
- Find the figures in the documents; never use numbers from memory. If tables list values under column codes, work out what the codes mean from the documents (search for them) before you use them.
- If a first search doesn't find it, try other words, a code, or grep. Several searches are normal.
- Tables: every column is a separate charge or attribute, written under a short code. Find out what each code stands for (search for it, and read how our other documents name the charges) before using it, and include EVERY column that is a tax or levy. A rate such as 0.15 is a fraction (15%), not an amount of money.
- Our documents mix narrative profiles (context, conditions, exemptions) with data tables (one line per item). A figure for a specific item is usually in a table line (grep for the item or its code); the profile tells you which conditions apply. Look in both before answering.
- When you use a table line, first copy it exactly, then expand it: one entry for EVERY non-empty column, written as "code = what it means = value as a percentage or amount" (the first rate columns are easy to forget). Only then calculate with calc over that list.
- Do every calculation with calc. State the assumptions you make.
- The final answer is short: the direct answer first, then the figures it is built from, with the document each came from. If the documents don't contain what's needed, say exactly what is missing."""


# ---------------------------------------------------------------- calc


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def calc(expression: str) -> float:
    """Evaluates +, -, *, /, ** and parentheses over numbers; nothing else."""
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError('only numbers and + - * / ** ( ) are allowed')

    return walk(ast.parse(expression.replace('%', '/100').replace('^', '**').replace(',', ''), mode='eval'))


# ---------------------------------------------------------------- tools over the baked files


class Library:
    """The baked RAG files, loaded once per question."""

    def __init__(self, countries: list[str]):
        self.chunks: dict[str, list[dict]] = {}
        for country in countries:
            path = store.baked_path(country)
            if path.exists():
                data = store._read_json(path, {})
                self.chunks[country] = [{'index': c['index'], 'text': c['text'], 'document': c.get('document'), 'section': c.get('section')} for c in data.get('chunks', [])]

    def country(self, name) -> str | None:
        wanted = str(name or '').strip().lower()
        return next((country for country in self.chunks if country.lower() == wanted), None)

    def _need_country(self, name):
        found = self.country(name)
        if not found:
            raise ValueError(f'Give "country" as one of: {", ".join(self.chunks)}.')
        return found

    def search(self, query: str, country: str) -> str:
        country = self._need_country(country)
        results = store.search_country(country, str(query), top_k=5)
        if not results:
            return 'No passages found.'
        return '\n\n'.join(f"[{r.get('document')} > {r.get('section')} (passage {r['chunk_index']})]\n{r['text'][:900]}" for r in results)

    def grep(self, pattern: str, country: str) -> str:
        """Lines matching the pattern (a regex). If nothing matches and the pattern is several words, lines containing
        all the words in any order. Matches are spread over the documents so a long narrative document can't crowd out a table."""
        country = self._need_country(country)
        pattern = str(pattern)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)
        lines = [(chunk['document'], chunk['index'], line.strip()) for chunk in self.chunks[country] for line in chunk['text'].splitlines() if line.strip()]
        hits = [item for item in lines if regex.search(item[2])]
        note = ''
        if not hits:
            words = [re.escape(word) for word in re.findall(r'\w{3,}', pattern)]
            if len(words) > 1:
                parts = [re.compile(word, re.IGNORECASE) for word in words]
                hits = [item for item in lines if all(part.search(item[2]) for part in parts)]
                note = '(no line has that exact text; these lines contain all the words)\n'
        if not hits:
            return 'No line matches.'
        by_document: dict[str, list] = {}
        for document, index, line in hits:
            by_document.setdefault(document, []).append((index, line))
        shown, summary = [], []
        for document, items in by_document.items():
            summary.append(f'{len(items)} in {document}')
            shown += [f'[{document} (passage {index})] {line[:400]}' for index, line in items[:4]]
        return note + f"Matches: {', '.join(summary)}. First lines of each document:\n" + '\n'.join(shown[:14])

    def read(self, country: str, document: str, start: int = 0) -> str:
        country = self._need_country(country)
        chunks = [c for c in self.chunks[country] if str(document).lower() in (c['document'] or '').lower()]
        if not chunks:
            names = sorted({c['document'] for c in self.chunks[country] if c['document']})
            raise ValueError(f'No such document. Documents: {", ".join(names)}')
        start = max(0, int(start or 0))
        out, size = [], 0
        for number, chunk in enumerate(chunks[start:], start=start):
            if size + len(chunk['text']) > RESULT_CHARS and out:
                out.append(f'(continues: call read again with start={number})')
                break
            out.append(f"[{chunk['document']} > {chunk['section']} (passage {number})]\n{chunk['text']}")
            size += len(chunk['text'])
        return '\n\n'.join(out) or 'No more passages.'


def run_tool(library: Library, name: str, args: dict) -> str:
    if name == 'search':
        return library.search(args.get('query', ''), args.get('country'))
    if name == 'grep':
        return library.grep(args.get('pattern', ''), args.get('country'))
    if name == 'read':
        return library.read(args.get('country'), args.get('document', ''), args.get('start', 0))
    if name == 'calc':
        value = calc(str(args.get('expression', '')))
        return f'{value:.6g}'
    raise ValueError('Unknown tool. Use search, grep, read or calc.')


# ---------------------------------------------------------------- the loop


def _json_object(text: str) -> dict | None:
    text = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)
    start = text.find('{')
    while start >= 0:
        depth = 0
        for end in range(start, len(text)):
            depth += {'{': 1, '}': -1}.get(text[end], 0)
            if depth == 0:
                try:
                    data = json.loads(text[start: end + 1])
                    if isinstance(data, dict):
                        return data
                except ValueError:
                    pass
                break
        start = text.find('{', start + 1)
    return None


REVIEW_PROMPT = """Before you finish, check your work against the RESULTS above:
1. List every charge, rate, condition or exemption in the results that bears on the question.
2. Check that your calculation includes each one that applies, and that you used the document that gives the exact figure for the item (not only a general statement).
3. If something is missing or uncertain, make more tool calls now. If everything is covered, repeat your final answer as {"answer": "..."}."""


def run(model: str, question: str, countries: list[str], cancel, on_step=lambda step: None, think: bool = False, review: bool = True) -> dict:
    """Runs the loop. Returns {answer, steps: [{tool, args, result|error}], finished}. on_step(step) is called after
    every tool call so a caller can show progress."""
    library = Library(countries)
    if not library.chunks:
        raise ollama_client.OllamaError('No country has baked documents yet — Load and Bake files in RAG Files first.')
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT.format(countries=', '.join(library.chunks))}, {'role': 'user', 'content': question}]
    steps = []
    options = {**OPTIONS, 'num_predict': 4000} if think else OPTIONS
    reviewed = not review
    for _ in range(MAX_STEPS):
        if cancel.is_set():
            return {'answer': '', 'steps': steps, 'finished': False}
        reply = ''
        for piece in ollama_client.stream_chat(model, messages, cancel, options, think):
            reply += piece
        messages.append({'role': 'assistant', 'content': reply})
        action = _json_object(reply)
        if action is None:
            messages.append({'role': 'user', 'content': 'Reply with ONE JSON object only: a tool call or {"answer": "..."}.'})
            continue
        if 'answer' in action:
            if not reviewed and steps:
                reviewed = True  # one completeness review before the answer is accepted
                messages.append({'role': 'user', 'content': REVIEW_PROMPT})
                continue
            return {'answer': str(action['answer']).strip(), 'steps': steps, 'finished': True}
        step = {'tool': action.get('tool'), 'args': action.get('args') if isinstance(action.get('args'), dict) else {}}
        try:
            step['result'] = run_tool(library, str(step['tool']), step['args'])
        except Exception as error:  # the model sees the problem and can correct itself
            step['error'] = str(error)
        steps.append(step)
        on_step(step)
        feedback = step.get('result') if 'result' in step else f"Error: {step['error']}"
        messages.append({'role': 'user', 'content': f'RESULT:\n{feedback[:RESULT_CHARS]}\n\nContinue: another tool call, or {{"answer": "..."}} once you have what you need.'})
    # out of steps: make it answer with what it has
    messages.append({'role': 'user', 'content': 'You are out of steps. Give your best final answer now as {"answer": "..."}, saying what is missing if anything.'})
    reply = ''.join(ollama_client.stream_chat(model, messages, cancel, options, think))
    action = _json_object(reply) or {}
    return {'answer': str(action.get('answer') or reply).strip(), 'steps': steps, 'finished': False}
