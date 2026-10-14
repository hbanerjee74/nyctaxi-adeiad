# dlt ingestion

Operator conventions for the pipelines in `ingestion/`. Where files live is declared in `repo-map.json`.

## Datasets (D5)

A pipeline's dataset is the schema it feeds: `bronze` (TLC), `ops_raw`, `mdm_raw`. Not `src_<connection>`.

## Write disposition (D6)

Set per resource, never per run: `append` for immutable events that arrive once, `replace` for a full reload of a fixed window, `merge` for mutable records with a key. Every resource here is `replace`: each run reloads the whole fixed window.

## Schema contract (D7)

`columns: freeze`, `tables: evolve` while a pipeline is new then `freeze` once every resource has loaded into a database that persists, `data_type: freeze`. A pipeline whose database is rebuilt from empty on every run keeps `tables: evolve`, because freezing it would forbid creating the tables. Any other value carries a `# why:` line in the pipeline and a decision in its design record.

## Bronze carries no logic (D8)

No transformation, casts, joins or filters in a pipeline. A pipeline loads what the source gives it. Simulated sources generate their data, but do not clean it.

## `_dlt_*` columns (D8b)

Never drop or alias them.

## Sample loads (D10)

A safety run or sample load sets `DLT_INGEST_LIMIT` (default 1,000 rows); a full load leaves it unset. No committed limit.

## Local-files feeds (D14)

A local-files feed is a one-off load and is not scheduled. Not applicable until this repo has one.
