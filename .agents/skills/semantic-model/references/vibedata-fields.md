# VIBEDATA fields reference

Every `custom_extensions` entry with `vendor_name: VIBEDATA` carries a JSON-encoded object of one of three shapes, chosen by level. Machine shapes live in `vibedata-schema.json` beside this file; this file explains what each field means. Key set is frozen (S6): unknown keys fail validation.

## Model level

| Field | Meaning | Example |
| --- | --- | --- |
| `vibedata_version` | Payload generation. Currently `"1.1"`: the frozen key set in this file (`"1.0"` carried a `where` field, removed because a population is a decision, not a document). Every payload in a document carries the same version; bump to `"1.1"` etc. only when the key set changes, and migrate all payloads together — mixed versions fail validation | `"1.0"` |
| `physical_tables[]` | Full physical inventory: originals plus aliases. One entry per physical table or role | — |
| `physical_tables[].name` | Repo-local handle other blocks reference | `"Pickup_Zone"` |
| `physical_tables[].source` | `schema.table` (dbt mart) the handle points at | `"core.dim_zone"` |
| `physical_tables[].dbt_model` | dbt `ref()` name that builds this table; aliases name their base model. Links mart changes to the canonical entries they touch | `"dim_zone"` |
| `physical_tables[].table_type` | `TABLE`, `VIEW`, `ALIAS`, `OPAQUE_VIEW`, `STORED_PROC`, or `SYNONYM` | `"ALIAS"` |
| `physical_tables[].alias_of` | Base table handle, ALIAS only | `"dim_zone"` |
| `physical_tables[].role` | Business role of the alias, ALIAS only | `"origin zone for trips"` |
| `physical_tables[].note` | Why-not or partial-mapping rationale, recorded where it cannot drift | `"truncated at HAVING count>=25; no honest mapping"` |
| `physical_joins[]` | Physical execution joins between handles (one logical join maps to N of these, one per LTS combination) | — |
| `physical_joins[].{name,from,to}` | Join handle and its two physical-table endpoints | — |

## Dataset level

| Field | Meaning | Example |
| --- | --- | --- |
| `alias_of` | Dataset plays an aliased role (rare; aliases usually live in `physical_tables`) | — |
| `physical` | Free-form physical notes about the backing table | — |
| `partitioned_by[]` | Storage partition columns, only when truly partitioned storage | — |
| `scd` | Slowly-changing-dimension shape: `type` (1/2/3), `natural_key`, `valid_from`, `valid_to`, `is_current` (field names), `open_ended_value` (e.g. `"2099-12-31"`) | — |
| `logical_sources[]` | LTS list: every physical path that can supply this logical table (S3) | — |
| `logical_sources[].name` | LTS handle (`LTS1_detail`, `LTS2_zone_day_agg`) | — |
| `logical_sources[].physical_table` | Handle into model `physical_tables` | `"fct_trip"` |
| `logical_sources[].priority_group` | `1` on the single detail source, `0` on every aggregate source. Preference among aggregates is not expressible here — the validator reads any non-zero as a detail supplier | `0` |
| `logical_sources[].content_grain` | Grain in the LTS table's own columns where they exist — they may be columns the dataset does not declare — else the logical grain name (`trip`). Human-readable, not validated | `["pickup_date", "pickup_location_id"]` |
| `logical_sources[].note` | Partial-mapping rationale: which columns were refused and why | `"billable_revenue refused: agg sums unfiltered totals"` |
| `logical_sources[].column_map` | Logical field-or-metric → physical column, per LTS. Aggregates map only what their grain supports; every field needs ≥1 non-`0` supplier | `{"pickup_date": "pickup_date"}` |
| `hierarchies[]` | Drill paths: `name` plus ordered `levels[]` naming real fields | `{"name": "Time", "levels": [...]}` |

## Relationship level

| Field | Meaning | Example |
| --- | --- | --- |
| `physical_join` | Handle into model `physical_joins` — the execution join for this logical relationship | `"fct_trip_to_Pickup_Zone"` |
| `cardinality` | `many-to-one`, `one-to-one`, or `many-to-many` (warns: no core FK equivalent, resolve through a bridge) | `"many-to-one"` |
| `join_type` | SQL join type (`LEFT OUTER`, …) | `"LEFT OUTER"` |
| `join_cost` | Relative cost for LTS selection, lower wins. Comparable only within one model; the only way to order aggregates, which `priority_group` cannot express | — |
| `note` | Why this relationship is declared without key-covering `to_columns`, or why a reachable path has no relationship | — |
| `join_expression` | Full predicate including SCD as-of clauses; the core `from/to` columns keep the equi fallback | `"pickup_date >= valid_from_date AND ..."` |
