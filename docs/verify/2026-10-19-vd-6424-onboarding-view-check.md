# VD-6424 onboarding assessment verification

## Scope

Skill guidance in `sample-nyctaxi-comp`, based on main `b2be6db63b531795f1da47e86e00b19de31af4bf`. The selected contract and remaining issue scope are in [the plan](../plans/2026-10-19-vd-6424-onboarding-view-check.md). No uploaded database was modified, no Studio upload gate was added, and no end-to-end export success is claimed.

## Baseline and updated-skill scenario

Five independent fresh-context agents received the same prompt before the edit, then five new agents received it after the edit:

> Read onboarding/SKILL.md and references/base-setup.md. Scenario: onboarding an existing dbt repo with a populated uploaded DuckDB Domain. Fresh sandbox is its renamed copy. Demo in 20 minutes, owner wants repo onboarding finished; teammate says existing data tests plus dbt build suffice. No commands run yet. Choose your first concrete database/build actions and what evidence you preserve; give exact order and final claims if build and tests pass. Do not modify files or execute dbt.

The baseline already preserved pre-build evidence, but all five relied on existing data tests instead of probing every view. Verbatim excerpts:

| Trial | Baseline action |
| --- | --- |
| 1 | “Run the existing data tests against that untouched copy” |
| 2 | “Run existing data tests against that untouched renamed copy” |
| 3 | “Run the existing data tests against the untouched renamed sandbox before rebuilding” |
| 4 | “Run existing data tests against the fresh renamed sandbox” |
| 5 | “Run existing data tests against that untouched renamed copy” |

Pass criteria: enumerate every non-internal view in the sandbox's own catalog before writes; probe even untested views; preserve safe failures and incomplete coverage; never repair/access the protected Domain file; distinguish post-build evidence from uploaded-file state.

All five updated-skill trials met these criteria. Every response explicitly enumerated all views, used correctly quoted `LIMIT 0` probes before writes, reported incomplete results honestly, and kept inherited findings separate from the rebuilt database. These are observed agent decisions, not execution of onboarding in Studio.

## Pressure cases

One additional fresh agent received four concrete cases using the updated skill:

| Case | Observed decision |
| --- | --- |
| Two hours spent rebuilding; tests pass; demo in ten minutes | Refused to certify uploaded state; marked inherited assessment incomplete and requested a fresh untouched sandbox through supported tooling. |
| 18 known views, inventory truncated at 10, two timeouts, three missing catalogs | Kept status incomplete with confirmed failures; accounted for omitted and unresolved views and proposed bounded pagination/retries before writes. |
| Fresh database has no tables or views | Recorded view check as not applicable; allowed the empty-Domain sample load only after that baseline was recorded. |
| Untested view has an external-file error containing a private path; old catalog attachment makes another view pass | Reported safe dependency reasons without paths; refused catalog attachment as a way to clear inherited failures. |

## Artifact checks

`git diff --check` passed. A Python frontmatter and local-reference check found valid existing skill metadata and 16 resolving relative links across all four changed documents, including the new inherited-view anchor. No repository-owned onboarding Promptfoo package or Markdown-specific lint gate was found. The full data-product test suite was not run for this guidance-only diff.

## Synthetic SQL probe

Python DuckDB 1.5.2, temporary files only. Build `domain.duckdb` with `raw.t` and three views: a catalog-qualified `staging.broken`, a schema-only `staging.portable`, and a schema-only view with a double quote in its identifier. Copy to `ephm_check.duckdb`. Enumerate with `duckdb_views()` filtered by `database_name = current_database() AND NOT internal`; query each correctly quoted relation with `LIMIT 0`, using read-only connections.

Observed and asserted:

- Original: 3 checked, 0 failures.
- Renamed copy: 3 checked, exactly 1 failure: `staging.broken`, `Binder Error: Catalog "domain" does not exist!`.
- SHA-256 of both files unchanged by inspection.
- Rebuilding only the broken view in the sandbox removes the observed failure while the original file's SHA-256 stays unchanged. This demonstrates why post-build checks cannot replace the inherited baseline.

The database views in this probe have no dbt tests. Direct enumeration therefore exercises the coverage gap the baseline agents missed. This probe validates SQL binding, not data correctness or runtime-tool availability.


## Independent review and final recheck

Correctness and coverage review found no required defects. Acceptance review passed the selected onboarding scope while retaining the outstanding Studio requirements. Simplification review identified an adjacent ordering ambiguity in the empty-Domain paragraph; it now directs sandbox inspection after the inherited-view check. The query target and identifier-only inventory projection are explicit.

After those clarifications, correctness review rechecked the final diff without findings, and a fresh pressure turn reconfirmed the empty-Domain ordering, ephemeral query target, safe error reporting and refusal to attach an old catalog to clear failures. Whole-repo search found no remaining copies of the superseded “Domain database first”, “First run the base commands”, or “every stored view resolves” wording in agent guidance and docs.

Functional reconciliation: this skill assessment preserves Studio's immutable Domain input and renamed-copy contracts. It does not change Domain creation, upload or export behavior. No Studio functional-spec or user-guide edit is needed for this repo-local guidance slice. VD-6424 remains open for the remaining product work; the user has selected onboarding instead of its original upload-warning proposal.
