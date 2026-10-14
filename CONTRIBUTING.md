# Contributing

## Set up

Follow the prerequisites in [`README.md`](README.md), then build once:

```bash
python3 orchestration/run_all.py
```

## Before you push

```bash
python3 -m pytest tests -q
ruff check . --extend-exclude .github,ingestion/sources
sqlfluff lint transformation/models
cd transformation && dbt test --exclude test_type:unit && dbt test --select test_type:unit
```

`test-map.json` names the narrow command for each layer, so a change to one model
needs only its layer's tests until the final run.

## Conventions

The operator conventions are in [`.agents/rules/`](.agents/rules/), indexed by
[`AGENTS.md`](AGENTS.md):

- model and file naming, layers and materialisation: [`dbt-models.md`](.agents/rules/dbt-models.md)
- SQL formatting: [`sql-style.md`](.agents/rules/sql-style.md)
- tests: [`dbt-testing.md`](.agents/rules/dbt-testing.md)
- pipelines: [`dlt.md`](.agents/rules/dlt.md)
- commits and pull requests: [`git-and-prs.md`](.agents/rules/git-and-prs.md)

`repo-map.json` says where each kind of file lives. Update it, and `test-map.json`,
when a layer, entrypoint, command or location changes; `tests/test_maps.py`
fails when either names something that does not exist.

## Decisions and designs

- A decision that is hard to reverse, surprising without context and a real
  trade-off is an ADR in `docs/adr/`. Standing business answers are ADRs too.
  See [`adr.md`](.agents/rules/adr.md). Never edit a decision that still holds;
  supersede one that does not.
- Each model and pipeline has a design record under `docs/design/`, and an ADR
  lists the design records it affects. See
  [`design-records.md`](.agents/rules/design-records.md).
- New terms go in `CONTEXT.md` only when a model, ADR or design record uses them.
  See [`context.md`](.agents/rules/context.md).
- Requirements for a piece of work go in `intents/<slug>/requirement.md`.

## Pull requests

Use the four sections in [`git-and-prs.md`](.agents/rules/git-and-prs.md): Summary,
Verification, Approved contract changes, Remaining manual checks.
