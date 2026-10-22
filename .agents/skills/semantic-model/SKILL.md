---
name: semantic-model
description: "Use when creating or editing the canonical semantic model, its VIBEDATA extensions, validating it, or deciding which source supplies a field or measure."
---

# Semantic model

The canonical model is Apache Ossie `0.2.0.dev0` — canonical definition in the upstream repo (exact links and pinned commit live beside the vendored machine schema, which is never edited) — flat document, one model per file, plus `VIBEDATA` extensions for the Oracle-style mappings Ossie core has no room for (aliases, multi-source LTS, hierarchies, SCD, partitioning). Consumer formats (MetricFlow, Tableau, PowerBI) export from canonical on the fly and are never committed.

## Stars are atomic; documents partition stars (S1)

A fact star — its fact, the dims it reaches, its relationships, its metrics, its aggregate sources — lives wholly inside one document. It is never split across documents, and there is no shared-dimension document: Ossie resolves relationships within a document only, and the schema is closed, so a cross-document reference is unexpressible and a "shared dims" file would leave every star broken.

Two stars in one document share one copy of a common dimension. Two stars in separate documents each carry their own copy, and the copies must agree on the dimension's identity — `source`, keys, and every field — while the role-specific parts stay local: a role alias (`Pickup_Zone`) and a role logical source exist only in a document whose facts play that role. The validator compares same-named datasets, metrics, and physical tables across a directory and fails any that diverge in identity.

## Curated fields, not a mirror (S2)

`fields` are semantic attributes (keys, grouping/filtering dims, inputs to metric expressions) — a curated subset of the mart, never a column dump. Degenerate non-semantic columns stay out. A field the model drops is a scope decision, recorded in the change, not an oversight.

## Every field needs a supplying LTS (S3)

`logical_sources[].column_map` names the physical column behind each logical field or metric **per LTS**; an aggregate LTS maps only what its `content_grain` supports. Priority convention: `0` is the preferred aggregate, higher numbers are fallbacks ending at the detail grain — every field must be suppliable by at least one non-`0` source (`field-agg-only` fails otherwise). `content_grain` names the grain in the LTS table's own columns where they exist, falling back to the logical grain name for the detail source; it is a human-readable grain declaration (list of strings), not a validated reference. Right-side (physical) columns are verified against the mart definitions, never assumed identity.

Red-flag trap (seen in testing): mapping a filtered measure onto an unfiltered agg column, e.g. `billable_revenue` onto a monthly `total_revenue` — a monthly total is not billable-filtered revenue. `validate` warns (`agg-metric-unverified`) on any metric an aggregate source maps; treat the warning as guilty until the agg SQL proves it innocent.

## Aliases are physical rows, not flags (S4)

Role-playing (pickup vs dropoff zone) and fan-traps are separate `physical_tables` entries with `table_type: ALIAS` and `alias_of` naming the base table, each with its own physical join. A fan-trap is two or more declared paths into the same table, not the mere presence of a bridge; a bridge reached by one path needs no alias. Aggregate LTS tables point their joins at a dimension for reachability; no logical relationship backs them (aggs aren't datasets), and that dangle is structural, not a smell. The core `relationships[]` keep the equi fallback; the real predicate (including SCD as-of clauses) lives in the relationship's `join_expression`. A `physical_join` naming no model-level join fails `validate`.

## SCD and hierarchies ride the dataset (S5)

Versioned dimensions declare `scd`, level lists ride `hierarchies[]`, and truly partitioned storage declares `partitioned_by` — all naming real fields, all shaped per `vibedata-fields.md`.

## Frozen keys (S6)

The `VIBEDATA` key set per level is closed and machine-readable in the vibedata schema beside this file, with field-by-field meanings in `vibedata-fields.md` beside it. An unknown key fails validation (`unknown-key`). New keys arrive with their schema change, validator change, and tests, never by silent addition. `vibedata_version` rides every payload.

## Validate (S7)

The canonical file(s) touched by the change must validate green before commit. Every file validates standalone (`relationships` resolve within the document; there are no cross-file references), so duplication of shared dims is the rule, not a smell. The validate command emits JSON diagnostics on stdout and a human summary on stderr; exit 1 on any error, warnings allowed. Expect `agg-metric-unverified` on every correct aggregate LTS — the validator cannot see agg SQL, so the warning is routine on aggs and green includes it; answer it by confirming the agg column computes the same aggregation, not by dropping the mapping. After any mart change, update the canonical in the same change.

## Every lakehouse object is mapped or justified (S8)

Every dbt-built table in the star's lineage (fact, dims, aggs, consumption marts) either has a handle in `physical_tables` (with its `dbt_model`) or carries its reason on itself: unmappable tables get a `note` on the physical-table entry (truncated, wrong star, bridge treatment); partially mapped sources get a `note` on the logical source naming each refused column and why. Reasons ride the entries so they cannot drift from them; the design record keeps the narrative. The rule binds both directions: reverse-engineering during onboarding enumerates and justifies gaps; forward-engineering a new mart registers it or justifies its absence in the same change.

## Refactoring the model (S10)

The model is not append-only. These moves are normal work, each validated across every file afterwards, with no dual sources of truth left behind:

- **New standalone model.** An object that serves no star (bridge, rate table, direct-consumption mart) gets its own document named after what it models, one dataset, its own `physical_tables` entry, and a `note` saying why it stands alone. Never park it in a star it cannot join.
- **Fold a standalone model into a star.** When a join key lands, move the dataset into the consuming document, add the relationship and its `physical_joins` entry there, delete the standalone document, and correct every stale statement about the object wherever it lives — its `note`, description, `ai_context`, and any rule the new path invalidates. Relationships cannot cross documents, so leaving both is a second source of truth, not caution.
- **Split the model across documents.** Partition by whole stars (S1); each document keeps every dataset its own facts need, and shared dims are copied identically.
- **Move or rename a dataset.** Update every relationship, `physical_join`, and `logical_sources[].physical_table` that names it in the same change; leave no dangling reference for validation to find.

Name new relationships and joins after the existing pattern in the target document rather than inventing one.

### Fact-grain change

When a fact's grain changes, the primary key, the detail `content_grain`, and every count metric change together: a `SUM(CASE ...)`-style count silently becomes a finer-grained count, so count metrics need the distinct rollup key while additive money metrics stay sums. Then establish — by reading each aggregate's SQL, never by assumption — whether that aggregate was rebuilt at the old grain or the new one; if the answer is not available, that is an S9 question, not a default. A metric whose grain disagrees with the aggregate source supplying it is the most expensive silent error in the model.

### Business-rule change

When a definition changes (billable, active, in-window), withdraw — do not merely annotate — every binding whose source computes the old rule; a note alone leaves the stale column bindable, and a priority-0 aggregate outranks the already-correct detail. Withdraw the whole dependency chain: a field whose only supplier is withdrawn cannot stay declared, and a metric whose expression names a withdrawn field is a lie, so the field and metric go with the mapping. One source-level `note` covers a partial withdrawal: name every withdrawn binding and its exact restore condition in it. Correct any `ai_context` that states the old rule, and record the restore as one tracked follow-up per change (decision-record revision or issue), never as memory. An empty `column_map` is a tombstone and must carry that note.

### Aggregate lifecycle

- **Added**: register the table, its join, and its source at honest grain.
- **Rebuilt at a different grain**: re-derive that source's `content_grain` and `column_map` as a grain change.
- **Absorbed by detail** (detail now answers everything the aggregate did): drop the mappings and the handle once nothing names it; a dead aggregate is a stale definition waiting to be trusted.
- **Retired**: delete the handle, its joins, and every source naming it in the same change.

### Star decommission

Deleting a fact star means deleting its document and the handles only it used, after moving the decisions and reasons it carried into the repo's decision record. A document left behind holding half a star is worse than no document: it still validates.

Business rules ride the model, not a footnote to it: a threshold, filter, or bound that changes the answer belongs in the logical source's `where` and (when it is a standing business answer) in the repo's decision record. A rule is not a defect to route around. When a refactor makes a stated rule wrong on one path, that is a business ruling — ask under S9 and record the answer; never quietly rewrite the rule to fit the new shape.

## When mapping is blocked, ask — never guess, never silently skip (S9)

When a table cannot be honestly mapped (mart SQL unreadable, grain ambiguous, truncation or filtering defeats every honest mapping, bridge treatment unclear), stop and ask the user. One question per item, each with: what the table is, why it is blocked, the options with a recommendation, and what unblocks each option. Ask first; write the entry plus its `note` only once ruled — never pre-create entries for undecided items. Skipping silently and assuming are both failures — the former hides the gap S8 exists to close, the latter writes a lie the validator cannot catch. Record the user's ruling as a `note` on the entry in the same change.

Ask versus note-only: when the mart SQL leaves exactly one honest disposition (wrong star by its own header, truncation that defeats every mapping), record the `note` directly under S8. When two or more dispositions are plausible, or the analysis itself is uncertain (contradictory grain evidence, undefined treatment), ask under this rule.

## Common mistakes
- Identity column maps assumed from siblings. Verify every right-side column against the mart definitions.
- New physical table without its `physical_joins` entries. The table exists but no query can reach it; `table-unjoined` warns.
- New key invented inline instead of arriving with its schema, validator, and test change. `unknown-key` fails it.

## Red flags — stop and re-check

- "Validate is green, so the mapping is semantically right." Green proves shape and references, never business correctness.
- "The agg table must carry this column." Check the agg SQL; grain decides, not hope.
- "I haven't read the mart SQL, but the column name is obvious." Block: no mapping without reading the mart definitions. Unreadable mart means unmapped source with a `note`, never an assumed map.
- "One more key won't hurt." It fails. Use the schema file.
