# Workarounds

Temporary rules that cover a gap in a platform skill or document. Each names the change that makes it redundant. When that change ships, delete the rule and its row in `AGENTS.md`. Track whether a rule helped in `docs/setup/skill-changes.md`.

## Write `plan.md` and `verify.md` once per phase

Draft the file once. Keep progress and evidence in your head or in a scratch note, and write them into the file in a single edit at the end of the phase. Do not edit the file after each task or check. Each edit echoes a snippet of the file back, and these files are large.

Remove when: the `planning`, `executing-the-plan` and `verifying` skills write these files once per phase (`skill-changes.md`).

## Run dbt in the sandbox

The repo's `transformation/profiles.yml` has `domain` and `slice` targets for local and CI use. Do not open it, or `~/.dbt/profiles.yml`, for any reason: not to work out how to run dbt, and not for the shipping contract check, which has nothing to read on this platform (no contracts are published for `duckdb_local`). The runtime provides the profile (`DBT_PROFILES_DIR`, `DBT_PROFILE_NAME`) and one target, `dev`, which writes the sandbox file. Run dbt through the runtime wrapper from `transformation/`:

```bash
cd transformation && <plugin>/scripts/vd-intent-context-run.sh "dbt <command> --target dev"
```

Run `dbt deps` the same way first if `dbt_packages/` is missing. The plain commands in `repo-map.json` `commands` are for a local checkout.

Remove when: the platform `duckdb_local/dbt.md` states this command (`skill-changes.md`).

## Run `dbt_project_evaluator` only for transformation changes

The verifying skill runs `dbt_project_evaluator` whenever the package is installed. Run it only when the change touches dbt models, tests, macros, seeds or `dbt_project.yml`. Registering a new source in `_sources.yml` does not count: an ingestion change always adds that entry, and the evaluator has nothing to judge until a model reads the source. For an ingestion-only change, skip it and say so in `verify.md`. Enable it with `--vars '{dbt_project_evaluator_enabled: true}'`.

Remove when: `skills/verifying/SKILL.md` step 3 gates the evaluator on the change kind (`skill-changes.md`).

## Change large files with a script, not the file editor

The file editor echoes the file back after every edit; for `repo-map.json`, YAML properties files, `plan.md` and `verify.md` that is 15K to 27K characters per edit. Change them with a script and print only what you need to confirm:

- `repo-map.json`, `test-map.json`: load with Python `json`, change, dump with `indent=2`, then validate (`python3 -m pytest tests/test_maps.py -q`).
- `plan.md`, `verify.md`: append with a heredoc, or replace one block with a short Python `str.replace`.
- YAML properties files (`_sources.yml`, `_staging.yml`): a short Python `str.replace` on a unique anchor.

Never make two edits to the same file in parallel.

Remove when: the editor caps its echo (`skill-changes.md`, platform file editor).

## Lint with ruff, not `check_python`

Lint Python with `ruff check <files>`. It uses the repo's `ruff.toml`; the `check_python` tool applies rules this repo does not use, and its fixes are churn.

Remove when: the skills name the repo's lint command from `repo-map.json` (`skill-changes.md`).

## Verify from the landed table and the saved profile

An independent recount at verify reads the landed table and `.agents_tmp/<source>-profile.json`. It never reads the remote source file again.

Remove when: `verifying` says where independent figures come from for an ingestion change (`skill-changes.md`).

## Tier-1 tests after a safety run

A `DEV_MODE` safety run loads into a timestamped dev dataset (`bronze_<timestamp>`), printed by the run. Pass that name to `run_bronze_tier1_tests.py --dataset`, not `bronze`. After the full load, pass `bronze`.

Remove when: the Tier-1 runner finds the dev dataset itself (`skill-changes.md`).

## Run each gate once per commit

Record each gate's command, commit and result in `plan.md` when it runs. Verify re-runs a gate only when a file it covers changed after the recorded commit; otherwise it cites the recorded result. Shipping re-runs nothing when the only changes since verify are the intent's own Requirement, Plan or Certification: the certification commit's results stand.

Remove when: `verifying` and `shipping` reuse recorded gate results at the same inputs (`skill-changes.md`).

## The contract check at ship needs dbt packages

`shipping` materialises the base commit's manifest with `diff_manifest_contract.py --materialize`, which checks the base out into a fresh git worktree and runs `dbt parse` there. A fresh worktree has no `dbt_packages/`, so the parse fails on this project's `packages.yml`. Run `dbt deps` first through `--dbt-command`, from the repo root:

```bash
printf '#!/bin/sh\ndbt deps --quiet || exit $?\nexec "$@"\n' > .agents_tmp/dbt-deps-then.sh && chmod +x .agents_tmp/dbt-deps-then.sh
python3 <plugin>/scripts/diff_manifest_contract.py --materialize <base sha> transformation .agents_tmp/base_manifest.json \
  --dbt-command ".agents_tmp/dbt-deps-then.sh dbt parse"
```

Then diff it against `transformation/target/manifest.json` as the skill says.

Remove when: `--materialize` installs packages itself (`skill-changes.md`).
