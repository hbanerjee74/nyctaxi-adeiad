# How the checker behaves

Read this when a gate surprises you. The rules live in `SKILL.md`; this file
explains what the tool actually inspects, so a green or red result is not
misread.

## Coverage of the checks

| Check | Reads | Does not read |
| --- | --- | --- |
| core validation | document structure, enums, references, `from_columns`/`to_columns`, SQL parses | `column_map` values, the repo's file list |
| VIBEDATA pass | key set per document component (metrics included), version consistency, LTS/source/alias references, grain/priority/column-map shape, levels (`keys` with exactly one primary and at most one display, attributes), `row_level` against the primary key and SCD, hierarchies against declared levels and `scd_rollup`, SCD field names, `from_columns` against declared fields, `content_levels`/`at_levels`/`time_series` against relationships and hierarchies, names in a `content_filter` (a `:placeholder` is an error) and its `held by` pointer, `derived_expression` inputs, that no column binds a derived, time-series or dimension-rule metric, one computation per metric and no cycles, a time-series or nested metric repeating its base expression, `FIRST`/`LAST` on a single time level | anything about meaning: honesty of a mapping, whether a filter matches the SQL, whether a level key is unique, population, additivity |
| cross-document drift | same-named datasets (`source`, keys, fields, `scd`, `hierarchies`, non-role logical sources including their content), metrics (expression and payload), physical tables (`source`, `dbt_model`, `table_type`, `alias_of`, `role`) | role logical sources and `note` text, which are local by design |
| `dimensionality` | per metric, the facts its expression reads and the dimensions reachable through many-to-one relationships and weighted bridges, derived metrics as the intersection of their inputs, `total` metrics as every dimension | queries: it reports reach, and the engine or exporter enforces it |
| `coverage` | dbt model file names under the model root the repo-map declares vs `dbt_model` values | anything inside the SQL |
| `suppliers` | declared fields and metrics with no `column_map` entry anywhere; a derived, time-series or dimension-rule metric counts as supplied when its inputs are | whether the mapped column exists in the mart |
| `level-tests` | the declared levels, hierarchies and aggregate content levels, turned into the warn-only dbt test `assert_semantic_levels_hold`; `--check` fails when the committed test is stale | the data: the dbt test reads it, and only reports |
| `content-tests` | every aggregate binding of a metric, compiled twice (the source under its content filter, and the detail under the same filter) into `assert_semantic_content_holds`, which fails on any difference: totals for a navigable source, each held group for one that is not; `--check` fails a stale file | whether a binding is the right business rule: an equal total proves the same population, not the right one |
| `columns` | every `column_map` target, aggregate `key_columns` and field-expression column against dbt's `catalog.json` (from `dbt docs generate` on a built warehouse) | whether the right column is mapped: only that it exists |
| `compile` | one semantic query: the source chosen, the rejected sources with reasons, the SQL | anything it reports as unsupported, which it refuses rather than guesses |
| `notes` | `held by <test>` and `ADR NNNN` pointers in a source `note`, resolved against the tests and ADR directories, and whether those directories exist | whether the test still tests what the note claims |
| ontology validation | the ontology schema, then unique concept names, `extends`/`identify_by`/`roles` resolving, declared QName prefixes | whether a concept is the right concept, whether identity is natural, whether an expression is executable |
| `refs` | `ontology_ref` and `semantic_model_ref` names against document names, every `concept`/`relationship` against the ontology, every `expression` against `dataset.field` in the referenced model, and a mapped concept's identity components against the relationships it maps | whether two mappings of one concept agree, whether the model's data honours the join |
| `glossary` | `**Term**:` headings in `CONTEXT.md` against `EntityType` concepts, in both directions | value types, which need no term; whether the term means what the concept says |
| `notes` | `held by <test>` and `ADR NNNN` pointers in a source `note`, resolved against the tests and ADR directories | whether the test still tests what the note claims |

## Behaviours worth knowing

- Cross-document comparison runs only when the directory holds more than one document.
- The VIBEDATA pass is skipped for a document that already fails the core checks, so fix core errors first.
- A missing `priority_group` defaults to `1`; nothing reports two detail-class sources.
- `validate` exits 1 only on structural errors. Warnings it emits are factual (for example `table-unjoined` — a table no join reaches, expected for a standalone document or an aggregate handle) and never fail the run.
- Unmatched files: a `*.y*ml` file in a validated directory that is not `*.ossie.yaml`, `*.ontology.yaml` or `*.mapping.yaml` is an error, so a mis-named document cannot be silently skipped.
- `validate` reads all three kinds and picks the schema from the document's own shape (`concept_mappings` → mapping, `ontology` → ontology, otherwise model). A directory can hold all three.
- The ontology checks are the ones the schema cannot make: an `EntityType` with no `identify_by` is an error, because identity is declared; `requires`, `derived_by`, `prefixes` or `custom_extensions` present is a warning, because nothing evaluates them.
- `refs` and `glossary` take directories, not files: identity is a claim across documents, so one document alone cannot answer it.
- A path that is not a directory, or a file that parses to something other than a document, is an error. A gate on a mistyped path must never report zero findings.
- `refs` reports `mapping/none` per model with no mapping, pointing at that model's file. It is a warning, and the reason goes in the model's own description, where a reader finds it.
- `glossary` reports a term with no concept as a `finding`, not an error: a term can name a rule, a measure or a decision, and those stay prose. It exits 1 only for an `EntityType` with no term.
- `coverage` and `suppliers` read model documents only, so they never trip over `.ontology.yaml` or `.mapping.yaml`.
