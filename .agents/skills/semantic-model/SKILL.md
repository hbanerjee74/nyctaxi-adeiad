---
name: semantic-model
description: "Use when creating or editing the canonical semantic model, its VIBEDATA extensions, or when validating it."
---

# Semantic model

The canonical model is Apache Ossie `0.2.0.dev0` — canonical definition in the upstream repo (exact links and pinned commit live beside the vendored machine schema, which is never edited) — flat document, one model per file, plus `VIBEDATA` extensions for the Oracle-style mappings Ossie core has no room for (aliases, multi-source LTS, hierarchies, SCD, partitioning). Consumer formats (MetricFlow, Tableau, PowerBI) export from canonical on the fly and are never committed.

## Curated fields, not a mirror (S2)

`fields` are semantic attributes (keys, grouping/filtering dims, inputs to metric expressions) — a curated subset of the mart, never a column dump. Degenerate non-semantic columns stay out. A field the model drops is a scope decision, recorded in the change, not an oversight.

## Every field needs a supplying LTS (S3)

`logical_sources[].column_map` names the physical column behind each logical field or metric **per LTS**; an aggregate LTS maps only what its `content_grain` supports. Priority convention: `0` is the preferred aggregate, higher numbers are fallbacks ending at the detail grain — every field must be suppliable by at least one non-`0` source (`field-agg-only` fails otherwise). `content_grain` names the grain in the LTS table's own columns where they exist, falling back to the logical grain name for the detail source; it is a human-readable grain declaration (list of strings), not a validated reference. Right-side (physical) columns are verified against the mart definitions, never assumed identity.

Red-flag trap (seen in testing): mapping a filtered measure onto an unfiltered agg column, e.g. `billable_revenue` onto a monthly `total_revenue` — a monthly total is not billable-filtered revenue. `validate` warns (`agg-metric-unverified`) on any metric an aggregate source maps; treat the warning as guilty until the agg SQL proves it innocent.

## Aliases are physical rows, not flags (S4)

Role-playing (pickup vs dropoff zone) and fan-traps are separate `physical_tables` entries with `table_type: ALIAS` and `alias_of` naming the base table, each with its own physical join. The core `relationships[]` keep the equi fallback; the real predicate (including SCD as-of clauses) lives in the relationship's `join_expression`. A `physical_join` naming no model-level join fails `validate`.

## SCD and hierarchies ride the dataset (S5)

Versioned dimensions declare `scd: {type, natural_key, valid_from, valid_to, is_current, open_ended_value}` naming real fields; level lists in `hierarchies[]` name real fields. `partitioned_by`, when a table is truly partitioned storage, is a column list.

## Frozen keys (S6)

The `VIBEDATA` key set per level is closed and machine-readable in the vibedata schema beside this file, with field-by-field meanings in `vibedata-fields.md` beside it. An unknown key fails validation (`unknown-key`). New keys arrive with their schema change, validator change, and tests, never by silent addition. `vibedata_version` rides every payload.

## Validate (S7)

The canonical file(s) touched by the change must validate green before commit. Every file validates standalone (`relationships` resolve within the document; there are no cross-file references), so duplication of shared dims is the rule, not a smell. The validate command emits JSON diagnostics on stdout and a human summary on stderr; exit 1 on any error, warnings allowed. Expect `agg-metric-unverified` on every correct aggregate LTS — the validator cannot see agg SQL, so the warning is routine on aggs and green includes it; answer it by confirming the agg column computes the same aggregation, not by dropping the mapping. After any mart change, update the canonical in the same change.
