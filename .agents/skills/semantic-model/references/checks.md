# How the checker behaves

Read this when a gate surprises you. The rules live in `SKILL.md`; this file
explains what the tool actually inspects, so a green or red result is not
misread.

## Coverage of the checks

| Check | Reads | Does not read |
| --- | --- | --- |
| core validation | document structure, enums, references, `from_columns`/`to_columns`, SQL parses | `column_map` values, the repo's file list |
| VIBEDATA pass | key set per level, version consistency, LTS/source/alias references, grain and priority shape, hierarchy and SCD field names | mart SQL, warehouse state |
| cross-document drift | same-named datasets (`source`, keys, fields, `scd`, `hierarchies`, non-role logical sources), metrics (expression), physical tables (`source`, `dbt_model`, `table_type`, `alias_of`, `role`) | role logical sources and `note` text, which are local by design |
| `coverage` | dbt model file names under the marts path vs `dbt_model` values | anything inside the SQL |

## Behaviours worth knowing

- Cross-document comparison runs only when the directory holds more than one document.
- The VIBEDATA pass is skipped for a document that already fails the core checks, so fix core errors first.
- A missing `priority_group` defaults to `1`; the validator warns (`no-detail-source`) only when no source is detail-class, so two detail sources pass.
- An empty `column_map` is accepted only with a `note` (a tombstone).
- Warnings carry no exit-code effect; only errors do.
