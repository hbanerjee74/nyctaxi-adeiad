---
name: validating-data-contract
description: "Use when reviewing a data contract before commit or before a change that touches one merges, when asked whether a contract is complete or trustworthy, or when triaging the contract review queue — the judgements the structural check cannot make."
---

# Validating a data contract

A contract can pass every structural check and still promise nothing, promise something false, or forbid a value the business sanctions. This skill reviews the promise: seven questions a reviewer answers and attributes, each pairing a mechanical read with a judgement no script settles.

Every location comes from `repo-map.json`: `artifact_paths.data_contract` places the contracts, `artifact_paths.logical_model` the documents they project, `artifact_paths.context` the business vocabulary, `artifact_paths.adr` the decisions, `artifact_paths.review` the queue, and each layer's `path` the root its relations build from. The tool is `odcs.py`, beside the authoring skill.

## Division of labour with `check`

`check` proves structure: schema validity, one contract per relation with no orphan, no empty `servers`, `authoritativeDefinitions` or `tags` and no empty relation-level `quality`, agreement with the canonical document on the fields it declares — and no relation left without one where its layer requires a document — and generated-key freshness. A property-level `quality: []` passes both the schema and `check`; it is the author's own omission to avoid, not something a green run catches. That list is settled before the review starts.

It proves nothing about a landed table. `check --relations` compares a contract with the relation the catalog holds — a column the contract dropped, a column it declares and the relation lacks, and a relation absent altogether — reading the warehouse the platform sets and refusing rather than skipping when there is none; that comparison is the review's, in Step 1, and until the check exists it is the only place a column the relation lost or gained shows up.

Never re-run `check` as the review, and never offer its output as evidence for one of the questions. A green run is the entry condition: the file is well-formed and its sections consistent, not that its promises are true or complete — a contract with no grain at all still exits 0. Where a finding is about a value, the evidence is a read of the data or of a document, cited by file and line or by query and count.

## Step 1 — read before you judge

For each contract in scope, in this order: the contract; the document the map places that declares the relation, where one does; the review queue, whose open rows are doubts already asked; the design record for the relation; the business vocabulary, because a description that uses a term the glossary does not hold is a finding even when it reads well; every ADR that a rule, a grain or a `required` decision touches; and the built relation's profile.

The queue is not background reading. Its open rows include the two doubts a contract cannot show by inspection: a property that holds nulls with no rule saying whether it may, and a property whose name reads as a reference with no target declared. Each is answered from the data or from the business, never by re-reading the contract; a row already open is not a second finding, and a row nobody can answer stays open with its evidence.

The profile is one pass per relation, over the whole relation and not a sample: rows, nulls and distinct values per column, the repeat count of every combination a grain statement or a `primaryKey` claims, and the columns and types the relation actually has, reconciled against the contract. That pass answers the data half of items 1, 2, 3 and 6; reading the documents answers the rest. A contract that cannot be profiled — no warehouse, no catalog — is reported as unjudged, never as passing.

The scope is the contract the change touches, every contract that declares a key it declares (item 6 is the only item that reads across contracts), and every contract whose document or ADR the change amends. Reviewing only the edited file is how a divergence and a stale sibling both survive.

## Step 2 — the checklist

Each item names its mechanical half and the judgement that follows it. Where two items rest on the same evidence, gather it once and cite it twice.

A contract fails in two directions and the checklist covers both: it can say nothing — no grain, no prose, no rule — or it can say something false, a promise the data or an ADR contradicts. Absence is caught by counting what is not there; a false claim only by reading it against evidence. A review that does one and not the other passes the wrong half.

1. **Is the grain true?** `dataGranularityDescription` must name what one row is, and the rows must be that. Absence is a warning (`contract/no-grain`) that still exits 0, and a `{{ }}` pointer draws that same warning as no grain at all — so a green run includes grainless contracts and says nothing about this sentence either way. Neither tells you it is this relation's grain: a sentence describing a row of a finer relation, or a blurb copied from the relation's description, passes. Test it against the data — does the combination it names repeat? — and against the relation's SQL.
2. **Is `required` honest against the data?** On a model's contract `required: true` renders no test, so nothing catches a false one: a column that is mostly null can declare a null impossible and ship. Require a profile showing no null, or an ADR forbidding one. `primaryKey` is the same kind of promise and gets the same evidence.
3. **Does each rule hold against the data, and does it contradict an ADR?** A rule with a stated count must find that count in the profile; a rule that passes because nothing can violate it — a filter no value reaches, a threshold beyond the domain — is vacuous. Then read the ADRs the rule touches: a rule that forbids a value an ADR sanctions is wrong even when every row currently satisfies it, because the sanction is the standing answer and the rule will break on the next row. A rule that encodes a narrower population than the ADR it cites — a filter the decision does not carry — is the same defect from the other side. What the check proves is only that a rendered test matches its rule: three library metrics with `mustBe: 0` render one, every other rule renders none, and an unenforced rule is as green as a satisfied one.
4. **Did the version move for the shape it changed?** Compare the contract with the version before it. A property removed or renamed, a type or grain changed, a rule withdrawn, or `required` newly refusing a value a consumer receives is breaking and takes a major move; an addition is minor; prose is patch. `check` validates the keys and the generated values, not what the version number means, so an unbumped breaking change is green.
5. **Does each description say something a consumer can act on, and is it true?** Prose is judged, not counted. A `{{ doc(...) }}` pointer, a sibling column's text copied over, and a sentence the column's values contradict are all failures. The number of undescribed consumer-facing properties is itself a finding: a contract carrying only a grain promises its reader nothing. `check` proves a description is non-empty; it cannot read it. A relation with no canonical document is not exempt — nothing else states what its columns mean, so its prose is the only promise it has, and this item is where such a contract gets read at all.
6. **Is the same key's `logicalType` the same across contracts?** The scan is mechanical: read the property out of every contract that declares it. The judgement is not. `check` compares each contract with the document that declares that relation and with nothing else, so one key typed `string` in one contract and `integer` in another passes twice. A divergence is a finding against the document rather than a preference between the two contracts, and which type is right is a question for whoever owns the key's meaning.
7. **Does a contract mean what its document means?** `check` proves every declared field is present and each `logicalType`, `primaryKey` and timezone option agrees, so a contract can resolve field by field and still describe a different relation. Take the document's own statements — the relation's purpose, its grain, what a field holds — and read the contract's prose against them. Agreement on every field and a different story in the sentences is the failure this item exists for.

## Step 3 — where a doubt goes

A doubt the data and the business cannot settle is a review finding, in the artifact `artifact_paths.review` places, in that artifact's shape: the relation and property, the evidence already gathered, and the question that would settle it. The question is answerable from the data or from a business owner; a question that needs a scope decision first is not a finding yet.

`reverse`'s `finding/*` warnings are already questions: the queue row is where each is answered, and one class raised twice is one row. `check`'s warnings are facts — absence, or a shape nothing proves — and the finding is the question behind one. Neither is a new finding on its own, and a warning the queue already owns is not a second row.

Where no queue exists yet, the map's pattern names the file the review creates; a doubt with no home is written there rather than left in a report nobody triages.

A finding the review settles lands in the contract — a description, a rule, a relationship, a stated reason there is none — in the change that settles it, and its row is closed rather than deleted. One nobody can settle yet stays open with its evidence, because a queue that quietly shrinks is indistinguishable from a queue that was answered. A finding is a question for triage, not a defect the reviewer patches: a defect goes to the authoring skill, which owns what the contract may say.

## Step 4 — report

Give the verdict, then each finding as location → evidence → the check that cannot see it → the question. Name the items you could not judge and why. A pass needs a cited file, query or ADR for every item; the review is over when every item carries evidence, not when `check` is green.

Close with which items rested on profiled data, which on documents alone, and which contracts you read beside the changed one — a reader who cannot tell how far the evidence reached cannot tell what a pass covers. Carry each `check` warning into the report by its code so triage can match it to the row that answers it, and state an item still open as open rather than folding it into the verdict.

A fix to a contract goes back through the authoring skill — `generate`, then `check` — because an edit is an edit and the review that approved the old file no longer describes this one.

## Maintenance note

This is a reference, not a discipline skill: the authoring skill, the ADRs and the design records already lead a competent reviewer to these items, so its job is coverage and attribution — every reviewer answers every item each time, and can say which check is blind to each — not a counter to a rationalisation anyone exhibited. Grow it only with a judgement no script can decide, and only once a review has missed it despite being asked.
