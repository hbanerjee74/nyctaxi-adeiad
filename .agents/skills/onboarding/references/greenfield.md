# Greenfield

The repo has no dbt project and no pipelines, and the Domain database is empty. Onboarding sets up an empty, working project so the first intent is a plain "add a source".

## Requirement

Ask what the domain is for and where its data will come from. Scope: the whole repo.

## Design: grill by file and section

Use the `grilling` skill. Every template under [templates/](../templates/) marks each section with an `<!-- onboarding -->` block:

- `ask: yes`: a question, a recommended answer and the alternatives. Ask these.
- `ask: no`: platform-driven, with the reason. Show them, do not ask.

Go file by file, in this order: `AGENTS.md`, then the `dbt-models`, `dlt`, `dbt-testing`, `sql-style` and `git-and-prs` skills, then the content skills and `workarounds`. For each file, show every section's recommended text in one message and ask its `ask: yes` sections one at a time, recommendation first; the user may also override an `ask: no` section. A section answered once (for example the layers, in `AGENTS.md` and `dbt-models.md`) is not asked again.

Also ask the dbt project name (recommended: the domain slug with underscores), and pass the first business terms to `domain-modeling` for `CONTEXT.md`.

## Build

Write from [templates/](../templates/), filling the confirmed answers:

| Write | From |
| --- | --- |
| `transformation/dbt_project.yml`, `packages.yml`, `profiles.yml` | `templates/dbt/` |
| `transformation/macros/relations.sql`, `generate_schema_name.sql` | `templates/dbt/` |
| `transformation/models/<layer>/` per confirmed layer, `models/staging/_sources.yml` (`version: 2`, no sources), `transformation/tests/` | empty, with a `.gitkeep` where a folder would be empty |
| `ingestion/.dlt/config.toml`, `ingestion/sources/`, `ingestion/requirements.txt` | `templates/dlt/` |
| `tests/conftest.py`, `tests/orchestration/test_run.py` | `templates/tests/` (`test_run.py` goes under `tests/orchestration/`) |
| `orchestration/run_ingest.py`, `run_transform.py`, `run_all.py` | `templates/orchestration/` |
| `tests/test_maps.py`, `tests/test_adr_links.py` | `templates/tests/` |
| Where the repo checks run | The Repo checks question in [base-setup.md](base-setup.md); recommended `.github/workflows/repo-checks.yml` from `templates/repo/` |
| `repo-map.json`, `repo-map.schema.json`, `test-map.json` | `templates/repo/`, layers (each with its `role`) from the answers, `data_platform` from the platform, `semantic_exclusions` and `sources` empty |
| `AGENTS.md`, `ruff.toml`, `requirements-dev.txt`, `.gitignore` (`gitignore-fragment`) | `templates/repo/`, `<!-- onboarding -->` blocks removed |
| `.sqlfluff` | `templates/repo/sqlfluff.cfg`; its profile comes from `.github/profiles/`, which `install-ci` writes |
| `docs/adr/`, `docs/design/`, `docs/review/`, `docs/proposal/` | empty, with a `.gitkeep` (the template `test-map.json` lists `docs/adr/` and `docs/design/` as the decisions module's sources) |
| `contracts/`, `ontology/`, and the `data-contract`, `validating-data-contract`, `ontology` and `validating-ontology` skills | `contracts/` and `ontology/` empty with a `.gitkeep`; the four skills seeded whole (`SKILL.md`, `scripts/`, `references/`), plus `.agents/skills/semantic-model/scripts/` alone (the ontology checker), by Semantic layer, ontology and contracts in [base-setup.md](base-setup.md). Declared in both maps, so the first contract and the first concept have their path |
| `.agents/skills/<name>/SKILL.md`, one per convention skill | `templates/skills/<name>.md`, with the confirmed answers in place of the placeholders and every `<!-- onboarding -->` block removed |
| `CONTEXT.md` and any ADR a confirmed decision earns | `domain-modeling` |
| CI, `.github/profiles/`, `.github/scripts/adr_lint.py` | `install-ci`. Not optional: `.sqlfluff` and the `adr_lint` command depend on it |

Fill the placeholders:

| Placeholder | Value |
| --- | --- |
| `<project_name>` | The confirmed dbt project name, in `dbt_project.yml`, `profiles.yml` and `run_transform.py` |
| `<Domain name>`, `<domain paragraph>` | The requirement answer |
| `<domain slug>`, `<one line>` | `repo-map.json` `applications`: the slug and the domain paragraph's first sentence |
| `<raw schema>`, `<source system>` | `repo-map.json` `layers`: one entry per confirmed input schema, keyed by its name, `role` `input`, `path` `ingestion/` |
| mart areas | One `layers` entry (`role` `boundary`) and one `dbt_project.yml` block under `marts` per confirmed area, path `transformation/models/marts/<area>/` |
| `<platform>` | `repo-map.json` `data_platform`: the platform kind the Domain runs on, which `servers[].type` in every contract derives from |
| Ossie document | Not created at greenfield: there is no fact to model yet, and the `semantic-model` and `validating-semantic-model` skills are not seeded. The first intent that lands a fact-bearing boundary mart seeds them, creates `logical-model/`, registers it in `repo-map.json` and `test-map.json`, and validates it before shipping |
| `<UTC timestamp>` | The time of writing, in both maps |
| `orchestrators` | Keep the `run_ingest` entry the template ships (`kind: python`, `path: orchestration/run_ingest.py`, `runs: []`). The first source adds itself to `runs` and to `PIPELINES`; a runner outside the repo is a separate entry with `location` |

Write no source, pipeline, model, contract or design record: the first intent adds them. Its input relation gets a contract (`status: proposed` until the table lands), whose `generate` writes `ingestion/contracts.py`; the pipeline imports `COLUMNS` from it. Write no review file: there is nothing to review, and `reverse` has nothing to draft.

## Verify

Install `requirements-dev.txt`. The base commands pass on the empty project: `dbt deps`, `dbt parse`, `python3 -m pytest tests -q`, `ruff check .`, and `odcs.py check` over the empty `contracts/`. `ossie.py validate ontology/` reports `cli/no-files` until the first concept lands, so it joins the ontology module's `structural` command then. `dbt parse` warns that the layer config paths match no models: expected until each layer has its first model; do not remove the blocks. Then the dry run, with one task: add the first source.

## Ship

One PR. The commit body and the PR description list the confirmed answers, one line per section, and recommend the next intent: add the first source.
