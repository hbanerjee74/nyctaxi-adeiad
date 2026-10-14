# Workarounds

Temporary rules that cover a gap in a platform skill or document. Each names the change that makes it redundant. When that change ships, delete the rule and its row in `AGENTS.md`. Track whether a rule helped in `docs/setup/skill-changes.md`.

## Write `plan.md` and `verify.md` once per phase

Draft the file once. Keep progress and evidence in your head or in a scratch note, and write them into the file in a single edit at the end of the phase. Do not edit the file after each task or check. Each edit echoes a snippet of the file back, and these files are large.

Remove when: the `planning`, `executing-the-plan` and `verifying` skills write these files once per phase (`skill-changes.md`).

## Run dbt in the sandbox

The repo's `transformation/profiles.yml` has `domain` and `slice` targets for local and CI use. Do not open it, or `~/.dbt/profiles.yml`, to work out how to run dbt in the sandbox. The runtime provides the profile (`DBT_PROFILES_DIR`, `DBT_PROFILE_NAME`) and one target, `dev`, which writes the sandbox file. Run dbt through the runtime wrapper from `transformation/`:

```bash
cd transformation && <plugin>/scripts/vd-intent-context-run.sh "dbt <command> --target dev"
```

Run `dbt deps` the same way first if `dbt_packages/` is missing. The plain commands in `repo-map.json` `commands` are for a local checkout.

Remove when: the platform `duckdb_local/dbt.md` states this command (`skill-changes.md`).
