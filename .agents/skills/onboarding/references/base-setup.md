# Base setup

What every onboarded repo has, so the first build intent does not spend its calls discovering the environment. It comes from how agents, the sandbox and the CI bundle work, not from the repo's code.

## Base commands

Put these in `repo-map.json` `commands`, using the repo's own paths: `dbt_deps`, `dbt_parse`, `dbt_build`, `python_tests`, `python_lint`, plus the run scripts if the repo has them.

In the design phase, before the inventory, run each once in the sandbox: dbt through the runtime wrapper with `--target dev`, after `dbt deps` when `packages.yml` exists. Record every result. A failure you cannot fix with a change from the two lists below is a review finding, `platform` or `bug`.

## Changes the build needs

The only edits to existing files. List each in the PR description.

| File | Change | Why |
| --- | --- | --- |
| `dbt_project.yml` | `profile: "{{ env_var('DBT_PROFILE_NAME', '<current name>') }}"` | The sandbox wrapper selects its profile through `DBT_PROFILE_NAME`; a fixed name means no dbt command runs in the sandbox. Local and CI runs keep the current name. |
| `dbt_project.yml` | Under `models:` and `seeds:`, `dbt_project_evaluator: +enabled: "{{ var('dbt_project_evaluator_enabled', false) }}"` | Keeps the evaluator out of normal builds; the CI quality workflow and `verifying` switch it on. Only with the `packages.yml` entry below. |

## Files onboarding adds

Only when the repo has none. When the repo has its own that conflicts, leave it and file the difference.

| File | Content |
| --- | --- |
| `packages.yml` entry | `dbt-labs/dbt_project_evaluator`, `version: [">=1.1.0", "<2.0.0"]`, added to an existing `packages.yml` or a new one. The CI quality workflow builds it. |
| `tests/test_maps.py` | Every map path exists; every source is registered; every `test-map.json` dbt selector resolves to a test. Its dbt calls name the repo's own profile (`--profiles-dir <dbt project> --profile <name>`) and run `dbt deps` once when `dbt_packages/` is missing, so they pass locally, in the sandbox and in CI. |
| `ruff.toml` | `[lint] select = ["E4", "E7", "E9", "F"]`, and `extend-exclude` with any paths the repo's documented lint command or CI already excludes (for example `--extend-exclude ingestion/sources`). Ruff's default selection changes between releases. Fix nothing it reports; file the findings as `style`. |
| `.gitignore` lines | Appended to the existing `.gitignore` (or a new one), only the lines missing: `**/secrets.toml`, `.agents_tmp/`, `*.log`, `dbt_packages/`, `target/`, `ingestion/last-run-preview.md` (or the dlt preview path the repo uses). |

## Rules

Copy these from [templates/rules/](../templates/rules/) as they are; only examples may change to the repo's own. When the repo's confirmed inventory says otherwise (its own commit format, for example), the inventory wins for that line.

| Rule file | What it holds |
| --- | --- |
| `context.md` | What goes in `CONTEXT.md` and what does not. |
| `design-records.md` | What goes in a design record: decisions with sources, consumers from lineage, evidence. |
| `adr.md` | The three tests, what is not an ADR, content, supersession. |
| `git-and-prs.md` | Commit format, staging named files (never `git add .`), the four PR-body sections the `shipping` skill fills. |
| `workarounds.md` | The open platform gaps, each with what removes it: the sandbox dbt command, the evaluator only for model changes, `plan.md` and `verify.md` written once per phase. |

Write these into the repo's own rule files beside its conventions:

| Rule file | Rule |
| --- | --- |
| `dlt.md` | Sample loads (`DLT_INGEST_LIMIT`) while a pipeline is written; one full load at most per intent, at the end, only when the requirement asks for loaded data. |
| `dlt.md` | Profile a remote source file once per intent into `.agents_tmp/<source>-profile.json`, and take every later figure from it. |
| `dlt.md` | To see whether a source exists, read `repo-map.json` `sources`; query the lakehouse only for data questions. |
| `dbt-models.md` | dlt lands naive Arrow timestamps as `TIMESTAMPTZ` and the sandbox session is not UTC: staging converts every dlt-loaded timestamp with `timezone('UTC', col)`. |
| `dbt-testing.md` | A left join on a derived key gets a singular test that every left row finds its match, or that the unmatched rows are the expected ones. |

## Agent entry points

- `AGENTS.md` starts with a Startup section: before a task, read `repo-map.json` and the rule file for the task (`dlt.md` to add a source, `dbt-models.md` for a model); do not read README, CONTRIBUTING or other human documents for a pipeline or model change.
- `repo-map.json` `notes_for_agents` has at least: `startup`; `new_source` (a new source mirrors an existing `sources` entry and creates every artifact it lists); `reviews_and_proposals`; and, when pipelines use the Vibedata dlt package, the environment variables they need outside Studio.

## Checks for the onboarding review

File each as a finding when it fails; change nothing.

| Check | Kind when it fails |
| --- | --- |
| Parquet or Arrow sources stamp `_dlt_load_id` and `_dlt_id` (`[normalize.parquet_normalizer] add_dlt_load_id`, `add_dlt_id`) | `platform` |
| Staging reads bronze only through `source()` | `platform` |
| Staging converts dlt-loaded timestamps to UTC | `bug` if a key or join depends on them, else `convention` |
| Run scripts install dbt packages before building | `bug` |
| A CI job runs the pytest suite | `gap` |
| `.sqlfluff` (or the SQL lint config) resolves its profile and project paths | `gap` |

## Verify

The base commands pass, or each failure is a filed finding. `tests/test_maps.py` passes in the sandbox.
