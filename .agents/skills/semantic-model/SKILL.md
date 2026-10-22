---
name: semantic-model
description: "Use when creating, editing or validating the canonical semantic model (Ossie, lakehouse logical model) — reverse-engineering it from dbt marts during onboarding, adding or refactoring a star, deciding which source supplies a field or measure, or explaining why a table is unmapped."
---

# Semantic model

The canonical model is Apache Ossie `0.2.0.dev0` — canonical definition in the upstream repo (exact links and pinned commit live beside the vendored machine schema, which is never edited) — flat document, one model per file, plus `VIBEDATA` extensions for the Oracle-style mappings Ossie core has no room for (aliases, multi-source LTS, hierarchies, SCD, partitioning). Consumer formats (MetricFlow, Tableau, PowerBI) export from canonical on the fly and are never committed. Before commit, run the `validating-semantic-model` skill for the content review. Open `references/refactoring.md` for split, fold, rename, grain-change, rule-change, aggregate-lifecycle and star-retirement work; `references/reverse-engineering.md` when onboarding a lakehouse or adding a mart; `references/vibedata-fields.md` for what a payload field means; `examples/standalone.ossie.yaml` beside this file is the shape for a table with no star; `examples/star.ossie.yaml` is the shape to copy for a star: one document, one fact, a role-playing dimension reached by two relationships, one aggregate source, and the two-level VIBEDATA payloads (one at model level for `physical_tables`/`physical_joins`, one per dataset and per relationship, each `data` a JSON-encoded string).

## Quick reference

| Question | Answer |
| --- | --- |
| Which commands gate a change? | `validate <dir>` (structure, references, VIBEDATA) and `coverage <dir> <marts>` (gold tables vs `dbt_model`); both must exit 0 |
| Where does a refused column go? | The detail source's `note`, naming each column and why |
| Where does an unmappable table's reason go? | A `note` on its `physical_tables` entry |
| Where does a blocked decision go? | Ask first (`references/reverse-engineering.md`); write the entry plus its `note` only once ruled |
| Where does a business rule go? | The source's `where`, plus the repo's decision record when it is standing |
| Aggregate source or standalone document? | Population decides (`references/refactoring.md`): star population rolled up → aggregate; narrower or different population → standalone |
| Detail or aggregate priority? | Detail-class `1` (one per role), aggregate `0` |

## Stars are atomic; documents partition stars (S1)

A fact's star is the set of dimension keys the fact carries as columns: every foreign key on the fact is a relationship into that dimension, whether or not the fact's own SQL joins it. `physical_join` names the equi join a consumer would execute; the fact's own `FROM`/`JOIN` refs only decide which aggregate sources are honest. A fact star — its fact, those dims, its relationships, its metrics, its aggregate sources — lives wholly inside one document. It is never split across documents, and there is no shared-dimension document: Ossie resolves relationships within a document only, and the schema is closed, so a cross-document reference is unexpressible and a "shared dims" file would leave every star broken.

Tables the population rule makes standalone share a document when they share a population: such a document declares no relationships and raises one `table-unjoined` per table, all expected. A dimension no gold fact can reach — an effective-dated reference table joined upstream — gets a one-dataset document whose `physical_tables` note carries the reason; that is not a shared-dimension document. A fact-to-fact key (a trip carrying `shift_id`) stays a degenerate field on the referencing fact unless both facts live in one document; never import another star's fact as a dataset to express the path. Two stars in one document share one copy of a common dimension. Two stars in separate documents each carry their own copy, and the copies must agree on the dimension's identity — `source`, keys, and every field — while the role-specific parts stay local: a role alias (`Pickup_Zone`) and a role logical source exist only in a document whose facts play that role. The validator compares same-named datasets, metrics, and physical tables across a directory and fails any that diverge in identity.

## Curated fields, not a mirror (S2)

`fields` are semantic attributes (keys, grouping/filtering dims, inputs to metric expressions) — a curated subset of the mart, never a column dump. Degenerate non-semantic columns stay out. A field the model drops is a scope decision, recorded in the change, not an oversight. Money types are `Decimal`, other floating values `Float`, integrals `Integer`; a vendor type outside the enum pairs `Opaque` with a `custom_extensions` note.

## Every field needs a supplying LTS (S3)

`logical_sources[].column_map` names the physical column behind each logical field or metric **per LTS**; an aggregate LTS maps only what its `content_grain` supports. Priority: detail-class `1` (one per role), aggregate `0`. The validator reads *any* non-zero value as detail supply and only warns when none exists, so inventing `2, 3, …` for aggregates makes an aggregate-only field look detail-supplied; order aggregates with the relationship's `join_cost` instead. Every field must be suppliable by the detail source (`field-agg-only` fails otherwise). `content_grain` names the grain in the LTS table's own result columns — including a derived one such as `weather_class` — falling back to the logical grain name only where no column expresses it; for a period-grain table name the period key (`shift_month`), never just the entity key, which reads as a false grain. It is a human-readable declaration (list of strings), not a validated reference. Right-side (physical) columns are verified by you against the mart SQL, never assumed identity — `validate` cannot see them, so a map onto a column that does not exist is green.

A join narrows the population just as effectively as a filter — an inner join against a banding seed with half-open ranges, a non-null join, a `distinct` collapse. That makes the table population-narrowed, not an aggregate source (`references/refactoring.md`); bind no metric whose population moves.

Metric names are compared across documents, so a name may not mean two populations: a metric answering a narrower population than the star's takes a scope-prefixed name (`billable_zone_day_trip_count`); a measure that also exists on another fact is named `<fact>_<measure>` (`shift_trip_count`); and a star metric name is never reused on a filtered table. A ratio is one metric whose expression divides two `SUM`s (`SUM(a) * 1.0 / NULLIF(SUM(b), 0)`), datatype `Decimal` — never two helper metrics that a consumer might add.

Red-flag trap (seen in testing): mapping a filtered measure onto an unfiltered agg column, e.g. `billable_revenue` onto a monthly `total_revenue` — a monthly total is not billable-filtered revenue. No automated check can see this: treat every aggregate metric binding as guilty until the agg SQL proves it innocent, and record that proof in the source's `note` (the `validating-semantic-model` skill reviews it).

## Additivity decides which measure becomes a metric (S3a)

A measure is additive only across the dims it can be summed over. A semi-additive fact — vehicle down-days (sums across vehicles, not across overlapping ranges), a balance, a headcount snapshot, a stock level — never becomes a plain `SUM` metric, because every consumer will then sum it across the dim it forbids. State the additivity limit in the field description and in the fact dataset's `description`, then choose one: supply no metric, and record the refusal in the detail source's `note` with the shape a legal metric would need; define a metric that expands to the legal grain (a daily expansion, an end-of-period pick); or define a per-event mean as ratio-of-sums over the same event count, which never totals the measure and so does not cross the forbidden dimension. An aggregate source whose grain crosses the forbidden dimension cannot supply that measure at all. `validate` cannot tell a plain `SUM` of a semi-additive measure from a legal one, so this is a rule you keep, not a check that keeps you.

## Aliases are physical rows, not flags (S4)

A role-playing dimension is one dataset and N relationships: `zone` stays a single dataset, `trips_to_pickup_zone` and `trips_to_dropoff_zone` both target it with different `from_columns`, and each relationship's `physical_join` names its own `physical_tables` entry with `table_type: ALIAS` and `alias_of` pointing at the base table. Do not clone the dimension into `pickup_zone`/`dropoff_zone` datasets — the endpoints that differ are the relationship's columns and the alias handle, not the dataset. A fan-trap is two or more declared paths into the same table with no distinguishing role; a bridge reached by one path needs no alias. Aggregate LTS tables point their joins at a dimension for reachability; no logical relationship backs them (aggs aren't datasets), and that dangle is structural, not a smell. The core `relationships[]` keep the equi fallback; the real predicate (including SCD as-of clauses) lives in the relationship's `join_expression`. A `physical_join` naming no model-level join fails `validate`.

## SCD and hierarchies ride the dataset (S5)

Versioned dimensions declare `scd`, their business key in `unique_keys` (`[[natural_key, valid_from]]`), level lists in `hierarchies[]`, and truly partitioned storage in `partitioned_by` — all naming real fields, all shaped per `references/vibedata-fields.md`.

## Frozen keys (S6)

The `VIBEDATA` key set per level is closed and machine-readable in the vibedata schema beside this file, with field-by-field meanings in `references/vibedata-fields.md`. An unknown key fails validation (`unknown-key`). New keys arrive with their schema change, validator change, and tests, never by silent addition. `vibedata_version` rides every payload.

## Validate (S7)

Before commit, run the `validating-semantic-model` skill: it executes the structural gate (`validate`, `coverage`) and then reviews whether every mapping is honest. `validate` checks structure only — schema, names, references, payload keys, file naming — so a green run never means the content is right. The tool exits 1 on errors; a warning such as `table-unjoined` is factual (a table no join reaches), expected for standalone documents and aggregate handles.

After any mart change, update the canonical in the same change.

## Common mistakes
- Identity column maps assumed from siblings. Verify every right-side column against the mart definitions.
- New physical table without its `physical_joins` entries. The table exists but no query can reach it; `table-unjoined` warns.
- New key invented inline instead of arriving with its schema, validator, and test change. `unknown-key` fails it.

## Red flags — stop and re-check

- "Validate is green, so the mapping is semantically right." Green proves shape and references, never business correctness.
- "The agg table must carry this column." Check the agg SQL; grain decides, not hope.
- "I haven't read the mart SQL, but the column name is obvious." Block: no mapping without reading the mart definitions. Unreadable mart means unmapped source with a `note`, never an assumed map.
- "One more key won't hurt." It fails. Use the schema file.
