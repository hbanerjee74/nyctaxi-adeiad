---
name: semantic-model
description: "Use when creating or editing the canonical semantic model in logical-model/, its VIBEDATA extensions, or when validating it with tools/ossie.py."
---

# Semantic model

Operator conventions for the canonical semantic model in `logical-model/`. Where files live is declared in `repo-map.json` (`artifact_paths.logical_model`); this file covers shape and rules. The model is Apache Ossie `0.2.0.dev0` (flat document, one model per file) plus `VIBEDATA` extensions for the Oracle-style mappings Ossie core has no room for (aliases, multi-source LTS, hierarchies, SCD, partitioning). Consumer formats (MetricFlow, Tableau, PowerBI) export from canonical on the fly and are never committed.

## One star per file (S1)

One model document holds one fact star plus the shared dimensions it needs (today: the trips star). Dimensions repeat across files; each file re-declares only the slice its star uses. The tooling supports one-or-many via the `repo-map.json` glob; the layout is the repo owner's call, not the tool's.

## Curated fields, not a mirror (S2)

`fields` are semantic attributes (keys, grouping/filtering dims, inputs to metric expressions) — a curated subset of the mart, never a column dump. Degenerate non-semantic columns stay out. A field the model drops is a scope decision, recorded in the intent, not an oversight.

## Every field needs a supplying LTS (S3)

`logical_sources[].column_map` names the physical column behind each logical field or metric **per LTS**; an aggregate LTS maps only what its `content_grain` supports (it must not map row-identity columns, and it must not map a measure its grain cannot compute — e.g. `billable_revenue` has no home in a day-grain agg). A field no LTS supplies fails `validate` (`field-unmapped`): the mapping is the consumer's path, so there is no guessing.

## Aliases are physical rows, not flags (S4)

Role-playing (pickup vs dropoff zone) and fan-traps are separate `physical_tables` entries with `table_type: ALIAS` and `alias_of` naming the base table, each with its own physical join. The core `relationships[]` keep the equi fallback; the real predicate (including SCD as-of clauses) lives in the relationship's `join_expression`. A `physical_join` naming no model-level join fails `validate`.

## SCD and hierarchies ride the dataset (S5)

Versioned dimensions declare `scd: {type, natural_key, valid_from, valid_to, is_current, open_ended_value}` naming real fields; level lists in `hierarchies[]` name real fields. `partitioned_by`, when a table is truly partitioned storage, is a column list.

## Frozen keys (S6)

The `VIBEDATA` key set per level is closed; an unknown key fails `validate` (`unknown-key`). New keys arrive by intent with a validator change and tests, never by silent addition. `vibedata_version` rides every payload.

## Validate (S7)

`python3 tools/ossie.py validate logical-model/` is green before any commit touching marts or the canonical file. JSON diagnostics go to stdout; the human summary to stderr; exit 1 on any error, warnings allowed. After any mart SQL, `_core.yml`, or `_semantic.yml` change, update the canonical in the same intent (see `workarounds`).
