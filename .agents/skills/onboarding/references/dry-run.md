# Dry run

Checks first: the map tests and the ADR link test pass, CI is green, and every `ADR NNNN` citation resolves.

Then pick three tasks a user of this repo would ask for:

1. Add a source like an existing one.
2. Add or change a mart model.
3. The most used domain skill, or a change to the most connected intermediate model.

For each, using only `AGENTS.md`, `repo-map.json` and `.agents/skills/`, write down:

| Task | Files read | Files changed or created | Commands |
| --- | --- | --- | --- |

Then check every entry against the repo: the paths exist, the command runs in the sandbox, and nothing the task needs is missing from the context. Do not run a build.

Each miss is a context fix before shipping, or a finding in the review. Record the table and its result in this intent's `verify.md`, not under `docs/review/`.

When a template or a reference changes, run `python3 -m pytest tests/setup/test_onboarding_dry_run.py -q` in the repo that carries this skill: it bootstraps a scratch Domain from [templates/](../templates/) as [greenfield.md](greenfield.md) says, then runs the plugin gates (the template map tests, the ontology validator, `odcs.py check` and `generate` over a proposed input contract) against it. A template that drifts from the semantic ownership model fails there before a customer sees it.
