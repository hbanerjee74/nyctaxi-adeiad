---
name: semantic-model
description: "Use when creating, editing or validating the canonical semantic model (Ossie, lakehouse logical model) — reverse-engineering it from dbt marts during onboarding, adding or refactoring a star, deciding which source supplies a field or measure, or explaining why a table is unmapped."
---

# Semantic model

The canonical model is Apache Ossie `0.2.0.dev0` — canonical definition in the upstream repo (exact links and pinned commit live beside the vendored machine schema, which is never edited) — flat document, one model per file, plus `VIBEDATA` extensions for the Oracle-style mappings Ossie core has no room for (aliases, multi-source LTS, hierarchies, SCD, partitioning). Consumer formats (MetricFlow, Tableau, PowerBI) export from canonical on the fly and are never committed. `examples/standalone.ossie.yaml` beside this file is the shape for a table with no star; `examples/star.ossie.yaml` is the shape to copy for a star: one document, one fact, a role-playing dimension reached by two relationships, one aggregate source, and the two-level VIBEDATA payloads (one at model level for `physical_tables`/`physical_joins`, one per dataset and per relationship, each `data` a JSON-encoded string).

## Quick reference

| Question | Answer |
| --- | --- |
| Which commands gate a change? | `validate <dir>` (structure, references, VIBEDATA) and `coverage <dir> <marts>` (gold tables vs `dbt_model`); both must exit 0 |
| Where does a refused column go? | The detail source's `note`, naming each column and why |
| Where does an unmappable table's reason go? | A `note` on its `physical_tables` entry |
| Where does a blocked decision go? | Ask first (S9); write the entry plus its `note` only once ruled |
| Where does a business rule go? | The source's `where`, plus the repo's decision record when it is standing |
| Aggregate source or standalone document? | Population decides (S10): star population rolled up → aggregate; narrower or different population → standalone |
| Detail or aggregate priority? | Detail-class `1` (one per role), aggregate `0` |

## Stars are atomic; documents partition stars (S1)

A fact star — its fact, the dims it reaches, its relationships, its metrics, its aggregate sources — lives wholly inside one document. It is never split across documents, and there is no shared-dimension document: Ossie resolves relationships within a document only, and the schema is closed, so a cross-document reference is unexpressible and a "shared dims" file would leave every star broken.

A fact-to-fact key (a trip carrying `shift_id`) stays a degenerate field on the referencing fact unless both facts live in one document; never import another star's fact as a dataset to express the path. Two stars in one document share one copy of a common dimension. Two stars in separate documents each carry their own copy, and the copies must agree on the dimension's identity — `source`, keys, and every field — while the role-specific parts stay local: a role alias (`Pickup_Zone`) and a role logical source exist only in a document whose facts play that role. The validator compares same-named datasets, metrics, and physical tables across a directory and fails any that diverge in identity.

## Curated fields, not a mirror (S2)

`fields` are semantic attributes (keys, grouping/filtering dims, inputs to metric expressions) — a curated subset of the mart, never a column dump. Degenerate non-semantic columns stay out. A field the model drops is a scope decision, recorded in the change, not an oversight. Money types are `Decimal`, other floating values `Float`, integrals `Integer`; a vendor type outside the enum pairs `Opaque` with a `custom_extensions` note.

## Every field needs a supplying LTS (S3)

`logical_sources[].column_map` names the physical column behind each logical field or metric **per LTS**; an aggregate LTS maps only what its `content_grain` supports. Priority: detail-class `1` (one per role), aggregate `0`. The validator reads *any* non-zero value as detail supply and only warns when none exists, so inventing `2, 3, …` for aggregates makes an aggregate-only field look detail-supplied; order aggregates with the relationship's `join_cost` instead. Every field must be suppliable by the detail source (`field-agg-only` fails otherwise). `content_grain` names the grain in the LTS table's own result columns — including a derived one such as `weather_class` — falling back to the logical grain name only where no column expresses it; for a period-grain table name the period key (`shift_month`), never just the entity key, which reads as a false grain. It is a human-readable declaration (list of strings), not a validated reference. Right-side (physical) columns are verified by you against the mart SQL, never assumed identity — `validate` cannot see them, so a map onto a column that does not exist is green.

A join narrows the population just as effectively as a filter — an inner join against a banding seed with half-open ranges, a non-null join, a `distinct` collapse. That makes the table population-narrowed (S10), not an aggregate source; bind no metric whose population moves.

Metric names are compared across documents, so a name may not mean two populations: a metric answering a narrower population than the star's takes a scope-prefixed name (`billable_zone_day_trip_count`), and a star metric name is never reused on a filtered table.

Red-flag trap (seen in testing): mapping a filtered measure onto an unfiltered agg column, e.g. `billable_revenue` onto a monthly `total_revenue` — a monthly total is not billable-filtered revenue. `validate` warns (`agg-metric-unverified`) on any metric an aggregate source maps; treat the warning as guilty until the agg SQL proves it innocent.

## Additivity decides which measure becomes a metric (S3a)

A measure is additive only across the dims it can be summed over. A semi-additive fact — vehicle down-days (sums across vehicles, not across overlapping ranges), a balance, a headcount snapshot, a stock level — never becomes a plain `SUM` metric, because every consumer will then sum it across the dim it forbids. State the additivity limit in the field description and in the fact dataset's `description`, then choose one: supply no metric, and record the refusal in the detail source's `note` with the shape a legal metric would need; define a metric that expands to the legal grain (a daily expansion, an end-of-period pick); or define a per-event mean as ratio-of-sums over the same event count, which never totals the measure and so does not cross the forbidden dimension. An aggregate source whose grain crosses the forbidden dimension cannot supply that measure at all. `validate` cannot tell a plain `SUM` of a semi-additive measure from a legal one, so this is a rule you keep, not a check that keeps you.

## Aliases are physical rows, not flags (S4)

A role-playing dimension is one dataset and N relationships: `zone` stays a single dataset, `trips_to_pickup_zone` and `trips_to_dropoff_zone` both target it with different `from_columns`, and each relationship's `physical_join` names its own `physical_tables` entry with `table_type: ALIAS` and `alias_of` pointing at the base table. Do not clone the dimension into `pickup_zone`/`dropoff_zone` datasets — the endpoints that differ are the relationship's columns and the alias handle, not the dataset. A fan-trap is two or more declared paths into the same table with no distinguishing role; a bridge reached by one path needs no alias. Aggregate LTS tables point their joins at a dimension for reachability; no logical relationship backs them (aggs aren't datasets), and that dangle is structural, not a smell. The core `relationships[]` keep the equi fallback; the real predicate (including SCD as-of clauses) lives in the relationship's `join_expression`. A `physical_join` naming no model-level join fails `validate`.

## SCD and hierarchies ride the dataset (S5)

Versioned dimensions declare `scd`, level lists ride `hierarchies[]`, and truly partitioned storage declares `partitioned_by` — all naming real fields, all shaped per `vibedata-fields.md`.

## Frozen keys (S6)

The `VIBEDATA` key set per level is closed and machine-readable in the vibedata schema beside this file, with field-by-field meanings in `vibedata-fields.md` beside it. An unknown key fails validation (`unknown-key`). New keys arrive with their schema change, validator change, and tests, never by silent addition. `vibedata_version` rides every payload.

## Validate (S7)

The canonical file(s) touched by the change must validate green before commit. Every file validates standalone (`relationships` resolve within the document; there are no cross-file references), so duplication of shared dims is the rule, not a smell. The validate command emits JSON diagnostics on stdout and a human summary on stderr; exit 1 on any error, warnings allowed. Two warnings are expected and are not findings: one `agg-metric-unverified` per metric binding on an aggregate source, and `table-unjoined` for a standalone document or an aggregate handle. Every other warning is a finding. That includes the upstream validator's warnings that carry no `code` — typically a relationship whose `to_columns` do not cover the target's key; fix those by declaring `unique_keys` on the target dataset or by joining on its key. A handle registered with a `note` and no logical source counts as an aggregate handle for `table-unjoined`. Answer each `agg-metric-unverified` by confirming, against the agg SQL, that the agg column computes that same aggregation — never by dropping the mapping — and record that sentence in the source's own `note`; a warning with no such note is an open finding. A finding that is not fixed must be recorded on the entry that owns it, or the change is not done. Green is necessary but not sufficient: `validate` never reads `column_map` values or the repo's file list. Cross-document comparison runs only when the directory holds more than one document, and the VIBEDATA pass is skipped for a document that already fails the upstream checks, so fix core errors first. Run the tool's `coverage` command (marts on disk vs `dbt_model` names) before claiming S8 is satisfied: it must exit 0. After any mart change, update the canonical in the same change.

## Every lakehouse object is mapped or justified (S8)

Scope is the gold marts — facts, dims, aggregates, consumption marts. Staging views, intermediate models and seeds are upstream of the model and never appear as handles — but a seed a gold table joins is an input to that table, and a join against it that narrows the population is recorded with that table (see S3). Build the inventory before partitioning documents: list every dbt model under the marts path, then read every mart's FROM/JOIN refs, because a table's star membership is only visible from its inputs. Every gold table either has a handle in `physical_tables` (with its `dbt_model`) or carries its reason on itself: unmappable tables get a `note` on the physical-table entry (truncated, wrong star, bridge treatment); partially mapped sources get a `note` on the logical source naming each refused column and why. Reasons ride the entries so they cannot drift from them. The rule binds both directions: reverse-engineering during onboarding enumerates and justifies gaps; forward-engineering a new mart registers it or justifies its absence in the same change.

## When mapping is blocked, ask — never guess, never silently skip (S9)

When a table cannot be honestly mapped (mart SQL unreadable, grain ambiguous, truncation or filtering defeats every honest mapping, bridge treatment unclear), stop and ask the user. One question per item, each with: what the table is, why it is blocked, the options with a recommendation, and what unblocks each option. Ask first; write the entry plus its `note` only once ruled — never pre-create entries for undecided items. Skipping silently and assuming are both failures — the former hides the gap S8 exists to close, the latter writes a lie the validator cannot catch. Record the user's ruling as a `note` on the entry in the same change.

Ask versus note-only: when the mart SQL leaves exactly one honest disposition (wrong star by its own header, truncation that defeats every mapping), record the `note` directly under S8. When two or more dispositions are plausible, or the analysis itself is uncertain (contradictory grain evidence, undefined treatment), ask under this rule.

## Refactoring the model (S10)

The model is not append-only. These moves are normal work, each validated across every file afterwards, with no dual sources of truth left behind:

- **New standalone model.** An object that serves no star (bridge, rate table, direct-consumption mart) gets its own document named after what it models, one dataset, its own `physical_tables` entry, and a `note` saying why it stands alone. Never park it in a star it cannot join.
- **Fold a standalone model into a star.** When a join key lands, move the dataset into the consuming document, add the relationship and its `physical_joins` entry there, delete the standalone document, and correct every stale statement about the object wherever it lives — its `note`, description, `ai_context`, and any rule the new path invalidates. Relationships cannot cross documents, so leaving both is a second source of truth, not caution.
- **Split the model across documents.** Partition by whole stars (S1); each document keeps every dataset its own facts need, and shared dims are copied so their identity matches (S1).
- **Move or rename a dataset.** Update every relationship, `physical_join`, and `logical_sources[].physical_table` that names it in the same change; leave no dangling reference for validation to find.

Name new relationships and joins after the existing pattern in the target document; when you are creating the document there is no pattern yet, so follow the example beside this file (`trips_to_<target>`, `fct_<fact>_to_<table>`, `LTS<n>_<purpose>`).

### Aggregate source or standalone document

Population, never the presence of a `where`, decides the disposition. An aggregate source may carry the report window in `where` when its grain is the star's grain rolled up and its population is still the star's population — every `agg_*` rollup is this case. A table whose population is narrower or different — a changed measure definition (billable, payment class), a truncation (`HAVING count >= 25`), an inner join that silently drops rows — is a standalone document, because its counts answer a different question. A table constructed from, or consumed by, two stars is standalone too. A standalone document has no relationships and therefore always raises `table-unjoined`; that is expected there.

### Fact-grain change

When a fact's grain changes, the primary key, the detail `content_grain`, and every count metric change together: a `SUM(CASE ...)`-style count silently becomes a finer-grained count, so count metrics need the distinct rollup key while additive money metrics stay sums. Then establish — by reading each aggregate's SQL, never by assumption — whether that aggregate was rebuilt at the old grain or the new one; if the answer is not available, that is an S9 question, not a default. A metric whose grain disagrees with the aggregate source supplying it is the most expensive silent error in the model.

### Business-rule change

When a definition changes (billable, active, in-window), withdraw — do not merely annotate — every binding whose source computes the old rule; a note alone leaves the stale column bindable, and a priority-0 aggregate outranks the already-correct detail. Withdraw the whole dependency chain: a field whose only supplier is withdrawn cannot stay declared, and a metric whose expression names a withdrawn field is a lie, so the field and metric go with the mapping. One source-level `note` covers a partial withdrawal: name every withdrawn binding and its exact restore condition in it. Correct any `ai_context` that states the old rule, move the rule itself into the source's `where` and the repo's decision record when it is standing, and record the restore as one tracked follow-up per change (decision-record revision or issue), never as memory. An empty `column_map` is a tombstone and must carry that note.

### Aggregate lifecycle

- **Added**: register the table, its join, and its source at honest grain.
- **Rebuilt at a different grain**: re-derive that source's `content_grain` and `column_map` as a grain change.
- **Absorbed by detail** (detail now answers everything the aggregate did): drop the mappings and the handle once nothing names it; a dead aggregate is a stale definition waiting to be trusted.
- **Retired**: delete the handle, its joins, and every source naming it in the same change.

### Star decommission

Deleting a fact star means deleting its document and the handles only it used, after moving the decisions and reasons it carried into the repo's decision record. A document left behind holding half a star is worse than no document: it still validates.

Business rules ride the model, not a footnote to it: a threshold, filter, or bound that changes the answer belongs in the logical source's `where` and (when it is a standing business answer) in the repo's decision record. When a refactor makes a stated rule wrong on one path, that is a business ruling — ask under S9; never quietly rewrite the rule to fit the new shape.

## Common mistakes
- Identity column maps assumed from siblings. Verify every right-side column against the mart definitions.
- New physical table without its `physical_joins` entries. The table exists but no query can reach it; `table-unjoined` warns.
- New key invented inline instead of arriving with its schema, validator, and test change. `unknown-key` fails it.

## Red flags — stop and re-check

- "Validate is green, so the mapping is semantically right." Green proves shape and references, never business correctness.
- "The agg table must carry this column." Check the agg SQL; grain decides, not hope.
- "I haven't read the mart SQL, but the column name is obvious." Block: no mapping without reading the mart definitions. Unreadable mart means unmapped source with a `note`, never an assumed map.
- "One more key won't hurt." It fails. Use the schema file.
