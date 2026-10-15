# <Domain name>: Agent Conventions
<!-- onboarding
ask: yes
question: What is this domain for, and where does its data come from?
recommended: One paragraph naming the business area, the source systems and who uses the outputs, in plain words.
alternatives: none; a domain must say what it is.
fills: <Domain name>, <domain paragraph>
-->

<domain paragraph> Read [`CONTEXT.md`](CONTEXT.md) for the vocabulary.

Read [`repo-map.json`](repo-map.json) first. It says where everything is: layers, entrypoints, commands and artifact locations. This file says how to work.

## Startup
<!-- onboarding
ask: no
reason: How agents read this repo; the same for every domain.
-->

Before a task, read `repo-map.json` and the rule file for the task. To add a source, read [`dlt.md`](.agents/rules/dlt.md); for a model, [`dbt-models.md`](.agents/rules/dbt-models.md). Read other documents only when the task needs them: not `README.md` or `CONTRIBUTING.md` for a pipeline or model change. Read `repo-map.json` whole, once, at the start of a task: its `modules`, `artifact_paths` and `sources` are the index of the repo, so do not list directories (`find`, `ls -R`) or read it again in parts.

After the conversation is condensed, re-read `.agents/rules/workarounds.md` before the next tool call: its rules are easy to lose in a summary.

## Medallion layers
<!-- onboarding
ask: yes
question: Which raw schemas and dbt layers does this domain have?
recommended: One raw schema per source system, named after it; staging → intermediate → marts split by area, starting with core.
alternatives: one raw schema for every source; marts not split by area.
fills: <raw schemas>, <mart areas>
-->

- **Bronze**: raw data loaded by dlt (`ingestion/`) into <raw schemas>.
- **Silver**: dbt staging and intermediate models in `transformation/`.
- **Gold**: dbt marts in <mart areas>.

Layer, schema and builder for each are in `repo-map.json` under `layers`.

## Rules
<!-- onboarding
ask: no
reason: One row per rule file written; follows from the rules.
-->

Operator conventions live in `.agents/rules/`. Read the ones that match your task.

| Rule | Covers |
| --- | --- |
| [`dbt-models.md`](.agents/rules/dbt-models.md) | Layer mapping, model naming, properties files, materialisation |
| [`sql-style.md`](.agents/rules/sql-style.md) | SQL formatting |
| [`dbt-testing.md`](.agents/rules/dbt-testing.md) | Generic, singular, unit and Python tests |
| [`dlt.md`](.agents/rules/dlt.md) | Datasets, write disposition, schema contract, bronze carries no logic |
| [`context.md`](.agents/rules/context.md) | What goes into `CONTEXT.md` |
| [`adr.md`](.agents/rules/adr.md) | What goes into an ADR, and when |
| [`design-records.md`](.agents/rules/design-records.md) | What goes into a design record |
| [`git-and-prs.md`](.agents/rules/git-and-prs.md) | Commit and pull request format |
| [`workarounds.md`](.agents/rules/workarounds.md) | Temporary rules for platform gaps. Each names what removes it |

## Decisions and designs
<!-- onboarding
ask: yes
question: Where do design records go?
recommended: Layered, `docs/design/models/<layer>/<model>.md`; ADRs, requirements, plans and certifications at the plugin's default paths.
alternatives: flat `docs/design/models/<model>.md`.
fills: the design-record wording here, and repo-map.json artifact_paths.design_record_model
-->

- Decisions are ADRs in `docs/adr/`. Standing business answers are ADRs too: check them before asking a requirement question.
- Each model and pipeline with a decision its code does not explain has a design record under `docs/design/` (models layered by folder). A design record cites its ADRs as `ADR NNNN`, and an ADR lists the designs it affects.
- Requirements, plans and certifications follow the plugin's artifact-path convention: `docs/requirement/`, `docs/plans/` and `docs/verify/`.
- Review findings for triage are in `docs/review/`; do not read them for a build task. Read a proposal in `docs/proposal/` only when the intent's requirement links to it.

## Commands
<!-- onboarding
ask: no
reason: The base commands; the same as repo-map.json commands.
-->

```bash
python3 orchestration/run_all.py          # ingestion, then dbt build
python3 orchestration/run_ingest.py       # dlt pipelines
python3 orchestration/run_transform.py    # dbt build
python3 -m pytest tests -q                # Python tests
```

The command for each layer's tests is in `test-map.json`.

## Safety
<!-- onboarding
ask: no
reason: Platform safety; the same for every domain.
-->

- The local warehouse is `domain.duckdb` at the repo root. It is ignored by git and rebuilt by `orchestration/run_all.py`. Never commit it or downloaded data.
- Never commit secrets. dlt reads them from the bound secret store.
- Do not edit `transformation/profiles.yml` to make a failure pass.

## Maintenance rules
<!-- onboarding
ask: no
reason: Keeps the maps honest; the guards are the map tests.
-->

Keep these current in the same change that makes them stale.

| Artifact | Update when | Guard |
| --- | --- | --- |
| `repo-map.json` | A layer, source, pipeline, entrypoint, command or artifact location is added, renamed or removed | `tests/test_maps.py` |
| `test-map.json` | A layer appears in the repo-map, or a new test starts protecting a layer | `tests/test_maps.py` |
| `CONTEXT.md` | A term appears in, or changes meaning in, a model, ADR or design record | none |
| `.agents/rules/` | A convention changes | none |
| `AGENTS.md` | A durable fact the code does not show | none |
