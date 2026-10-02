# Cargo Load Operations

Open **Majestic Cargo → Operations → Cargo Load Operations**. The module uses
the host application's React version, theme tokens, FastAPI app and SQLite
database. Three.js is loaded only when a deck preview is opened.

## Workflow

1. Select or edit an aircraft. The supplied A321P2F geometry and arms are
   editable estimates. Unknown weight-and-balance reference fields stay blank.
2. Add catalogue box types, enable their position allocations, and optionally
   enter quantities. Blank quantities mean as many as fit. Both decks share
   the catalogue and packing rules.
3. Review the backend-calculated layout, weight totals, door exclusions and
   planning warnings. Export scoped Code 128 labels, CSV or a load work order.
   Work orders require a loader team leader. Exports save the current plan.
4. **Release plan** publishes the current slot records. Editing/saving alone
   never changes released records. Changed layouts require confirmation before
   replacing them. Each simultaneously released plan needs a unique box ID
   prefix because box IDs are the cross-application primary key.

Saved plans preserve an aircraft snapshot, including “Use without saving”
edits. Inline aircraft are retained privately for database referential integrity;
only an explicit aircraft save adds them to the aircraft selector.

## Integration

- `GET /api/packer/boxes/{box_id}` reads a released slot.
- `GET /api/packer/events?after=0` reads up to 100 release events in ascending
  order, with `{id, plan_id, box_ids}`. Persist the last consumed `id` and poll
  again. The durable outbox and slot replacement commit in one transaction.
- All other routes are documented in FastAPI's `/docs` under Cargo load
  operations. Packing and suggestion routes run in FastAPI's sync thread pool.
- Plans are filtered by company. As with the host API, company IDs are data
  scoping, not an authentication or authorization boundary.

Optional aircraft drafting reads `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` only
from the backend environment. The specified model default is
`claude-sonnet-5-5`; configure a model available to your provider account.
The `DraftProvider` protocol is the replacement point for a local provider.
AI requests only open a draft for review; they do not save aircraft.

## Validation

Install the host `requirements.txt` and run:

```text
python -B -m unittest discover -s backend/tests/packer -v
npm run build
npx oxlint src/features/packer
```

The tests use a private in-memory SQLite database. They cover the supplied
reference loads, 200 deterministic randomized contours and box mixes,
containment, overlaps, support, density ordering, limits, IDs, door exclusions,
weight-and-balance null handling, saved plans, release stability/conflicts,
CSV/PDF exports, barcode SVG previews and defensive AI parsing.

All displayed geometry is for planning. Approved load control documentation
remains the authority; fuel, crew and bulk hold cargo are outside this module.
