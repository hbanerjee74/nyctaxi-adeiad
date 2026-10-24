---
name: validating-ontology
description: "Use when checking a business ontology or its mappings before commit, after a gold mart or metric change, or when asked whether a concept, its identity or a mapping is honest. Covers the structural run, the coverage a tool cannot see, and the content review against the semantic model."
---

# Validating an ontology

Its own step, not a corner of the semantic-model review: the ontology makes claims the model cannot state, and the model makes claims the ontology cannot check. This skill validates the ontology and its mappings against the canonical model, and the `validating-semantic-model` skill validates the model against the ontology's terms.

Python proves shape only: the schema, the names, and whether an expression names a field that exists. The schema it loads is the vendored spec beside the validator — `semantic-model/scripts/ossie_vendor/ontology/ontology.json` and `.../mapping.json` — so a construct rejected here is rejected by the pinned spec, not by local taste; read the `$defs` rather than arguing with the error. Coverage — is every table classified, does every concept reach a dataset — and meaning have no tool. Read `../validating-semantic-model/references/checks.md` for what the commands can and cannot see.

## Step 1 — structure

From the repo root, with the paths `repo-map.json` declares:

- `python3 .agents/skills/semantic-model/scripts/ossie.py validate <ontology-dir>` — exit 0, zero errors.
- `... ossie.py refs <ontology-dir> <model-dir>` — exit 0, zero errors.

`refs` proves the mapping references resolve by document `name`, that every `concept` and `relationship` is declared, and that every expression is a `dataset.field` the referenced document declares. It cannot see whether the expression means what the mapping says. Record each command with its exit code.

## Step 2 — coverage

The tool cannot count what is absent, so this step is a read, not a command. Enumerate the gold marts and classify every `dim_*` and `fct_*` with the table in the `ontology` skill. Then check:

1. **Every table is classified.** A dimension, transactional fact or event-derived interval either has a concept or carries its exemption where a reader finds it — a junk dimension, a degenerate key, a rebuilt state snapshot, an effective-dated rule, a bridge or an aggregate. A table nobody classified is a finding, and so is a concept invented for one of those kinds. A table the author could not classify is a blocked finding with the question it raised, never an omission.
2. **Every concept reaches a dataset.** A concept with no mapping anywhere is either ahead of its data, with its description saying so, or a finding.
3. **Every identity component is mapped.** A concept mapped on only some of the relationships its `identify_by` names is a partial identity — a gap to report, never a complete mapping.
4. **Every document is accounted for.** Each canonical document is mapped, or its own description says why no concept reaches it.
5. **Every dataset carrying a concept's identity is mapped.** A dataset whose key is a concept's identity and has no object mapping understates the model even when another dataset states the same concept.
6. **The glossary holds both ways.** Run `... ossie.py glossary <ontology-dir> <CONTEXT.md>` and read the three lists as signals, not a verdict: the command reports drift and always exits 0.
   - `entity_types_without_term` — always a finding. An entity type must have a word in the business's vocabulary; add the term or drop the concept.
   - `terms_without_concept` — adjudicate every entry. A rule, measure, population, period, classification or version stays prose; a term naming a thing with identity is a missing concept, added in the same change.
   - `value_types_without_term` — expected. A value type carries identity and needs no glossary word.
   The report carries the three lists and the category given to each term, so a reviewer can disagree with the call rather than having to re-derive it.

## Step 3 — content

Work from the mart SQL and the model, never from the mapping's own prose.

7. **Identity is natural.** Each `identify_by` reaches the value holding the entity's natural key in the mart or its staging SQL. A surrogate over natural key plus valid-from is a version; a key with no natural code beside it is a surrogate the report names as such.
8. **A relationship's direction and multiplicity match the foreign key.** The inverse is implicit; a declared inverse, or two relationships where one would do, is a finding.
9. **Cross-document identity is the claim under test.** Where two documents map one concept, both expressions identify the same real-world object. A mapping that bridges them through a version surrogate asserts an identity the data does not have.
10. **A versioned or re-grained dataset has had its mappings re-derived.** A mapping that still resolves to a real field can still identify the wrong thing after a grain change, a Type 1-to-Type 2 change, or a natural key replaced by a surrogate.
11. **Declaration status.** No `requires`, `derived_by`, `prefixes` or vendor payload, and no `iri` on a concept or relationship: an identifier for another party's vocabulary, named with its release, or omitted. The report says plainly that no tool parses, converts or executes a mapping.

## Step 4 — report

The verdict, then every finding as location → evidence → fix, then the checks you could not run and why. A verdict of "passes" cites a file per claim.

Close with two sections:

- **Coverage**: the classification table, one row per gold mart — conceptually carried, exempt with the reason and where it is recorded.
- **Declaration versus executable**: which artifacts were checked for shape, which expressions no tool reads, and which concepts or documents are unmapped with their reasons.

## Red flags — stop and re-check

- "The join column is the identity." A surrogate that changes per version is not identity.
- "It validates, so the mapping works." Nothing executes a mapping; shape is all a tool proves.
- "The glossary is the coverage list." The glossary names what the business says, not what the lakehouse holds. Both directions matter.
- "An aggregate is a fact." A rollup's rows are a population, not an event; it gets a metric, not a concept.
- "Every table needs a concept." Junk dimensions, bridges, derived snapshots and rule tables exist to make queries cheap, not to name a thing.
- "The name matches, so the concept is covered." A term and a concept can be spelled alike and disagree; step 3 reads the SQL.
- "The table fits no row exactly, so the nearest one will do." That is a question for the user, not a classification: a wrong row silently deletes a concept or invents one.
