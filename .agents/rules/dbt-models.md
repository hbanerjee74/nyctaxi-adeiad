# dbt models

Operator conventions for dbt models in `transformation/`. Where files live is declared in `repo-map.json`; this file covers naming and shape.

## Medallion mapping (B1)

- **Bronze**: raw data loaded by the dlt pipelines in `ingestion/` (schemas `bronze`, `ops_raw`, `mdm_raw`). dbt reads it as sources and never writes to it.
- **Silver**: dbt `staging` (views) and `intermediate` (tables). Staging renames and casts one source table. Intermediate applies business logic and joins, with no grain commitment of its own.
- **Gold**: dbt marts (`core`, `agg`, `finance`, `ops`): grain-committed facts, conformed dimensions, aggregates.

## Time zones (B17)

dlt lands naive Arrow timestamps as `TIMESTAMPTZ`, and the session time zone is not always UTC (the sandbox is not). Staging converts every dlt-loaded timestamp with `timezone('UTC', col)`, so later models see the wall-clock value the source recorded. A model that reads bronze without the conversion, or hashes a key from a converted and an unconverted timestamp, matches nothing and stays green.

## Naming (B2, B3)

| Prefix | Layer | Responsibility |
| --- | --- | --- |
| `stg_` | staging | One source table: rename and cast only |
| `int_` | intermediate | Business logic and joins, no grain commitment |
| `fct_` | gold | Grain-committed events |
| `dim_` | gold | Descriptive entities, conformed across facts |
| `agg_` | gold | Aggregates built from facts |
| `mart_` | gold | Consumption-shaped marts |

- Staging models are `stg_<source>__<entity>` (B3; double underscore), for example `stg_tlc__yellow_tripdata`.
- Intermediate and gold models name the entity directly.
- No `_fact` or `_dimension` suffix: the prefix carries it.

## Properties files (B6)

One YAML file per folder, named `_<folder>.yml` (`_staging.yml`, `_intermediate.yml`, `_core.yml`). Unit tests sit in `_unit_tests.yml` beside the models they cover.

## Columns (B8)

List columns explicitly. No `select *` in a mart.

## Audit columns (B12)

None unless a requirement asks for them. When one does: gold only, all or none of `_loaded_at`, `_dbt_invocation_id`, `_git_sha`.

## Materialisation (B15)

| Layer | Default |
| --- | --- |
| staging | view |
| intermediate | table |
| gold | table |

`fct_trip` is incremental by `trip_key`; a late-arriving trip at or before the loaded boundary needs a full refresh (see its design record).
