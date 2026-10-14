# Workarounds

Temporary rules that cover a gap in a platform skill or document. Each names the change that makes it redundant. When that change ships, delete the rule and its row in `AGENTS.md`. Track whether a rule helped in `docs/setup/skill-changes.md`.

## Write `plan.md` and `verify.md` once per phase

Draft the file once. Keep progress and evidence in your head or in a scratch note, and write them into the file in a single edit at the end of the phase. Do not edit the file after each task or check. Each edit echoes a snippet of the file back, and these files are large.

Remove when: the `planning`, `executing-the-plan` and `verifying` skills write these files once per phase (`skill-changes.md`).

## Run dbt in the sandbox

The repo's own `profiles.yml` targets are for local and CI use. Do not open it, or `~/.dbt/profiles.yml`, to work out how to run dbt in the sandbox. The runtime provides the profile (`DBT_PROFILES_DIR`, `DBT_PROFILE_NAME`) and one target, `dev`, which writes the sandbox file. Run dbt through the runtime wrapper from the dbt project directory:

```bash
cd <dbt project> && <plugin>/scripts/vd-intent-context-run.sh "dbt <command> --target dev"
```

Run `dbt deps` the same way first if `dbt_packages/` is missing. The plain commands in `repo-map.json` `commands` are for a local checkout.

Remove when: the platform `duckdb_local/dbt.md` states this command (`skill-changes.md`).

## Run `dbt_project_evaluator` only for transformation changes

The verifying skill runs `dbt_project_evaluator` whenever the package is installed. Run it only when the change touches dbt models, tests, macros, seeds or `dbt_project.yml`. Registering a new source in `_sources.yml` does not count: an ingestion change always adds that entry, and the evaluator has nothing to judge until a model reads the source. For an ingestion-only change, skip it and say so in `verify.md`. Enable it with `--vars '{dbt_project_evaluator_enabled: true}'`.

Remove when: `skills/verifying/SKILL.md` step 3 gates the evaluator on the change kind (`skill-changes.md`).
