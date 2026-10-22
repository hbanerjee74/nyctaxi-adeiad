# How the checker behaves

Read this when a gate surprises you. The rules live in `SKILL.md`; this file
explains what the tool actually inspects, so a green or red result is not
misread.

## Coverage of the checks

| Check | Reads | Does not read |
| --- | --- | --- |
| core validation | document structure, enums, references, `from_columns`/`to_columns`, SQL parses | `column_map` values, the repo's file list |
| VIBEDATA pass | key set per level, version consistency, LTS/source/alias references, grain/priority/column-map shape, hierarchy and SCD field names, `from_columns` against declared fields | anything about meaning: honesty of a mapping, whether a field has a supplier, population, additivity |
| cross-document drift | same-named datasets (`source`, keys, fields, `scd`, `hierarchies`, non-role logical sources), metrics (expression), physical tables (`source`, `dbt_model`, `table_type`, `alias_of`, `role`) | role logical sources and `note` text, which are local by design |
| `coverage` | dbt model file names under the marts path vs `dbt_model` values | anything inside the SQL |

## Behaviours worth knowing

- Cross-document comparison runs only when the directory holds more than one document.
- The VIBEDATA pass is skipped for a document that already fails the core checks, so fix core errors first.
- A missing `priority_group` defaults to `1`; the validator warns (`no-detail-source`) only when no source is detail-class, so two detail sources pass.
- An empty `column_map` is accepted only with a `note` (a tombstone).
- `validate` exits 1 only on structural errors. Warnings it emits are factual (for example `table-unjoined` — a table no join reaches, expected for a standalone document or an aggregate handle) and never fail the run.
- Unmatched files: a `*.y*ml` file in the model directory that is not `*.ossie.yaml` is an error, so a mis-named model cannot be silently skipped.
