# VIBEDATA fields reference

Every `custom_extensions` entry with `vendor_name: VIBEDATA` carries a JSON-encoded object of one of four shapes, chosen by level (model, dataset, relationship, metric). Machine shapes live in `vibedata-schema.json` beside this file; this file explains what each field means. Key set is frozen (S6): unknown keys fail validation.

## Model level

| Field | Meaning | Example |
| --- | --- | --- |
| `vibedata_version` | Payload generation. Currently `"1.2"`: the frozen key set in this file. Every payload in a document, metric payloads included, carries the same version; bump only when the key set changes, and migrate all payloads together — mixed versions fail validation. History is under *Upgrades* below | `"1.2"` |
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
| `variables[]` | Named values a `content_filter` reads as `:name` (OBIEE repository variables). `name`, `datatype`, `dbt_var` (the dbt project var that supplies it, so the filter moves when the var moves), `note`. `tests/test_ossie_validate.py` fails a `dbt_var` the dbt project does not define | `{"name": "report_start", "datatype": "Date", "dbt_var": "report_start"}` |

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
| `logical_sources[].content_levels[]` | What the source holds, per dimension role (OBIEE LTS *Content*): `{via, hierarchy, level}`, where `via` is a relationship from this dataset and names the role. `via` alone means the target's own key level. A role not listed is aggregated away. The detail source declares none. This is what lets an engine choose an aggregate: a query is answerable when every level it groups by is at or above the declared one | `{"via": "trips_to_date", "hierarchy": "Time", "level": "day"}` |
| `logical_sources[].content_filter` | Row predicate every row of the source satisfies, in the dataset's declared fields and `:variables` (OBIEE fragmentation content). Covers the mart's `WHERE` **and** the rows its inner joins drop. An engine uses the source only when the query's own filter implies this one. Unlike the removed `where`, it is code, not prose: the validator resolves every name, and a source that binds anything must name the test that holds it (`held by <test>`) in its `note` | `"pickup_date >= :report_start AND pickup_date < :report_end AND is_billable"` |
| `logical_sources[].navigable` | `false` when the source's population is narrower than any row predicate can state (a `HAVING` floor). An engine then reads it only when asked for it by name. Default `true` | `false` |
| `logical_sources[].note` | Partial-mapping rationale: which columns were refused and why | `"billable_revenue refused: agg sums unfiltered totals"` |
| `logical_sources[].column_map` | Logical field-or-metric → physical column, per LTS. Aggregates map only what their grain supports; every field needs ≥1 non-`0` supplier | `{"pickup_date": "pickup_date"}` |
| `hierarchies[]` | Drill paths, coarsest level first: `name`, `is_time` (levels order chronologically, so time-series metrics may shift along them), and `levels[]` | `{"name": "Time", "is_time": true, "levels": [...]}` |
| `hierarchies[].levels[]` | `name`, `key` (the fields that identify one member: a month is `month_start_date`, never `calendar_month`, which repeats every year) and optional `label` (the field shown for a member) | `{"name": "zone", "key": ["zone_natural_key"], "label": "zone_name"}` |

## Relationship level

| Field | Meaning | Example |
| --- | --- | --- |
| `physical_join` | Handle into model `physical_joins` — the execution join for this logical relationship | `"fct_trip_to_Pickup_Zone"` |
| `cardinality` | `many-to-one`, `one-to-one`, or `many-to-many` (warns: no core FK equivalent, resolve through a bridge) | `"many-to-one"` |
| `join_type` | SQL join type (`LEFT OUTER`, …) | `"LEFT OUTER"` |
| `join_cost` | Relative cost for LTS selection, lower wins. Comparable only within one model; the only way to order aggregates, which `priority_group` cannot express | — |
| `note` | Why this relationship is declared without key-covering `to_columns`, or why a reachable path has no relationship | — |
| `join_expression` | Full predicate including SCD as-of clauses; the core `from/to` columns keep the equi fallback | `"pickup_date >= valid_from_date AND ..."` |

## Metric level

The core `expression` stays the metric's aggregate over detail rows. The payload says how an engine may answer it from anything else.

| Field | Meaning | Example |
| --- | --- | --- |
| `aggregation` | How a pre-aggregated column rolls up to a coarser grain (OBIEE aggregation rule): `SUM`, `MIN`, `MAX`, or `NON_ADDITIVE`, which never rolls up, so only a source at the query's own grain or the detail can answer (distinct counts) | `"SUM"` |
| `derived_expression` | Post-aggregation formula over other metrics (OBIEE logical-column measure). The metric binds to no column: an engine evaluates its inputs at the query's grain, then applies the formula, which is how a rate is rebuilt from summed numerator and denominator (ADR 0016). Binding one to a column fails `derived-metric-mapped`; `suppliers` counts it supplied when its inputs are | `"on_trip_hours * 1.0 / NULLIF(online_hours, 0)"` |
| `at_levels[]` | Level-based metric (OBIEE level-based measure): evaluated at these `{via, hierarchy, level}` levels whatever finer level the query groups by. The denominator of a share of parent | `{"via": "trips_to_pickup_zone", "hierarchy": "Geography", "level": "borough"}` |
| `time_series` | `function` (`AGO` with an `offset` of periods back, or `TODATE`), `of` (the metric shifted, whose core `expression` this metric must repeat), and the `via`/`hierarchy`/`level` period, on an `is_time` hierarchy | `{"function": "AGO", "of": "billable_revenue", "via": "trips_to_date", "hierarchy": "Time", "level": "month", "offset": 1}` |

`at_levels` and `time_series` change what the number means but not the core `expression`, so a consumer that ignores VIBEDATA must not expose those metrics: its value would be the base metric's.

## Upgrades

| Version | What moved | Why |
| --- | --- | --- |
| `1.1` | `logical_sources[].where` removed | It was prose; a population is a decision (ADR) held by a test, not a sentence |
| `1.2` | Added `variables`, `content_levels`, `content_filter`, `navigable`, metric payloads (`aggregation`, `derived_expression`, `at_levels`, `time_series`); hierarchy levels became `{name, key, label}` objects with `is_time` on the hierarchy; date gained `month_start_date` and `week_start_date` | An engine could not pick an aggregate (grain was prose), could not tell a windowed aggregate from the full fact (the aggregates silently covered fewer trips than the detail), keyed levels on non-unique columns (`calendar_month`, `zone_name`), and re-summed ratio columns. `content_filter` is the machine-checked successor of `where` |
