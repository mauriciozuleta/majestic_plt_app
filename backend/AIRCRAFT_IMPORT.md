# Aircraft database and selected fleet

Source located using `D:/OneDrive/0. software Lab/AI_FRESH24/graphify-out/graph.json`:

- `main_models_aircraft` → `main/models.py`, `Aircraft`, table `main_aircraft`
- `main_forms_aircraftform` → `main/forms.py`, `AircraftForm`
- `main_views_routes_api_add_aircraft` → `main/views_routes_api.py`, `add_aircraft`
- Table UI: `templates/aircraft_list_table.html`

The six records in the source SQLite database were imported into the Majestic
Cargo aircraft database. The source database is opened with `mode=ro` and is
never modified. The original record, including duplicate pounds fields and its
source identifier, is retained in `logistics_aircraft.source_data`.

Canonical kilograms and gallons are copied without conversion. Renamed fields:

| Source | Destination |
| --- | --- |
| fuel_burn_gal | fuel_burn_gal_hr |
| cruise_speed | cruise_speed_kt |
| max_range_at_max_payload | max_range_at_max_payload_nm |
| max_range_with_max_fuel | max_range_with_max_fuel_nm |

Run the import explicitly, after starting the backend once for schema migration:

```powershell
python -B -m backend.import_aircraft_database --source 'D:\OneDrive\0. software Lab\AI_FRESH24\db.sqlite3' --company-id majestic-cargo-1789481169784
```

Existing imports are skipped, preserving local edits. Import is atomic and
does not automatically select aircraft for the fleet.

In Fleet Management, **Aircraft Database** creates and edits specifications.
The upper **Aircraft** card adds existing records through a multi-select picker.
Selections persist in `in_fleet`; FRESH24 provider lists and provider-save
validation both enforce them. Removing a fleet selection retains the database
record; removing or deleting a provider-assigned aircraft is blocked. Aircraft
that existed before the selection feature remain selected during migration.

API endpoints under `/companies/{company_id}/air-logistics`:

- `GET aircraft-catalogue`: all database records
- `GET aircraft`: provider-eligible fleet records for Majestic Cargo/FRESH24
- `POST fleet`: add `{aircraft_ids: [...]}` atomically
- `DELETE fleet/{aircraft_id}`: remove a selection without deleting its record
- Existing aircraft create/update/delete endpoints manage database records.

Tests: `python -B -m unittest discover -s backend/tests -p 'test_fleet_selection.py' -v`
