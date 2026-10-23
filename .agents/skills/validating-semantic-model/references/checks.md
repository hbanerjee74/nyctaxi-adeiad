# How the checker behaves

Read this when a gate surprises you. The rules live in `SKILL.md`; this file
explains what the tool actually inspects, so a green or red result is not
misread.

## Coverage of the checks

| Check | Reads | Does not read |
| --- | --- | --- |
| core validation | document structure, enums, references, `from_columns`/`to_columns`, SQL parses | `column_map` values, the repo's file list |
| VIBEDATA pass | key set per level (metrics included), version consistency, LTS/source/alias references, grain/priority/column-map shape, hierarchy level keys and labels, SCD field names, `from_columns` against declared fields, `content_levels`/`at_levels`/`time_series` against relationships and hierarchies, names and `:variables` in a `content_filter` and its `held by` pointer, `derived_expression` inputs, that no column binds a derived, time-series or nested metric, one computation per metric and no cycles, a time-series or nested metric repeating its base expression, `FIRST`/`LAST` on a single time level | anything about meaning: honesty of a mapping, whether a filter matches the SQL, whether a level key is unique, population, additivity |
| cross-document drift | same-named datasets (`source`, keys, fields, `scd`, `hierarchies`, non-role logical sources including their content), metrics (expression and payload), physical tables (`source`, `dbt_model`, `table_type`, `alias_of`, `role`) | role logical sources and `note` text, which are local by design |
| `coverage` | dbt model file names under the marts path vs `dbt_model` values | anything inside the SQL |
| `suppliers` | declared fields and metrics with no `column_map` entry anywhere; a derived, time-series or nested metric counts as supplied when its inputs are | whether the mapped column exists in the mart |
| `notes` | `held by <test>` and `ADR NNNN` pointers in a source `note`, resolved against the tests and ADR directories | whether the test still tests what the note claims |

## Behaviours worth knowing

- Cross-document comparison runs only when the directory holds more than one document.
- The VIBEDATA pass is skipped for a document that already fails the core checks, so fix core errors first.
- A missing `priority_group` defaults to `1`; nothing reports two detail-class sources.
- `validate` exits 1 only on structural errors. Warnings it emits are factual (for example `table-unjoined` — a table no join reaches, expected for a standalone document or an aggregate handle) and never fail the run.
- Unmatched files: a `*.y*ml` file in the model directory that is not `*.ossie.yaml` is an error, so a mis-named model cannot be silently skipped.
