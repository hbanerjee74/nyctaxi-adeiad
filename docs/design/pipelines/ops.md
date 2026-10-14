---
artifacts: [ops]
---

# ops

Loads the fleet operator's dispatch and telematics platform, a simulated source system, into `ops_raw`.

## Grain

Eight resources, one row per entity: garage, vehicle, driver, lease agreement, shift, trip assignment, driver status event and maintenance event.

## Decisions

- `D-01` Generate the operator's records deterministically in memory with DuckDB, derived from the yellow trips, which are read in memory and never written; the pipeline loads the eight `ops_raw` tables only ([ADR 0008](../../adr/0008-simulated-sources-are-generated-inside-their-pipelines.md)). Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0008](../../adr/0008-simulated-sources-are-generated-inside-their-pipelines.md).
- `D-02` The operator identifies a trip by its natural columns and carries no `trip_key` ([ADR 0007](../../adr/0007-trip-key-has-one-definition.md)). Attribution hashes the natural columns, so the attributed trips differ from the earlier arrangement. Source: intents/setup-dlt-ingestion/requirement.md R-03, [ADR 0007](../../adr/0007-trip-key-has-one-definition.md).
- `D-03` Remove overlapping trips on one vehicle repeatedly until none remain; a single pass left some behind. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0008](../../adr/0008-simulated-sources-are-generated-inside-their-pipelines.md).
- `D-04` Keep the deliberate imperfections a real feed has: shifts that never log out, events that arrive out of order, missing odometer readings. dbt flags them; the pipeline does not clean them. Source: [ADR 0008](../../adr/0008-simulated-sources-are-generated-inside-their-pipelines.md).
- `D-05` `garage`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `garage_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-06` `vehicle`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `vehicle_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-07` `driver`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `driver_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-08` `lease_agreement`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `lease_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-09` `shift`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `shift_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-10` `trip_assignment`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `assignment_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-11` `driver_status_event`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `event_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-12` `maintenance_event`: write disposition `replace` (each run reloads the whole fixed window); no incremental cursor; contract `columns: freeze`, `tables: evolve`, `data_type: freeze`; duplicate keys: none expected: `maintenance_id` is unique by construction. Source: intents/setup-dlt-ingestion/requirement.md R-01, [ADR 0005](../../adr/0005-all-raw-sources-are-loaded-by-dlt.md).
- `D-13` `tables` stays `evolve` for the same reason as the `tlc` pipeline. Source: intents/setup-dlt-ingestion/requirement.md R-01.

## Rejected

- Writing the generated tables straight into the warehouse: it bypasses the load path every other source uses.
- A dlt transformer on the TLC trips resource: shifts and overlaps span monthly files, so the generator needs every trip at once.

## Consumers

Depended on by: `stg_ops__drivers`, `stg_ops__garages`, `stg_ops__leases`, `stg_ops__maintenance`, `stg_ops__shifts`, `stg_ops__status_events`, `stg_ops__trip_assignments`, `stg_ops__vehicles`.

## Evidence

- Counts on the three-month load: driver 760; driver_status_event 1,807,117; garage 6; lease_agreement 760; maintenance_event 848; shift 38,205; trip_assignment 463,848 (4.8% of yellow trips); vehicle 420. A second run leaves them unchanged, and `bronze` is untouched by the ops run.
- Pipeline: `ingestion/ops_pipeline.py`; source: `ingestion/sources/ops.py`; resource docs: `ingestion/docs/ops.yml`.

## History

- - 2026-10-14 — setup-dlt-ingestion — design record written when the generator moved from a script into a dlt pipeline — D-01 to D-13
