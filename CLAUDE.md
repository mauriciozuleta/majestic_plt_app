## Session start — MANDATORY, every session, before anything else

Do these reads first, in this order, before answering, planning or touching code — no exceptions, even for a small task or a
resumed session:

1. **`diary.md`** — the "Handout — start here" block, "At a glance", and the newest entries under "Entries".
2. **The graphify files** — `graphify-out/GRAPH_REPORT.md` and `graphify-out/wiki/index.md` (and any `graphify-out/wiki/` page
   that matches the task).

Only after both reads, use `graphify query "<question>"` / `graphify path` / `graphify explain` for specific questions and read
source files for the parts you will change. Say in your first reply that you read them.

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
