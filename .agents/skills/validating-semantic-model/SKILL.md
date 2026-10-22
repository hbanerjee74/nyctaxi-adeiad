---
name: validating-semantic-model
description: "Use when checking a canonical semantic model before commit, after a mart change, or when asked to validate it or whether a metric is trustworthy — covering both the structural tool run and the content review that decides whether the model is honest."
---

# Validating a semantic model

Two passes, and the change is not done until both have evidence. The tool proves the document is well-formed; it cannot judge meaning. A green structural run says the file parses — not that a metric computes what it claims.

The scripts live beside the authoring skill: `../semantic-model/scripts/ossie.py`. Tool behaviour — what each check reads, and what it cannot see — is in `references/checks.md`.

## Step 1 — structure

From the repo root, run `python3 .agents/skills/semantic-model/scripts/ossie.py validate <model-dir>` and require exit 0 with zero errors. Then `ossie.py coverage <model-dir> <marts-dir>` and require `0 coverage error(s)`. Record each command with its exit code.

An error means the document is malformed; fix it and re-run before going further. Nothing in step 2 compensates for a document that does not parse.

## Step 2 — content

Work from the mart SQL, never from the model's own prose. Every item's evidence is a file you read and the line that settles it.

1. **Every declared field resolves.** Each field's `column_map` right side must be a column its mart's `SELECT` produces; for a `table_type: ALIAS` handle, check the table it is an alias of. A field with no `column_map` entry in any source is unsupplied — a finding.
2. **Every aggregate metric binding is honest.** The agg column must compute the same aggregation over the same population as the metric: a filtered metric bound to an unfiltered column fails, and so does any table whose rows are a subset of the metric's population. Record the confirming sentence in that source's `note` and in your report — a binding whose note does not carry it is itself a finding.
3. **Rates are rebuilt, never averaged.** A rate or ratio metric may come from an aggregate only when the aggregate computes it from summed numerator and denominator at its own grain. A precomputed rate column that a consumer would sum is wrong.
4. **Population matches the bound metric, not the table's name.** A star-population rollup is an aggregate source even when it carries the report window or a billable filter, because the metric it supplies has the same population. It is standalone for any metric whose population is wider — a truncation, a row-dropping join, a different denominator.
5. **Semi-additive measures are not plain sums.** Down-days, balances, snapshots, stock levels: no `SUM` metric, and no aggregate whose grain crosses the forbidden dimension.
6. **Refusals are recorded.** Every declared field or metric an aggregate declines to supply, and every table that cannot be mapped, carries a `note` naming why. Refusing an undeclared physical column needs no note.
7. **Coverage is complete.** `coverage` proves the model set; the notes prove the gaps. A gold table with neither a handle nor a note is a finding.
8. **Consumer parity.** When a dbt semantic layer exists, compare metric names and expressions against it. A divergence is a finding, not a curiosity.

## Step 3 — report

Give the verdict, then each finding as location → evidence → fix, then the checks you could not run and why (no warehouse, no dbt, no catalog). A verdict of "passes" needs a cited file per claim.

## Red flags — stop and re-check

- "The tool says green." It says the file parses. Step 2 is unstarted.
- "The note says it was checked." Read the SQL; a note is a claim, not evidence.
- "No warehouse, so I'll assume the keys are unique." Report the unknown as unknown; never convert it into a pass.
- "One mapping looked odd but validate passed." That is a finding.
- "The model documents its own intent, so it is consistent." Read the mart and the ADR; a model can be green and wrong.
