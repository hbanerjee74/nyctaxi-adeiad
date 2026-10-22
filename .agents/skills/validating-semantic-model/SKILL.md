---
name: validating-semantic-model
description: "Use when checking a canonical semantic model before commit, after a mart change, or when asked to validate it or whether a metric is trustworthy — covering both the structural tool run and the content review that decides whether the model is honest."
---

# Validating a semantic model

Two passes, and the change is not done until both have evidence. The tool proves the document is well-formed; it cannot judge meaning. A green structural run says the file parses — not that a metric computes what it claims.

The scripts live beside the authoring skill: `../semantic-model/scripts/ossie.py`. Tool behaviour — what each check reads, and what it cannot see — is in `references/checks.md`.

## Step 1 — structure

From the repo root, run `python3 .agents/skills/semantic-model/scripts/ossie.py validate <model-dir>` and require exit 0 with zero errors. Then `ossie.py coverage <model-dir> <marts-dir>` and require `0 coverage error(s)`, `ossie.py suppliers <model-dir>` and require an empty list — it is the instrument behind review item 1 — and `ossie.py notes <model-dir> <tests-dir> <adr-dir>` and require none dangling, which is what keeps a note's promises true after a test or ADR is renamed. Record each command with its exit code.

An error means the document is malformed; fix it and re-run before going further. Nothing in step 2 compensates for a document that does not parse.

## Step 2 — content

Work from the mart SQL, never from the model's own prose. Every item's evidence is a file you read and the line that settles it.

1. **Every declared field resolves.** Each field's `column_map` right side must be a column its mart's `SELECT` produces; for a `table_type: ALIAS` handle, check the table it is an alias of. A field with no `column_map` entry in any source is unsupplied — a finding.
2. **Every aggregate metric binding is honest.** The agg column must compute the same aggregation over the same population as the metric: a filtered metric bound to an unfiltered column fails, and so does any table whose rows are a subset of the metric's population. Record the confirming sentence in that source's `note` and in your report — a binding whose note does not carry it is itself a finding.
3. **Rates are rebuilt, never averaged.** A rate or ratio metric is a `derived_expression` over its numerator and denominator metrics and binds to no column; `validate` fails a binding (`derived-metric-mapped`). Check the formula against the ADR that defines the rate.
4. **Population matches the bound metric, not the table's name.** A star-population rollup is an aggregate source even when it carries the report window or a billable filter, because the metric it supplies has the same population. It is standalone for any metric whose population is wider — a truncation, a row-dropping join, a different denominator.
4a. **Content is the SQL, not a guess.** Each aggregate's `content_filter` restates its `WHERE` plus every row its inner joins drop, and its `content_levels` match its `GROUP BY` level by level, with the role (`via`) the join actually uses. Run the holding test against a built warehouse, or report it as unrun. A level keyed on a column that repeats across members (a month number, a zone name) is a finding: query the dimension for duplicates.
5. **Semi-additive measures are not plain sums.** Down-days, balances, snapshots, stock levels: no `SUM` metric, and no aggregate whose grain crosses the forbidden dimension.
6. **Refusals are recorded.** Every declared field or metric an aggregate declines to supply, and every table that cannot be mapped, carries a `note` naming why. Refusing an undeclared physical column needs no note.
7. **Coverage is complete.** `coverage` proves the model set; the notes prove the gaps. A gold table with neither a handle nor a note is a finding.
8. **Datatypes and SCD are honest.** Each field's `datatype` matches the column the staging or ingestion SQL produces, and each `scd` claim matches the ADR that rules it — a Type 2 claim on a Type 1 source is a finding.
9. **Documents hold whole stars.** A dataset that exists only to bridge two documents is a partition error, not a table.
10. **Consumer parity.** When a dbt semantic layer exists, compare metric names and expressions against it. A divergence is a finding, not a curiosity.

## Step 3 — fix, or escalate

You fix what the model can settle without a business decision, and re-run `validate` and `suppliers` afterwards. That is: a missing confirming sentence, a wrong `datatype` traceable to the staging or ingestion SQL, an unsupplied metric whose column is obvious, a dangling reference, a note that contradicts the SQL.

You escalate as a grilling session — one finding at a time, location → evidence → options → recommendation, waiting for the ruling before raising the next — when the fix changes what the number means: withdrawing a mapping, reclassifying a table as standalone, deciding a truncated or row-dropping source is acceptable, or resolving a contradiction between the model and an ADR. Those are S9 questions in the authoring skill, not validation calls.

Never edit mart SQL, a seed or a macro to satisfy the model. If the mart is wrong, it is a finding about the mart, reported — the model records what the lakehouse actually does.

## Step 4 — report

Give the verdict, then each finding as location → evidence → fix, then the checks you could not run and why (no warehouse, no dbt, no catalog). A verdict of "passes" needs a cited file per claim, and every content fix is followed by re-running `validate` and `suppliers` — a content edit is an edit.

## Red flags — stop and re-check

- "The tool says green." It says the file parses. Step 2 is unstarted.
- "The note says it was checked." Read the SQL; a note is a claim, not evidence.
- "No warehouse, so I'll assume the keys are unique." Report the unknown as unknown; never convert it into a pass.
- "One mapping looked odd but validate passed." That is a finding.
- "The model documents its own intent, so it is consistent." Read the mart and the ADR; a model can be green and wrong.
- "I fixed it while reviewing, so the review is done." Re-run both gates after any fix, or the verdict describes a file that no longer exists.
