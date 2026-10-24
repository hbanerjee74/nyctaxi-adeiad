---
name: ontology
description: "Use when creating or changing a business ontology or an ontology mapping in a repo that has a glossary — classifying the gold tables, declaring concepts and relationships, and mapping them to a canonical model. Not for authoring metrics or dbt models, and not for the review itself."
---

# The business ontology

The ontology renders the repo's glossary as concepts and relationships at the pinned Apache Ossie spec. It is the only artifact that states an object is the same object across the canonical model's documents. Mappings connect concepts to the fields of exactly one document.

It sits at the language layer, beside the glossary, not above the gold marts. A concept can be declared before any dataset carries it, and a dataset at any layer can populate one. Read the artifact paths from `repo-map.json`; never assume a directory.

**The schema is a file, not a memory.** The allowed fields are the vendored specs: `semantic-model/scripts/ossie_vendor/ontology/ontology.json` for a concept document and `.../ontology/mapping.json` for a mapping. Both are pinned to the same upstream commit as the validator, and `validate` loads exactly these files. Read the relevant `$defs` before writing a construct — a field you half-remember is not in the spec, and a field that is in the spec but unused here is still a declaration nothing reads.

## Rules

1. **The glossary is the source.** Every concept names a glossary term. A term that denotes a rule, decision or derived measure gets no concept and stays prose. A term that denotes a thing with identity gets one. Check both directions.
2. **One ontology, one mapping per document.** Concepts are global and never cloned per document. A mapping references exactly one canonical document.
3. **Identity is natural.** `identify_by` names a declared relationship to a `ValueType`. Never a surrogate, never a version: a column that changes when the entity is re-designated is not identity. The same test applies to every relationship's referent: the expression must carry the target concept's own identity, so a foreign key that is a version of the target leaves the relationship unmapped.
4. **One direction per relationship.** The declared direction is the foreign key the lakehouse has, with `ManyToOne`; only an identifying relationship is `OneToOne`. The inverse is implicit and never declared. `roles` names the concepts at the far end; the relationship name carries the role, so two roles are two relationships to one concept.
5. **Versioning is not a concept.** The ontology has no valid-time, as-of predicate or one-to-many multiplicity. History is declared in the canonical model. When a document exposes only a version surrogate for a concept — a key over natural key plus valid-from — the relationship is left unmapped and the gap is reported; the surrogate is not a stand-in for the target's identity, and writing it into a referent asserts an identity the data does not have.
6. **Layer-agnostic.** A mapping expression is exactly `dataset.field` as the referenced document declares it — never a schema, table or layer, and never a bare field.
7. **Declaration-only.** No `requires`, `derived_by` or `custom_extensions`, no `prefixes`, and no `iri` on a concept or relationship — an identifier for an external vocabulary nothing resolves. A mapping's `ontology_ref` and `semantic_model_ref` may carry the `iri` the schema gives them, because that names a document, not a meaning. Nothing parses, converts or executes a mapping: never write that one works, and never describe a green run as proof of behaviour.
8. **Re-pin as one change.** The core, ontology and mapping schemas are vendored from one commit. A re-pin moves all four files, the checker and the parity test together.

## Workflow

1. Read the glossary and the canonical documents the map names.
2. Declare the value types, then the entity types with `identify_by`, then the relationships.
3. Write one mapping per canonical document, for the concepts that reach it. A document none reach gets no mapping, and its own description says why.
4. Validate with `validating-ontology`: its step 1 (`validate`, `refs`), then its coverage step — the classification below, in full.
5. Report the concepts declared, the concepts mapped, each table's classification, each document left unmapped with its reason, each relationship left unmapped with its reason, and the declaration-only status.

Adding a concept whose term is missing is one change: write the term or do not declare the concept. The ontology never invents vocabulary.

## When the canonical model changes

A mart change can leave a mapping true in form and false in meaning: the expression still names a declared `dataset.field` while the column now holds a version, a different grain or a narrower population. So the model change and the ontology change are one change:

- Re-run `refs` after the model edit. It catches a renamed document, dataset or field, and a concept mapped on only some of its identity components.
- Add the mapping entry for every dataset the change produced that carries a concept. A dataset no concept reaches gets no entry, and its document's description says why — never silence.
- When the identity moves — a grain change, a Type 1 dimension becoming Type 2, a natural key replaced by a surrogate — change the concept, its `CONTEXT.md` sentence and every mapping of that concept in the same commit. A mapping that still resolves is not evidence that it still identifies the same thing.
- A concept with no dataset anywhere is a declaration ahead of its data and its description says so; a dataset with a concept and no mapping is a gap.

Nothing tests the meaning of that update: `refs` proves fields exist, and the review item on cross-document identity is the only thing that reads it.


## Which tables get a concept

The ontology is not a mirror of the star schema, and it is not the glossary alone. Every gold `dim_*` and `fct_*` table is classified before any concept is declared: the classification decides whether it gets a concept, and the reason a table does not gets written where a reader will look for it — the table's own description, or the model document that carries it.

| Table kind, read from the name and the SQL | Concept? | What it becomes instead |
| --- | --- | --- |
| Conformed dimension: same meaning and key in more than one document | Yes, an `EntityType` | — |
| Reference dimension: one meaningful attribute, a name or a code | Yes, an `EntityType` | — |
| Transactional fact: one row per event the business names | Yes, an `EntityType` | its numbers are metrics, not concepts |
| Junk dimension: a bundle of unrelated low-cardinality flags | No | attributes of the concept that owns them |
| Degenerate dimension: an identifier with no table, a key on the fact | No | an identity component or a relationship |
| Event-derived interval fact: one row per derived interval the business names, with its own id | Yes, an `EntityType` | its durations are metrics; the derivation is the model's business |
| Rebuilt state snapshot: a state recomputed as of a date, no interval of its own | No | the rule that derives it, in an ADR |
| Effective-dated rule table: rates, thresholds, bands | No | the rule, in an ADR |
| Bridge: two concepts many-to-many, with a weight | No | the relationship's `weight` in the model |
| Aggregate or service mart: a rollup or a report shape | No | metrics on the concepts it rolls up |
| Transferable entity: a licence, contract or membership whose holder changes over time | Yes, an `EntityType` of its own | the current holding as a `ManyToOne`; the transfers as a gap in the model |

Two consequences worth stating:

- **A classification is not a vocabulary.** A missing `CONTEXT.md` term blocks a concept whatever the table is; add the term in the same change.
- **A classification is not an identity.** A reference dimension whose only key is a surrogate still gets a concept when the business names it, but its identity is that key and the mapping says the natural code is absent. Do not invent a code to satisfy the rule.

Every table in the layer appears in the report's classification table, including the ones that get nothing.


## When in doubt, ask — never skip

A silent gap reads as coverage. Every one of these is a question to the user, one at a time, with the options and a recommendation, before a concept is declared or omitted:

- **The table fits no row of the classification.** A junk dimension with one meaningful flag, an interval fact rebuilt from events, a rule table a fact joins as if it were a dimension: name the two readings and ask which the business means.
- **The standard cannot state the relation.** A many-to-many over time, a validity window, a transfer. Declare what the standard can hold, and say what it cannot — never widen one concept to absorb the other.
- **Identity cannot be proven from the SQL.** A `*_key` with no code beside it, a name that might rename, a column that might be a surrogate.
- **A term is missing.** Add it in the same change, or ask whether the business names the thing at all.
- **Two concepts seem to name one object,** or one concept seems to name two.

Record the ruling where the artifact lives — the concept's description, the mapping's description, or the table's note — and list the table in the report as ruled or blocked. A blocked table is a finding, never an omission.

Do not pick the nearest row of the classification and move on, and do not invent a concept so the table has somewhere to go. The classification is a question the model cannot answer on its own.

## Red flags — stop and re-check

- "The join column is the identity." A surrogate that changes per version is not identity; the natural key is. A join column is also not automatically a referent: map the relationship only when the column carries the target's identity.
- "It validates, so it works." Validation proves shape. No evaluator reads an expression.
- "The concept is obvious, the term is implied." Add the term in the same change, or drop the concept.
- "This document has no concepts, so no mapping is needed." Report it unmapped with the reason; silence reads as covered.
- "Every table needs a concept." Junk dimensions, bridges, snapshots and rule tables exist to make queries cheap, not to name a thing.
- "The glossary is the coverage list." It names what the business says, not what the lakehouse holds; classify the tables, then check the terms.
- "It is close enough to one of the rows." Close enough is how a snapshot becomes a concept and a licence becomes a vehicle attribute. Ask.
- "I will leave it out and nobody will notice." An omission in an ontology reads as a statement that the thing does not exist.
- "The schema allows `requires`." Allowed is not readable: nothing evaluates it, so the rule belongs in an ADR.
