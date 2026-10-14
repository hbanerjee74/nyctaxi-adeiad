# Base setup

What every onboarded repo has, so the first build intent does not spend its calls discovering the environment.

## Base commands

Put these in `repo-map.json` `commands`, using the repo's own paths: `dbt_deps`, `dbt_parse`, `dbt_build`, `python_tests`, `python_lint`, plus the run scripts if the repo has them.

In the design phase, before the inventory, run each once in the sandbox: dbt through the runtime wrapper with `--target dev`, after `dbt deps` when `packages.yml` exists. Record every result. A failure you cannot fix by adding a file from the list below is a review finding, `platform` or `bug`.

## Files onboarding adds

Onboarding changes no model, pipeline, existing config or human document. It adds these, and only when the repo has none:

| File | Content |
| --- | --- |
| `tests/test_maps.py` | Every map path exists; every source is registered; every `test-map.json` dbt selector resolves to a test. Its dbt calls name the repo's own profile (`--profiles-dir <dbt project> --profile <name>`) and run `dbt deps` once when `dbt_packages/` is missing, so they pass locally, in the sandbox and in CI. |
| `ruff.toml` | `[lint] select = ["E4", "E7", "E9", "F"]`, and `extend-exclude` with any paths the repo's documented lint command or CI already excludes (for example `--extend-exclude ingestion/sources`). Ruff's default selection changes between releases. Fix nothing it reports; file the findings as `style`. |
| `.gitignore` lines | `**/secrets.toml`, `.agents_tmp/`, `*.log`, `dbt_packages/`, `target/`, `ingestion/last-run-preview.md` (or the dlt preview path the repo uses). |

When the repo already has a ruff config, a different test layout or a `.gitignore` that conflicts, leave it and file the difference.

## Base rules

Write these into the rules whatever the repo's own conventions are; they come from how agents work in the sandbox, not from the code.

| Rule file | Rule |
| --- | --- |
| `dlt.md` | Sample loads (`DLT_INGEST_LIMIT`) while a pipeline is written; one full load at most per intent, at the end, only when the requirement asks for loaded data. |
| `dlt.md` | Profile a remote source file once per intent into `.agents_tmp/<source>-profile.json`, and take every later figure from it. |
| `dlt.md` | To see whether a source exists, read `repo-map.json` `sources`; query the lakehouse only for data questions. |
| `adr.md` | The three tests, then what is not an ADR: a choice one model or pipeline makes that is easy to change (load window, write disposition, cursor) goes in its design record. |
| `workarounds.md` | Each platform gap still open in the plugin, with what removes it: the sandbox dbt command (`vd-intent-context-run.sh "dbt <command> --target dev"`, do not open `profiles.yml`), `dbt_project_evaluator` only for model, test, macro, seed or `dbt_project.yml` changes, and `plan.md` and `verify.md` written once per phase. |

## Verify

The base commands pass, or each failure is a filed finding. `tests/test_maps.py` passes in the sandbox.
