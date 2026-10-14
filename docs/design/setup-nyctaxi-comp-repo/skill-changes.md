# Skill changes

What should change in the `vibedata-data-engineering` plugin (`~/src/studio/ext/vd-data-engineering/plugins/vibedata-data-engineering`), derived from building this repo. Paths in the Reference column are relative to the plugin root. The conventions behind each row are in `conventions-inventory.md`; the gaps found while building are in `skill-change-notes.md`.

## Principle

A convention belongs to one of three owners:

- **Skill** (platform): safety, correctness of the loop, and anything a CI script reads. It stays in the plugin.
- **Rule** (operator): naming, layout, style, test policy and content bars. It lives in the repo's `.agents/rules/`, and the skills read it.
- **Repo-map** (operator): where things are. It lives in `repo-map.json`, and the skills resolve locations from it.
- Standing business answers are ADRs in the repo; a skill checks them before asking.

There is no "default in the skill, override in the repo". A skill that restates a rule today should link to it and drop the text.

## What `init` must do

`skills/init/SKILL.md` today writes one file, `AGENTS.md`, from `_shared/templates/agents-md-template.md`, and stops if it exists. The repo needs five more things before the other skills work efficiently.

**Both cases**

1. Write `repo-map.json`, validated against `repo-map.schema.json` (both shipped as templates): layers with the builder of each (`dlt` or `dbt`), sources, `artifact_paths`, entrypoints, commands, modules.
2. Write `AGENTS.md` as an index: a short domain paragraph, the rules table, and the commands. No inline conventions.
3. Write `.agents/rules/`: `dbt-models.md`, `sql-style.md`, `dbt-testing.md`, `dlt.md`, `context.md`, `adr.md`, `design-records.md`, `git-and-prs.md`, from templates under `_shared/templates/rules/`.
4. Write `test-map.json` once a test lane exists: each layer to its narrow command.
5. Run `install-ci` when the platform has a bundle, and add the `.gitignore` fragments (`**/secrets.toml`, `.agents_tmp/`, `*.log`).

**Greenfield**: write the defaults. Layers `bronze` (dlt), `staging`, `intermediate`, `marts/<area>`; design records at `docs/design/models/{model}.md`; ADRs at `docs/adr/{nnnn}-{slug}.md`; the plugin's current template values for every rule.

**Brownfield**: detect first, then write what exists, and ask only about what it cannot tell.

- Find the dbt project directory and read `model-paths`, `test-paths`, `seed-paths` from `dbt_project.yml`.
- Derive layers from the model folders and `+schema` config; read each source's loader (a `pipelines`/`ingestion` folder means dlt, a loader script means `script`).
- Detect the existing design-record layout (flat or by layer), ADR numbering and `CONTEXT.md` format, and record them in `artifact_paths` rather than moving files.
- Detect naming from the models that exist (prefixes, double-underscore staging names) and write those into `dbt-models.md`.
- Detect the test layout (generic YAML tests, singular tests, unit tests) for `dbt-testing.md` and `test-map.json`.
- Where existing files differ from the plugin templates (ADR frontmatter, glossary entry format, design-record sections), report the gap and offer a conforming pass instead of rewriting.
- Never overwrite an existing `AGENTS.md`, rule, map or document.

**What this repo needed that `init` does not do today**: the layered design-record layout declared (`docs/design/models/{layer}/{model}.md`), a flat staging layout declared, a repo with dlt sources and no `ingestion/.dlt/config.toml`, and the three environment variables for running dlt outside Studio.

## Changes by skill

| Skill | Reference | Suggested change |
| --- | --- | --- |
| init | `skills/init/SKILL.md` steps 1 to 3 | Extend as in the section above: write `repo-map.json`, rules, `test-map.json` and the index `AGENTS.md`; detect on a brownfield repo. |
| init | `_shared/templates/agents-md-template.md` (Medallion Layers, Model Naming, File Organization, Testing, SQL Style) | Reduce to an index. Move each inline section to a rule template. Add a rules table and a pointer to `repo-map.json`. |
| init | `_shared/templates/` (new) | Add `repo-map-template.json`, `repo-map.schema.json`, `test-map-template.json` and `rules/*.md`. |
| domain-modeling | `skills/domain-modeling/SKILL.md` steps 1, 4, 5 | Read `.agents/rules/context.md` and `adr.md` for what belongs; delete the restated bars (three tests, no example values, no consumers). Keep the mechanics: five glossary changes, supersession, commit. |
| domain-modeling | `_shared/references/conventions/domain-context-and-adrs.md` lines 15 to 16 | Move the content bars to the operator rules. Keep the format rules that CI scripts read (frontmatter, section names). |
| domain-modeling | `_shared/templates/adr-template.md` | Add an `## Affected designs` section (relative links to design records). Step 6 (supersede) also updates the design records that cited the old ADR to cite its successor. |
| domain-modeling | `skills/domain-modeling/SKILL.md` step 4 | Treat a standing business answer (week boundary, null and unmatched-key handling, aggregation of nulls) as an ADR. |
| domain-modeling | `_shared/templates/context-md-template.md` | Drop the "belongs here / belongs in the catalog" table; it is content policy, and now lives in `context.md`. |
| designing | `_shared/references/conventions/artifact-paths.md` (Model design row, line 21) | Resolve the design-record path from `repo-map.json` `artifact_paths.design_record_model`; use the flat default only when no repo-map exists. Replace "AGENTS.md names a location wins" with the repo-map. |
| designing | `skills/designing/SKILL.md` steps 6, 8, 9 | When a record cites an ADR, update that ADR's `## Affected designs` in the same commit. |
| designing | `_shared/templates/model-design-template.md` (Consumers) | Say "dependents only, from lineage (`dbt ls --select <model>+`); no teams or reports". Read `.agents/rules/design-records.md`. Add the optional `## Semantic Model` section that `generating-semantic-model` reads. |
| capturing-requirements | `_shared/playbooks/kinds/transformation.md` `## Intent` (week boundary, null and unmatched-key handling, NULL aggregation) | Search `docs/adr/` for a standing answer first; ask only when none exists. |
| capturing-requirements | `skills/capturing-requirements/SKILL.md` step 3 | Resolve locations from `repo-map.json`. The intent root stays platform-owned (`VD_INTENT_DOCS_ROOT`). |
| generating-dbt-model | `skills/generating-dbt-model/SKILL.md` steps 7 and 11; `references/artifact-kinds.md` | Naming, folder layout, properties-file naming, materialisation and audit columns come from `.agents/rules/dbt-models.md` and `repo-map.json` `layers`. Remove the restated defaults. |
| generating-dbt-model | `skills/generating-dbt-model/SKILL.md` step 10 | Test policy (key and relationship tests, which models need a unit test) comes from `.agents/rules/dbt-testing.md`. |
| generating-dbt-model | `references/artifact-kinds.md` line 21 | Replace "tell the user `/init` can seed AGENTS.md" with the extended `init`. |
| generating-dbt-model | `_shared/references/guides/medallion-guardrails.md` (Silver, Cross-layer) | Keep as platform correctness. Add: Arrow timestamps load as `TIMESTAMPTZ`, so staging converts them (`timezone('UTC', col)`) before any key is hashed; and a staging model reads `source()` only, including models that rebuild a key. |
| generating-dbt-model | `_shared/references/conventions/runtime-audit-columns.md` | Make audit columns an operator rule (`dbt-models.md`); keep the all-or-none and hashing guidance. |
| generating-dbt-model | `references/artifact-kinds.md` (incremental) | State that an incremental fact needs `--full-refresh` after any change to upstream logic; the stale table fails relationship tests. |
| generating-dlt-pipeline | `skills/generating-dlt-pipeline/SKILL.md` step 2; `_shared/references/guides/ingestion-artifact-paths.md` | Read `repo-map.json` `artifact_paths` (`ingestion_root`, `pipeline`, `resource_docs`) instead of the fixed table; keep the flat default when absent. |
| generating-dlt-pipeline | `skills/generating-dlt-pipeline/SKILL.md` step 5 (knobs, line 46); `_shared/templates/pipeline-inventory-template.md` | Write-disposition defaults, schema-contract defaults and the sample-load default come from `.agents/rules/dlt.md`. |
| generating-dlt-pipeline | `_shared/references/guides/medallion-guardrails.md` Bronze (lines 7 to 10) | Move "no casts, filters, joins in bronze", "never drop `_dlt_*`" and the `src_<connection>` default to `dlt.md`. Keep the `BRONZE_INADEQUATE` halt in the skill. |
| generating-dlt-pipeline | `skills/generating-dlt-pipeline/SKILL.md` steps 4 and 5 | Support a pipeline with more than one source object that is not a catalog connector: a custom source module, a generated source, a source built from another source's output read in memory. Today the template assumes one vendored connector. |
| generating-dlt-pipeline | `_shared/platforms/duckdb_local/templates/dlt-pipeline.py` | For file sources: set `[schema] naming = "direct"` when names must be kept, and `[normalize.parquet_normalizer] add_dlt_load_id/add_dlt_id`; dlt otherwise snake-cases names and omits the load columns on Arrow data. Changing either on an existing database fails, so rebuild it. |
| generating-dlt-pipeline | `_shared/platforms/duckdb_local/dlt.md` `## Sandbox run` | Document the three variables `setup_environment()` needs outside Studio: `VD_DOMAIN_DATA_PLATFORM=duckdb_local`, `VD_DOMAIN_SECRET_STORE_KIND=local_toml`, `VD_EPHM_DUCKDB_LOCAL_PATH`. |
| generating-dlt-pipeline | `references/audit-tests-docs.md` (schema contract) | A pipeline whose database is rebuilt from empty each run keeps `tables: evolve`; freezing forbids creating the tables. |
| generating-dlt-pipeline | `skills/generating-dlt-pipeline/SKILL.md` step 15 | Resolve the dbt sources file from `artifact_paths.dbt_sources`; do not create a second sources file when the repo has one. |
| add-or-update-source | `skills/add-or-update-source/SKILL.md` steps 3 and 8 | Add a route for sources defined in the repo (`connector = "custom"`, `connector_source = "local"`) and for generated sources. Today only catalog connectors (`dlt-verified`, `dlt-builtin`) are accepted. |
| add-or-update-source | `skills/add-or-update-source/references/local-files-route.md` line 19 | The `schema` default (`src_<connection>`) comes from `dlt.md`. |
| generating-orchestration | `skills/generating-orchestration/SKILL.md` steps 1 and 3; `_shared/platforms/<platform>/orchestration.md` | Add a `duckdb_local` route: scripts at `artifact_paths.orchestration`, run in order (ingestion, then `dbt build`), named in `repo-map.json` `entrypoints` and `commands`. Today the skill halts or omits when the platform file is absent. |
| generating-semantic-model | `skills/generating-semantic-model/SKILL.md` step 5 | Allow helper metrics: a MetricFlow ratio metric takes metrics, not measures, as numerator and denominator. Say where the YAML goes (`models/marts/<area>/_semantic.yml`) from the repo-map. |
| verifying | `skills/verifying/SKILL.md` step 7 | Make "words against data" checkable: every `ADR NNNN` citation resolves; an ADR and the design records it lists agree both ways; CONTEXT, ADR and design-record content follow the three content rules. Ship a script beside `adr_lint.py`. |
| verifying | `_shared/playbooks/kinds/transformation.md` `## Verify` | Add a silent-miss check: every natural-key rejoin matches every row. A key hashed from differently typed inputs matches nothing, the left join reports every value missing, and the build stays green. This repo hit it. |
| shipping | `skills/shipping/references/pr-publication.md` line 65 | PR body sections come from `.agents/rules/git-and-prs.md`; keep the `Ship-Step:` trailer in the skill. |
| shipping | `_shared/references/conventions/git-workflow.md` | Commit subject format comes from `git-and-prs.md`. Branch naming stays with the platform (Studio assigns `intent/<slug>`). |
| planning | `skills/planning/SKILL.md` (gate commands) | Take each task's gate from `test-map.json` instead of rediscovering the narrow command. |
| executing-the-plan | `skills/executing-the-plan/SKILL.md` | Same: run the gate named by `test-map.json` for the task's layer. |
| install-ci | `skills/install-ci/SKILL.md` deploy step; `domain-cicd/shared/scripts/bundle_deploy.py` | The manifest writes `.git/hooks/*`. In a git worktree `.git` is a file and the hooks directory is shared with the main checkout. Deploy only tracked paths (`.github/`, `.workflow/`), and install hooks separately through `git rev-parse --git-path hooks`, with consent. |
| install-ci | `domain-cicd/shared/scripts/adr_lint.py`, `design_drift.py` | `adr_lint.py` checks numbering and dangling citations only; add the two-way link check. `design_drift.py` should read the design-record path from `repo-map.json` so layered layouts and the `## Semantic Model` section pass. |
| install-ci | `skills/install-ci/SKILL.md` (slug) | Ask for `VD_DOMAIN_SLUG` when it cannot be derived; the template placeholder is `<domain-name>`. |
| grilling | `skills/grilling/SKILL.md` step 6 | No change except linking to the content rules through `domain-modeling`. |
| reconciliation | `skills/reconciliation/SKILL.md` | No change. |
| ephemeral-workspace-recovery | `skills/ephemeral-workspace-recovery/SKILL.md` | No change. |

## Order

1. Ship the rule and repo-map templates, and the extended `init`. Nothing else depends on the content rules until the skills read them.
2. Change the skills that restate a rule to read it (`domain-modeling`, `designing`, `generating-dbt-model`, `generating-dlt-pipeline`, `shipping`), one at a time, each with its eval cases.
3. Add the new routes (`add-or-update-source` for custom sources, `generating-orchestration` for `duckdb_local`).
4. Update CI (`install-ci`, `adr_lint.py`, `design_drift.py`).
