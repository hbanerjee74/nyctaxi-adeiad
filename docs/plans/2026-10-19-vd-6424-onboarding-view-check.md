# VD-6424 onboarding view check

## Scope and contract

The user selected onboarding, rather than upload validation, to detect inherited DuckDB view failures. Assess the untouched sandbox before any database write, enumerate every user-defined view (including views without dbt tests), preserve safe findings, and distinguish that assessment from post-build portability. Never repair the uploaded Domain database or claim a sandbox rebuild repairs it.

This is a partial implementation of VD-6424. Export diagnostics, upload/UI changes and existing-Domain product surfaces are outside this change. Studio functional references are `docs/functional/domain/README.md` and `docs/functional/data-platform/duckdb-local-backend.md` (immutable Domain input; renamed sandbox copies preserve views). Related design: `docs/design/domain/bundle-export.md` (third-catalog replay failures remain fatal). Those paths are in `accelerate-data/studio`; this change preserves their runtime contracts and introduces no Studio UI change.

## Files and sequence

- [x] Read the issue, domain flow label, functional contracts, related export design, existing onboarding skill and its base setup.
- [x] Create isolated issue worktrees. The implementation belongs to `sample-nyctaxi-comp`; the Studio worktree supplies issue/spec context only.
- [x] Run five fresh-agent controls against the existing skill. Score pre-build coverage of every view, not just dbt-test coverage.
- [x] Modify `.agents/skills/onboarding/SKILL.md` to route the Design phase through the assessment before builds.
- [x] Modify `references/base-setup.md` with the read-only assessment, incomplete-result semantics and reporting; preserve post-build checks separately.
- [x] Verify the SQL approach on synthetic DuckDB files, including a view without a test, portable references, quoted identifiers and unchanged file hashes.
- [x] Run five fresh-agent trials on the updated skill and additional pressure cases: already rebuilt, truncated inventory/timeouts, empty database and sensitive dependency errors.
- [x] Check diff whitespace, frontmatter and local links; run independent correctness, simplification, coverage and scoped acceptance reviews.
- [x] Record verification, update Linear with partial scope and remaining ACs, and commit locally. Do not push or create a PR.

## Authoring checks

- [x] Baseline scenarios and verbatim failures recorded before editing; guidance addresses uncovered views rather than assuming test coverage.
- [x] Existing workspace-local skill name, frontmatter and trigger description preserved; no additional skill created.
- [x] Procedure stays in the existing reference with one entry-point link; no redundant helper or new dependency.
- [x] Fresh structure/link checks and final prose audit.
- [x] Review findings resolved and affected scenarios rerun if behavior changes.
- [x] Apply `closing-authoring-work` verification; use the explicitly requested implementation-only boundary instead of its publish step.

No onboarding Promptfoo package or Markdown-specific gate was found in this repository. Fresh subagent scenarios and the synthetic binding probe provide the changed-area evidence; they do not constitute an end-to-end Studio onboarding or export run.
