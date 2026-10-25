---
name: data-contract
description: "Use when a relation or a column a consumer reads is added, changed or removed; when a column needs a quality rule, a grain, or the target it references; when a published shape, type or rule changes under a consumer; or when adopting an existing repo into data contracts. Not for building the model or the pipeline that produces the relation."
---

# Data contracts

A data contract is the promise a consumer reads: what the relation is, what one row of it means, what each property holds, and what must be true of it. The contract is **authored**. The keys that make dbt and dlt enforce it are **generated** from the contract, and a hand edit there is a second, silent source of truth. This skill keeps the two halves apart.

Every location comes from `repo-map.json`: `artifact_paths.data_contract` places the contracts, `artifact_paths.review` the queue of doubts, `artifact_paths.logical_model` the canonical documents, and each layer's `path` the relations it builds. `odcs.py` beside this skill is the tool; run it from the repo root. Its `check` proves shape and agreement, never meaning.

Two orders, and never the other way round:

- **Changing a relation:** profile it and the column, decide the contract, `generate`, then the SQL or pipeline, then the build.
- **Adopting an existing repo:** rebuild with `--full-refresh`, `reverse` once, take its findings into the review, triage them, `generate`, `check`.

## Quick reference

| Question | Answer |
| --- | --- |
| Where does a column's promise go? | The contract's `properties[]`; then `generate` writes the keys the build reads |
| May I write `data_type`, `data_tests`, `contract.enforced` or a dlt hint? | No. `generate` owns them, and `check` cannot tell a hand-written key from a generated one when the value happens to match |
| I added a property. Which version? | Minor. Removed or renamed property, changed type or grain, withdrawn rule, or `required` newly refusing a value a consumer receives: major. Description only: patch |
| Where does a quality rule go? | `quality` on the property, in the standard's library shape; `generate` renders the dbt test |
| A rule no dbt test can express? | Declare it in `quality` and say in the rule's `description` that the build does not enforce it. Never hand-write the test beside it |
| Which `logicalType`? | The canonical model's, where its document declares the field; the physical type's otherwise |
| The model does not declare the column — do I add it? | No. The model is curated; the contract carries every column regardless |
| Is this `_dlt_*` column mine? | Not on a relation the loader creates. Yes on one a dbt model selects it through |
| No grain statement available? | Omit it; `check` warns and the review queues it. Never invent the sentence |
| The only description is `{{ doc(...) }}`? | Omit it. A pointer is not prose |
| Which type string? | `physicalType` on every property: the built relation's own type, or the profiled expression's before the column exists. Never a normalized type |
| A type the mapper does not know? | A refusal, not a guess. Report it |
| Nothing to say in a section? | Omit the key. An empty one claims a promise nobody made, and `check` fails it |
| Where does an unsettled doubt go? | The review artifact at `artifact_paths.review`, as a question |
| May I run `reverse` to refresh the contracts? | Not on a repo that has contracts. Plain `reverse` skips them; `--force` replaces them |
| What comes before `reverse`? | A full refresh of the warehouse |
| What comes before commit? | `generate`, then `check`, exit 0 with only the warnings the review already owns |

## The contract is authored; the keys are generated

**Authored:** the document itself — `version`, `status`, `schema[].name`, `dataGranularityDescription`, and each property's `name`, `logicalType`, `physicalType`, `required`, `primaryKey`, `description`, `quality` and `relationships`.

**Generated:** the relation entry's `contract: {enforced: true}`, every `data_type` and `data_tests` under it, the column hints for a relation dlt loads, and the tests for a relation dbt loads from a CSV.

`generate` finds the properties file that already names the relation and writes its keys there, or creates the one it owns. It writes nothing it cannot ground: a property with no `physicalType`, a relationship naming no `<relation>.<column>`, a `servers[].schema` that disagrees with the map — the run refuses, writes no file at all, and exits 1. Fix the contract, run it again.

`check` then compares what `generate` would write with what is on disk (`generated/stale`). That is a comparison of values, and it is why a hand-written `data_type` that happens to be correct passes. Only running `generate` proves the key was generated.

## A new property is a decision about the promise

The column is the smallest part of it. Decide these in order:

1. **What it holds.** `physicalType` from the built relation — or, before the column exists, from the profiled expression; `logicalType` as the next section says; `required` only when null is impossible or forbidden.
2. **What it promises.** A `description` a consumer can act on; a `quality` rule, or the stated reason there is none; a `relationships` entry where it points into another relation. `required: true` declares that a null is not allowed but renders no test: when a null must fail the build, add `nullValues` `mustBe: 0` too.
3. **Whether the grain moved.** A new relation needs `dataGranularityDescription`. A new column on an existing one leaves the grain alone unless it changes what one row is.
4. **The version.** A property added, a rule added, a relationship declared: minor. A property removed or renamed, a `logicalType` or `physicalType` changed, the grain changed, a rule withdrawn, or `required` newly disallowing a value a consumer may already receive: major. A description or `authoritativeDefinitions` edit: patch. `1.0.0` is a version, not a placeholder; a `1.0.0` contract that gains a column becomes `1.1.0`.

This is the whole forward path for one property:

```yaml
version: 1.1.0                    # 1.0.0 -> 1.1.0: a property added, no consumer query breaks
schema:
  - name: <relation>
    properties:
      - name: <property>
        logicalType: boolean      # the model's datatype where it declares the field
        physicalType: BOOLEAN     # the expression's profiled type; the build proves it
        description: <what true means to a consumer>
        quality:
          - type: library
            metric: nullValues
            mustBe: 0
```

`generate` then adds `contract: {enforced: true}` to the relation, and `data_type: BOOLEAN` and `data_tests: [not_null]` to the property. Those keys are never written by hand; the version is. The property ships in the build that carries it, with the contract enforced.

A new relation, in a repo that already has contracts, is the same path from a sibling's document: copy its `apiVersion` and `kind`, give it its own `id` and `version: 1.0.0`, and change every place it names the relation — `name`, `schema[].name`, `servers[].schema`.

## `quality` is the rule; the dbt test is its rendering

A rule is `{type: library, metric, mustBe}`. `generate` renders exactly three: `nullValues` with `mustBe: 0` to `not_null`, `duplicateValues` with `mustBe: 0` to `unique`, and `invalidValues` with `mustBe: 0` and `arguments.valid_values` to `accepted_values`. Any other metric or operator, and any `text`, `sql` or `custom` rule, states a promise the build does not enforce: keep it when it is the honest statement of the rule, and say so in the rule's own `description`. Never write the dbt test beside it, and never let a rule live only as a hand-written test.

`primaryKey` and `required` are declarations too, and neither renders a test. A key that must be unique and never null carries both rules. Both are promises, so either one moves the version.

## The canonical model owns the logical type, not the column set

On a relation the canonical model documents, the contract is a projection of that document, not a second opinion. Every field the document declares must appear — a missing one fails `check`; `logicalType` is the document's `datatype` under the standard's mapping; `DateTimeTz` carries `logicalTypeOptions: {timezone: true}` and `DateTime` carries none; a field in the document's `primary_key` sets `primaryKey: true`. A disagreement on any of those fails `check` too.

A property the document does not declare is the contract's business. State its type and promise there and leave the model alone: the model is a curated subset for consumers of the semantic layer, and a relation column does not enlarge it. **REQUIRED SUB-SKILL:** Use `semantic-model` when the field's meaning has to enter the model; the contract does not make that decision, and when the model changes the two artifacts change in one commit.

## What the loader adds is not the relation's shape

A relation dlt creates owns its own bookkeeping. A `_dlt_*` column is added by the loader to the table, not yielded by the resource, so the contract does not declare it; `check` fails `contract/loader-column` when one appears. The exception is a dbt model that selects such a column through: its contract is enforced, so every output column must be declared, and dropping the property to satisfy the loader rule breaks the build. Read which one the relation is from the map's layer, never from the column name.

## Prose, grain and type are never invented

**Prose is authored or absent.** A description says what a consumer needs; a `{{ doc(...) }}` reference is a dbt parse-time pointer and is omitted rather than copied. A templated grain states no grain.

**The grain is one sentence about a row.** It lives in `dataGranularityDescription` and comes from a description that already states it — a blurb that describes the relation without saying what one row is does not. When none exists, omit it: `check` warns `contract/no-grain` and the review carries the question. An invented sentence is worse than the warning, because nothing downstream can tell it is wrong.

**`physicalType` on every property, verbatim.** It is the warehouse's type string, never a normalized one: `generate` writes the dbt `data_type` from it and maps it to a dlt column type. Read it from the built relation where the column exists. A property the change adds has no column to read yet, and `generate` needs the type before the build, so profile the expression — `typeof`, `DESCRIBE`, or the type the query returns against the warehouse — and author that; the enforced contract proves it at the build. Never build first to read the type, because that inverts the authored-first order this skill enforces. A property without one, or a type the mapper does not know, is a refusal (`contract/unmapped-type`); the nearest known type is a lie the build will enforce.

## Absence is the only honest no promise

An empty `quality`, `servers`, `tags` or `authoritativeDefinitions` claims a promise nobody made, and `check` fails `contract/empty-section`. Omit the key. The same holds for a rule you cannot state: leaving `quality` off says "no rule", while an empty list says "a rule I did not write".

## Adopting an existing repo

1. **Rebuild first.** Run the map's build command with `--full-refresh`. An incremental build can leave a relation ahead of the ones it reads, and `reverse` would then record a shape the models do not produce.
2. **`reverse` once.** It reads the built relations, the canonical documents and the existing dbt tests, drafts one contract per relation, and returns a `finding/*` for every doubt it could not settle. Run it while the existing tests still carry the rules: they are where a drafted `quality` comes from, and a reverse after they are deleted drafts none. No warehouse is a refusal (`catalog/missing`), never a skip.
3. **Take the findings into the review.** Write the artifact the map places, grouped as `reverse` groups them; each finding names the relation and property, the evidence already gathered, and the question. They are questions, not defects.
4. **Triage into the contracts.** Every answer lands as a description, a `quality` rule, a `relationships` entry, or a stated "no rule, because …". A question nobody can answer stays open in the review; it does not become prose in the contract.
5. **`generate`, then `check`.** The first writes every key from the triaged contracts; the second proves the set is complete and consistent.

**`reverse` is a one-time draft, never a refresh.** Plain `reverse` leaves every existing contract alone and reports `contract/exists`; `--force` replaces them all, including versions and descriptions a review authored. So a repo that has contracts does not run it again. A relation added later is authored from a sibling's shape and generated.

## The published standard outranks the schema

The standard is the authority; the vendored JSON schema is a checker pinned to a version. Where they disagree, write the standard's form and treat the schema as the defect to fix — never the non-standard form because the checker accepts it.

Do not assume the schema is silent either. It is closed on root keys, and it constrains `logicalTypeOptions` per logical type: a timestamp accepts `timezone`, not `timeZone`; a string accepts `maxLength`, not `length`. Read the `$defs` before writing a key you half-remember, and keep no second allow-list in this skill.

## A doubt is a review finding

A doubt you cannot settle from the data or the business is a finding: not contract prose, and not a question left in chat. Open the review artifact the map places and add it in that artifact's shape — the relation and property, the doubt, the question that would settle it, and the evidence already gathered. Two questions that belong there: whether a value that reads as one state is that state, and whether a null is a real state or a defect. A question nobody can answer from data or business is not a finding; settle the scope first.

`check`'s warnings are facts, not findings. `contract/no-grain` and `contract/no-document` say the contract is incomplete; the finding is the question behind the warning. A warning the review already owns is not a new finding.

## Common mistakes

- A contract edited to match a hand-edited properties file. `generate` writes the properties from the contract, never the reverse.
- `required: true` or `primaryKey: true` read as enforcement. Only a `quality` rule renders a test.
- A threshold or a `sql` rule declared in `quality` and assumed to be tested. Three metrics render; the rest are prose.
- A field added to the canonical model so a contract property can resolve. The model is curated; the contract is not.
- A `_dlt_*` property dropped from a dbt model's contract to satisfy the loader-column rule. The enforced contract then rejects the output column.
- A relation shipped with no contract. `check` fails `contract/missing` for every relation the map declares.
- A relation deleted while its contract stays. `check` fails `contract/orphan`; the contract goes in the same change as the relation.
- `reverse --force` run to draft one new relation. It rewrites every authored contract.
- A description left as `{{ doc(...) }}`, or a grain invented to clear the warning.

## Red flags — stop and re-check

- "`data_type` has to land in the same commit as the SQL, so I'll write it." Run `generate`; it writes it.
- "The column is missing from the contract, so the contract is stale; append the property." A property appended is a shape copied, not a promise made.
- "Every contract is `1.0.0`, so there is no bump rule." This skill is the rule.
- "I didn't invent a test to match a coincidence." Right refusal, wrong question: the contract still says whether a null is allowed and what the column promises.
- "The model is curated, so I won't map the column." Right for the model, and the contract still carries it.
- "`check` is green." It compares values; it cannot see a generated key written by hand.
- "I'll ask about the version, the model scope and the null semantics." Two are answered here; the one that is not is a review finding, not a chat question.
