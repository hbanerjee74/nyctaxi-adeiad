---
name: validating-data-contract
description: "Use when reviewing a data contract before commit or before a change that touches one merges, when asked whether a contract is complete or trustworthy, or when triaging the contract review queue — the six judgements the structural check cannot make."
---

# Validating a data contract

A contract can pass every structural check and still promise nothing, promise something false, or forbid a value the business sanctions. This skill reviews the promise: six questions, each one a script cannot answer, and for each the check that is blind to it.

Every location comes from `repo-map.json`: `artifact_paths.data_contract` places the contracts, `artifact_paths.logical_model` the documents they project, `artifact_paths.context` the business vocabulary, `artifact_paths.adr` the decisions, `artifact_paths.review` the queue, and each layer's `path` the root its relations build from. The tool is `odcs.py`, beside the authoring skill.

## Division of labour with `check`

`check` proves structure: schema validity, one contract per relation with no orphan, no present-but-empty section, agreement with the canonical document on the fields it declares, generated-key freshness, and — with `--relations` — agreement with the built relation. That list is settled before the review starts.

Never re-run `check` as the review, and never offer its output as evidence for one of the six. A green run is the entry condition: the file is well-formed and complete, not that it is true. Where a finding is about a value, the evidence is a read of the data or of a document, cited by file and line or by query and count.

`--relations` narrows that gap without closing it: it compares the declared columns with the built relation's schema, and reads no row. So it can prove a column is present and typed, and never that a grain holds, a null is absent or a rule passes — which is why items 1 to 3 gather data evidence of their own.

## Step 1 — read before you judge

For each contract in scope, in this order: the contract; the document the map places that declares the relation, where one does; the design record for the relation; the business vocabulary, because a description that uses a term the glossary does not hold is a finding even when it reads well; every ADR that a rule, a grain or a `required` decision touches; and the built relation's profile.

The profile is one pass per relation, over the whole relation and not a sample: rows, nulls and distinct values per column, and the repeat count of every combination a grain statement or a `primaryKey` claims. That single pass answers items 1, 2, 3 and 6's data half; reading the documents answers the rest. A contract that cannot be profiled — no warehouse, no catalog — is reported as unjudged, never as passing.

The scope is the contract the change touches, every contract that declares a key it declares (item 6 is the only item that reads across contracts), and every contract whose document or ADR the change amends. Reviewing only the edited file is how a divergence and a stale sibling both survive.

## Step 2 — the six

Each item names the evidence that settles it and the check that cannot see it. Where two items rest on the same evidence, gather it once and cite it twice.

A contract fails in two directions and these six cover both: it can say nothing — no grain, no prose, no rule — or it can say something false, a promise the data or an ADR contradicts. Absence is caught by counting what is not there; a false claim only by reading it against evidence. A review that does one and not the other passes the wrong half, and the second half is the one no check reaches.

1. **Is the grain true?** `dataGranularityDescription` must name what one row is, and the rows must be that. `check` proves a statement is present and is prose, never that it is the relation's grain: a sentence describing a row of a finer relation, or a blurb copied from the relation's description, passes. Test it against the data — does the combination it names repeat? — and against the relation's SQL.
2. **Is `required` honest against the data?** `required: true` renders no test, so nothing catches a false one: a column that is mostly null can declare a null impossible and ship. Require a profile showing no null, or an ADR forbidding one. `primaryKey` is the same kind of promise and gets the same evidence.
3. **Does each rule hold against the data, and does it contradict an ADR?** A rule with a stated count must find that count in the profile; a rule that passes because nothing can violate it — a filter no value reaches, a threshold beyond the domain — is vacuous. Then read the ADRs the rule touches: a rule that forbids a value an ADR sanctions is wrong even when every row currently satisfies it, because the sanction is the standing answer and the rule will break on the next row. `check` proves the rule is well-formed and rendered, not that it is true or sanctioned. A rule that encodes a narrower population than the ADR it cites — a filter the decision does not carry — is the same defect from the other side.
4. **Did the version move for the shape it changed?** Compare the contract with the version before it. A property removed or renamed, a type or grain changed, a rule withdrawn, or `required` newly refusing a value a consumer receives is breaking and takes a major move; an addition is minor; prose is patch. `check` validates the keys and the generated values, not what the version number means, so an unbumped breaking change is green.
5. **Does each description say something a consumer can act on, and is it true?** Prose is judged, not counted. A `{{ doc(...) }}` pointer, a sibling column's text copied over, and a sentence the column's values contradict are all failures. The number of undescribed consumer-facing properties is itself a finding: a contract carrying only a grain promises its reader nothing. `check` proves a description is non-empty; it cannot read it. A relation with no canonical document is not exempt — nothing else states what its columns mean, so its prose is the only promise it has, and this item is where such a contract gets read at all.
6. **Is the same key's `logicalType` the same across contracts?** `check` compares each contract with the document that declares that relation, and with nothing else, so one key typed `string` in one contract and `integer` in another passes twice. Read the key across every contract that declares it: a divergence is a finding against the document, not a preference between the two contracts, and settling it is a question for whoever owns the key's meaning.

## Step 3 — where a doubt goes

A doubt the data and the business cannot settle is a review finding, in the artifact `artifact_paths.review` places, in that artifact's shape: the relation and property, the evidence already gathered, and the question that would settle it. The question is answerable from the data or from a business owner; a question that needs a scope decision first is not a finding yet.

`check`'s warnings are facts, not findings. The finding is the question behind one, and a warning the queue already owns is not a second row.

Where no queue exists yet, the map's pattern names the file the review creates; a doubt with no home is written there rather than left in a report nobody triages.

A finding the review settles lands in the contract — a description, a rule, a relationship, a stated reason there is none — in the change that settles it, and its row is closed rather than deleted. One nobody can settle yet stays open with its evidence, because a queue that quietly shrinks is indistinguishable from a queue that was answered. A finding is a question for triage, not a defect the reviewer patches: a defect goes to the authoring skill, which owns what the contract may say.

## Step 4 — report

Give the verdict, then each finding as location → evidence → the check that cannot see it → the question. Name the items you could not judge and why. A pass needs a cited file, query or ADR for every one of the six; the review is over when all six carry evidence, not when `check` is green.

Close with which items rested on profiled data, which on documents alone, and which contracts you read beside the changed one — a reader who cannot tell how far the evidence reached cannot tell what a pass covers. Carry each `check` warning into the report by its code so triage can match it to the row that answers it, and state an item still open as open rather than folding it into the verdict.

A fix to a contract goes back through the authoring skill — `generate`, then `check` — because an edit is an edit and the review that approved the old file no longer describes this one.

## Maintenance note

This is a reference, not a discipline skill: the authoring skill, the ADRs and the design records already lead a competent reviewer to all six, so its job is coverage and attribution — every reviewer answers all six every time, and can say which check is blind to each — not a counter to a rationalisation anyone exhibited. Grow it only with an item no script can decide, and only once a review has missed it despite being asked.
