---
name: ontology
description: "Use when creating or changing a business ontology or an ontology mapping in a repo that has a glossary — declaring concepts and relationships, mapping them to a canonical model, and checking the result before commit. Not for authoring metrics or dbt models."
---

# The business ontology

The ontology renders the repo's glossary as concepts and relationships at the pinned Apache Ossie spec. It is the only artifact that states an object is the same object across the canonical model's documents. Mappings connect concepts to the fields of exactly one document.

It sits at the language layer, beside the glossary, not above the gold marts. A concept can be declared before any dataset carries it, and a dataset at any layer can populate one. Read the artifact paths from `repo-map.json`; never assume a directory.

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
4. Run the gates from `validating-semantic-model` step 1: `validate`, then `refs`, then `glossary`.
5. Report the concepts declared, the concepts mapped, each document left unmapped with its reason, each relationship left unmapped with its reason, and the declaration-only status.

Adding a concept whose term is missing is one change: write the term or do not declare the concept. The ontology never invents vocabulary.

## Red flags — stop and re-check

- "The join column is the identity." A surrogate that changes per version is not identity; the natural key is. A join column is also not automatically a referent: map the relationship only when the column carries the target's identity.
- "It validates, so it works." Validation proves shape. No evaluator reads an expression.
- "The concept is obvious, the term is implied." Add the term in the same change, or drop the concept.
- "This document has no concepts, so no mapping is needed." Report it unmapped with the reason; silence reads as covered.
- "The schema allows `requires`." Allowed is not readable: nothing evaluates it, so the rule belongs in an ADR.
