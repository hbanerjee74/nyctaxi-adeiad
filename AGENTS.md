# NYC Taxi Analytics (nyc-taxi-duckdb-demo): Agent Conventions

A DuckDB lakehouse for NYC taxi analytics: real TLC trip records, plus two simulated source systems (fleet operations and master data). Read [`CONTEXT.md`](CONTEXT.md) for the vocabulary.

Read [`repo-map.json`](repo-map.json) first. It says where everything is: layers, entrypoints, commands and artifact locations. This file says how to work.

## Startup

Before a task, read `repo-map.json` and the rule file for the task. To add a source, read [`dlt.md`](.agents/rules/dlt.md); for a model, [`dbt-models.md`](.agents/rules/dbt-models.md). Read other documents only when the task needs them: not `README.md` or `CONTRIBUTING.md` for a pipeline or model change, and never `docs/setup/`, which is repo maintenance. Read `repo-map.json` whole, once, at the start of a task: its `modules`, `artifact_paths` and `sources` are the index of the repo, so do not list directories (`find`, `ls -R`) or read it again in parts. List one folder only when the repo-map names it and the task needs what is in it.

After the conversation is condensed, re-read `.agents/rules/workarounds.md` before the next tool call: its rules are easy to lose in a summary.

## Medallion layers

- **Bronze**: raw data loaded by dlt (`ingestion/`) into `bronze` (TLC), `ops_raw` and `mdm_raw`.
- **Silver**: dbt staging and intermediate models in `transformation/`.
- **Gold**: dbt marts in `core`, `agg`, `finance` and `ops`.

Layer, schema and builder for each are in `repo-map.json` under `layers`.

## Rules

Operator conventions live in `.agents/rules/`. Read the ones that match your task.

| Rule | Covers |
| --- | --- |
| [`dbt-models.md`](.agents/rules/dbt-models.md) | Layer mapping, model naming, properties files, materialisation |
| [`sql-style.md`](.agents/rules/sql-style.md) | SQL formatting |
| [`dbt-testing.md`](.agents/rules/dbt-testing.md) | Generic, singular, unit and Python tests |
| [`dlt.md`](.agents/rules/dlt.md) | Datasets, write disposition, schema contract, bronze carries no logic |
| [`context.md`](.agents/rules/context.md) | What goes into `CONTEXT.md` |
| [`adr.md`](.agents/rules/adr.md) | What goes into an ADR, and when |
| [`workarounds.md`](.agents/rules/workarounds.md) | Temporary rules for platform gaps: single edits of `plan.md` and `verify.md`, running dbt in the sandbox, the evaluator only for transformation changes, large files changed by script, ruff for lint, verify from the landed table, the Tier-1 dev dataset, one run per gate, dbt packages for the ship-time contract check. Each names what removes it |
| [`design-records.md`](.agents/rules/design-records.md) | What goes into a design record |
| [`git-and-prs.md`](.agents/rules/git-and-prs.md) | Commit and pull request format |

## Decisions and designs

- Decisions are ADRs in `docs/adr/`. Standing business answers (week boundary, null handling) are ADRs too: check them before asking a requirement question.
- Each model and pipeline has a design record under `docs/design/`. A design record cites its ADRs as `ADR NNNN`, and an ADR lists the designs it affects.
- Each intent's Requirement, Plan and Verification live where `repo-map.json` `artifact_paths` says (`requirement`, `plan`, `verification`); the plugin names each one for its intent.
- Review findings for triage are in `docs/review/`; do not read them for a build task. Read a proposal in `docs/proposal/` only when the intent's requirement links to it.

## Commands

```bash
python3 orchestration/run_all.py          # ingestion, then dbt build
python3 orchestration/run_ingest.py       # dlt pipelines: tlc, ops, mdm
python3 orchestration/run_transform.py    # dbt build
python3 -m pytest tests -q                # Python tests
```

The command for each layer's tests is in `test-map.json`. See `CONTRIBUTING.md` for the workflow before a push.

## Safety

- The warehouse is `domain.duckdb` at the repo root. It is ignored by git and rebuilt by `orchestration/run_all.py`. Never commit it or downloaded data.
- Never commit secrets. dlt reads them from the bound secret store.
- Do not edit `transformation/profiles.yml` to make a failure pass.

## Maintenance rules

Keep these current in the same change that makes them stale.

| Artifact | Update when | Guard |
| --- | --- | --- |
| `repo-map.json` | A layer, source, pipeline, entrypoint, command or artifact location is added, renamed or removed | `tests/test_maps.py` fails on a missing path, config section or source file |
| `test-map.json` | A layer appears in the repo-map, or a new test starts protecting a layer | `tests/test_maps.py` fails when a layer has no module or a selector selects nothing |
| `CONTEXT.md` | A term appears in, or changes meaning in, a model, ADR or design record. Use `domain-modeling`; do not edit freehand. Typo and link edits are exempt | none |
| `.agents/rules/` | A convention changes | none |
| `AGENTS.md` | A durable fact the code does not show: an environment constraint or a workflow gotcha | none |

