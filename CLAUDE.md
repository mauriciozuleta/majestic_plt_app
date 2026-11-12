## Session start — MANDATORY, every session, before anything else

Do these reads first, in this order, before answering, planning or touching code — no exceptions, even for a small task or a
resumed session:

1. **`diary.md`** — the "Handout — start here" block, "At a glance", and the newest entries under "Entries".
2. **The graphify files** — `graphify-out/GRAPH_REPORT.md` and `graphify-out/wiki/index.md` (and any `graphify-out/wiki/` page
   that matches the task).

Only after both reads, use `graphify query "<question>"` / `graphify path` / `graphify explain` for specific questions and read
source files for the parts you will change. Say in your first reply that you read them.

## Supermarket catalog service — check at session start

Majestic's "Build supermarket catalog" talks to the separate app `D:\OneDrive\0. software Lab\Supermarket_data_fetch` over a local
API on `http://127.0.0.1:8020`. After the mandatory reads, check it is running **and healthy**: `GET /health` AND `GET /stores` must both
answer 200 (`/health` alone is not enough — `/stores` is what Majestic's status check calls). If either fails, stop the old process
(whatever listens on 8020) and start it with the **global Python, not `launch_api.bat`**: the bat falls back to `py`, which resolves to
Majestic's `.venv` when launched from here, and that environment lacks `requests`, so `/stores` crashes with an empty reply:

    Start-Process "C:\Python313\python.exe" -ArgumentList 'api_server.py' -WorkingDirectory "D:\OneDrive\0. software Lab\Supermarket_data_fetch" -WindowStyle Hidden

Wait ~8 s, re-check both endpoints, and tell the user whether it was already running or you started it. Do not edit that app's
`api_server.py` or `AGENTS.md` (owned by Codex).

## Tax calculators — conflicting rates (standing rule from the user)

When two parts of a customs document give different rates for the same tariff line (the schedule vs a List, a Specific Order vs the CET …), the calculator uses the
**higher** tariff or tax and **still shows the "CONFLICT IN THE FILE" warning** (say which rate was used). The shared helper is `higher_rate()` in
`backend/tax_calc/base.py`; apply it to every new country adapter. A side that is not a percentage (a specific amount, unreadable text) is ignored by the helper;
if the two charges are of different kinds (e.g. a per-gallon Order vs an ad valorem rate) compute both when the inputs allow and use the higher amount.

## Backend-first — standing rule for every new feature (from the user)

The goal of the app is to be **agent-ready**: everything that computes, decides or changes data must run from the backend (FastAPI, `backend/`) so that tests, schedulers and
agents can call it. The React front end only **shows** results and collects input. Build every new feature the way Phases 0-6 of the move to the backend were built (see the
diary and `docs/agent_tool_inventory.md`):

- **No business logic in JavaScript.** Calculations (prices, taxes, conversions, allocations, statements, matching, classification), rules (thresholds, caps, caps-by-market),
  scheduling and anything that writes data live in a Python module under `backend/<feature>/` with an endpoint in `backend/routers/`. The front end calls it through a thin
  `src/services/*.js` function / hook and renders the answer. Allowed in JS: formatting, layout, sorting for display, UI state, CSV / PDF layout.
- **One module per capability**, with a pure core (functions of plain dicts, no database, no web) and a thin service layer that reads the database. The core is what tests call.
- **Label every endpoint with a tier** in its docstring — R (read), S (simulate: computes, saves nothing), W (writes), X (external / paid call) — and add it to
  `docs/agent_tool_inventory.md`. A paid or external call is never made by a read endpoint; it needs an explicit step.
- **A paid call (Anthropic credits, web search) never starts without a stated cost.** The endpoint gives the estimate on a dry run and refuses to run without `confirm_usd`; one run is capped; the UI
  shows the amount and asks. One click once cost 8 USD (2026-11-11). Free, deterministic steps (tables, rules, stored data) come before any paid one.
- **Writes go through the data history** (`backend/data_history/`: record, guard, approve suspicious changes) so they can be undone.
- **Porting existing JavaScript:** first freeze what the JavaScript produces (run it with node or Playwright on real data plus edge cases, stub paid / external calls) into
  `backend/tests/fixtures/js_parity/`, then port it EXACTLY and prove it with a parity test (identical numbers, same order of float sums), check the test can fail (mutate the
  port), and only then change behaviour as a separate, named step. Delete the JavaScript only after the parity test passes. Never delete the fixtures.
- **Tests:** a pure-function test with hand-worked numbers, a service / API test on an in-memory database, and (for screens) a check on a COPY of the real database in a real
  browser (`backend/tests/js_parity/serve.py` + Vite + Playwright). Never point a test at the real database or the real history file.
- **Document in the same change:** diary entry, `docs/agent_tool_inventory.md` row(s), `apis.md` when a router or external source is added.
- If a feature cannot be built this way (for example it truly needs the browser), say so and ask before writing logic into the front end.

## APIs register — `apis.md`

`apis.md` at the project root lists every external API / data source the app uses (what it is used for, the code that calls it, the `.env` variable it needs,
its status) and the groups of the app's own endpoints.

Rules:
- Any time a new API or external data source is added (a new service called from the backend or frontend, a new `.env` key, a new scraped/downloaded source, or a
  new group of own endpoints), add its entry to `apis.md` **in the same change**: name, purpose, where in the code, the `.env` variable name (never its value) and its
  status. Update the entry when one is removed, replaced or changes status (for example a key stops working).
- Something only tested and not wired into the app goes under "Tested but not part of the app yet".

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Always read graphify-out/GRAPH_REPORT.md and graphify-out/wiki/index.md at the start of every session (see "Session start" above); use query/path/explain for the detail after that.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- After every git commit in this repo, run `graphify update .` — no exceptions, even for small commits. The graph must never drift behind the actual committed code.

## Diary (progress wiki)

`diary.md` at the project root is the progress wiki: an "At a glance" map of the project plus one entry per prompt.

Rules:
- Reading `diary.md` at the start of every session is mandatory (see "Session start" above) — before exploring the code or re-deriving anything it already records.
- After every prompt that changes the project, add an entry at the top of its "Entries" section: the date, the user's prompt (verbatim, trimmed only if very long) and a summary of what changed and why. Keep "At a glance" accurate.
- Do not paste code into it; name the files.
- `diary.md` starts with a "Handout — start here" block for a new or changed session. After reading it and adding your entries, delete it; as the last step of the session (or of each prompt that changes something) write a fresh handout in its place describing the state at that moment. Never leave a stale handout.
