---
name: onboarding
description: "Use only when the user asks to onboard this repository into a Vibedata domain: an existing dbt and dlt repo that has no repo-map.json or .agents/rules yet. Do not use for adding sources or models, for any other build task, or to refresh an already onboarded repo."
user-invocable: true
triggers: [onboard this repo, onboard into vibedata, onboard into a vibedata domain]
---

# Onboarding

Onboarding is an intent kind. It captures what the repo already does, so later intents can work in it, and files everything that should change for triage. It ships context, not code.

## The two stages

1. **This intent**: capture conventions, write the context, file the onboarding review, ship one PR.
2. **Later intents**: each review finding an engineer picks up is a normal intent (requirement, design, build, verify, ship). An intent that changes code compares output before and after in its own session.

So during onboarding you change no model, pipeline or human document. A problem you find goes in the review, even when the fix is one line. The only other changes are the base setup in [base-setup.md](references/base-setup.md): two `dbt_project.yml` lines the sandbox build needs, and files added where the repo has none.

## Loop phases

| Phase | Work |
| --- | --- |
| Requirement | Scope: which dbt projects and dlt pipelines. The deliverable is the context and the review. |
| Design | Discover the repo (dbt project, dlt pipelines, profiles, CI, existing documents) and run a build on the sandbox `dev` target. The runtime provides that profile; the repo's own `profiles.yml` targets are for local and CI use, so do not ask which target the sandbox uses. First run the base commands: [base-setup.md](references/base-setup.md). Then build the inventory: [inventory.md](references/inventory.md). Confirm it: [grilling.md](references/grilling.md). Find domain-skill candidates: [domain-skills.md](references/domain-skills.md). |
| Build | `init` writes `repo-map.json`, `test-map.json`, the map tests, the `AGENTS.md` index and `.agents/rules/` from the confirmed inventory, plus the base setup files and base rules in base-setup.md. Write confirmed domain skills under `.agents/skills/`. `domain-modeling` writes `CONTEXT.md` and the ADRs for decisions already in the code. Write design records as the `designing` skill and `.agents/rules/design-records.md` say, only where a model or pipeline makes a decision its code does not explain. A `D-NN` line is a choice plus its reason; a line that only says what the code does is not a decision. Handle existing documents: [existing-docs.md](references/existing-docs.md). Declare `docs/review/` and `docs/proposal/` in `repo-map.json`. Run `install-ci`. Run `reviewing` with type `onboarding`, including the checks in base-setup.md. |
| Verify | Base commands, map tests in the sandbox, CI, ADR citations, then the dry run: [dry-run.md](references/dry-run.md). |
| Ship | One PR. The description lists where each existing convention went, and recommends a trial intent after merge: a standard prompt, with its trajectory reviewed. |

## Where things go

| Thing found | Destination |
| --- | --- |
| A location or identity a script can check | `repo-map.json` |
| A must or never for every change of a kind | `.agents/rules/` |
| A multi-step procedure only this repo has, confirmed by the user | `.agents/skills/` |
| A decision with a reason (why this grain, this filter, this key) | ADR |
| A business term | `CONTEXT.md` |
| A decision one model or pipeline makes that its code does not explain | That model's design record |
| Anything that should change | Onboarding review finding |

## Common mistakes

| Mistake | Instead |
| --- | --- |
| Design record lists inputs, tests, columns, SQL, or decisions that only describe the code ("vendor resolved the same way", "key is an md5 of the flags") | Grain, `D-NN` decisions with their source, rejected alternatives, consumers, evidence, history. No record when there is nothing beyond the code. |
| Conventions written into `AGENTS.md` | `AGENTS.md` is an index; conventions go to rules. |
| Editing README or CONTRIBUTING, or linking agents to them | Leave human documents alone. Tell agents not to read them. |
| Fixing a tracked generated file, a broken config path or a lint setting now | A review finding. |
| Asking the user what the code already answers | Infer, show the inventory, ask only the three kinds of question in grilling.md. |
| An ADR rationale you made up | Write the decision, mark the reason `inferred from code`, and file it for confirmation. |
