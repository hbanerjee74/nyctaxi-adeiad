# Skill changes

What should change in the `vibedata-data-engineering` plugin (`~/src/studio/ext/vd-data-engineering/plugins/vibedata-data-engineering`), derived from building this repo. Paths in the Reference column are relative to the plugin root. The conventions behind each row are in `conventions-inventory.md`; the gaps found while building are in `skill-change-notes.md`.

Rows whose change has shipped, or whose target no longer exists after the VD-6872 simplification (vibedata-data-engineering#797), were removed on 2026-10-16. What remains is open or partly done. On the same day the rest were filed in Linear (below), or done in this repo's onboarding: the ADR link test and the repo-checks workflow (`tests/test_adr_links.py`, `.github/workflows/repo-checks.yml`), and loading an empty Domain database in the onboarding sandbox or proposing its seeding. The dlt preview row was dropped: onboarding's `.gitignore` lines cover it. The `duckdb_local` orchestration row was dropped: DuckDB has no native orchestrator, so orchestration is the repo's own run scripts (`orchestration/`, from onboarding's templates, named in `repo-map.json` `entrypoints` and `commands`).

## Principle

A convention belongs to one of three owners:

- **Skill** (platform): safety, correctness of the loop, and anything a CI script reads. It stays in the plugin.
- **Rule** (operator): naming, layout, style, test policy and content bars. It lives in the repo's `.agents/skills/`, and the skills read it.
- **Repo-map** (operator): where things are. It lives in `repo-map.json`, and the skills resolve locations from it.
- Standing business answers are ADRs in the repo; a skill checks them before asking.

There is no "default in the skill, override in the repo". A skill that restates a rule today should link to it and drop the text.

## `init` is retired

The onboarding skill (`.agents/skills/onboarding/`) replaces `init` for both an empty repo and an existing dbt and dlt repo. It carries what this section used to ask `init` for: the `repo-map.json`, `repo-map.schema.json`, `test-map.json` and `AGENTS.md` templates, every rule template, a generic `tests/test_maps.py`, the dbt, dlt and orchestration templates, the base commands, `ruff.toml` and the `.gitignore` lines. Each template section is marked for grilling with a recommended answer.

## Changes by skill

| Skill | Reference | Suggested change |
| --- | --- | --- |
| platform (Studio runtime) | conversation condensation | Once VD-6910 has shipped, check in the next long run that the agent still follows the repo's rules after a condensation. In run b2f37191 and the seventh HVFHV run it stopped following `workarounds` after condensing (repeated `verify.md` edits, a missed contract-check workaround). If it still drifts, the fix is to keep `AGENTS.md` and the skills it names in context through a condensation. |
| `generating-dlt-pipeline` | repo-map registration; the new-source footprint | A new source joins its runner's `repo-map.json` `orchestrators.<name>.runs`, in addition to its `sources` entry. `runs` is the set; the runner's own code holds the order. The skill's footprint list must name `orchestrators`, or every repo it builds leaves a raw table with no declared producer. |
| `add-or-update-source` | adding a table to an existing source | When the new table makes a `dataset` shared by two sources, both sources declare `produces` (their table names). With a single owner, the module's resources are the list and a copy would drift. |
| `install-ci` | the canonical-artifact lint, as one script | A Domain's pre-commit hook and CI must run the same script, never two copies of a command list: `validate` (model and ontology), `refs`, `coverage`, `suppliers`, `notes`, a non-blocking `glossary`, the contract gate (`odcs.py check`, blocking on an error and skipping a repo with no `contracts/`), then the mechanical lints a command cannot see — a mapping identifying a version surrogate (`lint/surrogate-identity`, checked against the model's declared `scd.natural_key`), a partial identity, a declaration nothing reads, a concept-level `iri`. This repo carries it as `tools/ossie_lint.py` (`commands.ossie_lint`, 3.7s end to end), runs it from `.github/workflows/repo-checks.yml`, and ships `.githooks/pre-commit` that chains into a CI-bundle hook rather than setting `core.hooksPath`. Verified both ways: green on the repo, and one blocking finding when a mapping's identity was moved onto a version surrogate. Open for the plugin: an installer that chains per clone, so the hook is not opt-in; until then CI is the enforcement and the hook is a convenience. Classification coverage, cross-document identity agreement and the two `--check` generators stay in VD-7317 — they need a classification file the tool reads. |
| `generating-dbt-model` | gold-mart completion; `coverage` and the ontology mapping | A new or changed gold model is not done until the canonical document names it (`coverage`) and the ontology mapping for the concepts it populates is updated in the same intent. When the change moves a concept's identity — grain, SCD shape, a natural key replaced by a surrogate — the concept, its `CONTEXT.md` sentence and every mapping of it move together; a mapping that still resolves to a real field can still identify the wrong thing. Until the skill carries it, this repo's `workarounds` holds the rule. |
| `generating-dbt-model` | `layers.<x>.built_by` routing | `built_by` is now `dlt`, `dbt` or `custom`. A `custom` layer has no skill procedure, so the skill must not fall through to the dbt procedure for it; it should read the layer's `notes` and stop. |
| `onboarding` (plugin copy) | repo-map schema, template, its map tests, `templates/skills/dlt.md` and `templates/dbt/dbt_project.yml` | The schema and template carried in the plugin gain `orchestrators`, `sources.<name>.produces`, `built_by: custom` (with `notes` required for it and for a null `path`) and the `sqlfluff_lint` command; its `tests/test_maps.py` template gains the orchestrator↔source, shared-dataset `produces`, source↔resource and `runs`↔`PIPELINES` guards; `templates/skills/dlt.md` carries the same registration rule; the template `dbt_project.yml` drops the unused `analysis-paths`. A repo onboarded by the plugin copy must produce the same map shape and the same guards as this repo's `.agents/skills/onboarding/` templates. |

## Data contracts

The convention skills live in the reference Domain and the tooling is generic; these are the plugin gaps
derived from building and running it. Every row is tracked in VD-7139.

| Skill | Reference | Suggested change |
| --- | --- | --- |
| `generating-dbt-model` | gold-mart completion | A model change updates its contract and regenerates the generated keys in the same intent. A breaking shape change moves the contract's version. Today the reference Domain's `workarounds` holds the rule. |
| `generating-dlt-pipeline`, `add-or-update-source` | resource completion | A resource change updates its contract; the generated column hints are what keep the loader's column freeze meaningful. A dropped or retyped source column is a contract change, never schema evolution. |
| `verifying` | the contract gate | Run the contract check as part of verification, with `--relations` against the ephemeral warehouse, and record both results with the landed-table figures. |
| `install-ci` | the canonical-artifact lint | The bundle runs the contract check beside the canonical lint and skips cleanly in a repo with no contracts directory. The reference Domain's single lint already does both. |
| `onboarding` | the repo-map template and its map tests | The template and the map tests gain `data_platform` and `gold_layers`, so a repo onboarded by the plugin declares both before it writes a contract. Without them every contract names `custom` with the platform `unknown`. |
| `onboarding` | the contracts step | Seed both contract skills with their scripts and the vendored schema, declare the contracts directory in both maps, rebuild in full, reverse once without the force flag, write the review artifact, and carry the three contract rows in the `workarounds` template so a freshly onboarded repo inherits them. |

When the plugin lands, the canonical-artifacts and contract rows above collapse into one rule: a change reaches
code, model, ontology and contract in the same intent.

## Tracked in Linear

A row that becomes a Linear issue moves here; the issue holds the work and its acceptance criteria. Status as of 2026-10-22, mirrored from Linear.

| Issue | Owner | Skill or area | What it covers | Status |
| --- | --- | --- | --- | --- |
| VD-7137 | hemanta | repo-map schema; `dlt`, `onboarding` convention skills; the four plugin skills above | The map can record which pipeline lands each raw table (derived from the module, declared in `produces` once a dataset is shared) and what invokes each pipeline; `built_by` becomes `dlt`/`dbt`/`custom`. Implemented in this repo; the plugin rows are recorded above for triage. | Done in this repo |
| VD-6902 | hemanta | init | Retire the `init` skill and its `_shared/templates/agents-md-template.md`; onboarding replaces them. Studio's skill snapshot, `workflow.ts` maps and compatibility contract drop `init` with the plugin pointer bump; `artifact-kinds.md` points at onboarding. | Done |
| VD-6904 | hemanta | platform (data tools) | `summarize_data`, `profile_data`, `compare_data_profiles`, `load_tabular_to_ephemeral` and `visualize_data` read Parquet within their size bounds. | Done |
| VD-6905 | hemanta | platform (Studio runtime) | The first call after a condensation is rejected on DeepSeek thinking mode because `reasoning_content` is not passed back. | Todo |
| VD-6901 | Jason | install-ci | The shipped CI bundle carries `FAKE_WORLD` hooks, internal ticket IDs and a wrong intent-branch message into customer repos; a check keeps them out. Follow-ups: the plugin's `managed-constraints.txt` ticket IDs (VD-6939) and the Fabric live-E2E test step (VD-6940). | Done |
| VD-6910 | hemanta | platform (Studio runtime) | Studio loads the Domain repo's `AGENTS.md` and project skills (`load_project_skills: true`). | Done |
| VD-6912 | Trang | platform (evals); plugin fixtures | The eval provider mirrors Studio's persona, `soul_content` and project skills; the `v2-nyctaxi` fixture is re-vendored with the convention skills; the in-tree nyctaxi and project fixtures drop their `database:` vars and `../domain.duckdb` path; a capture regression eval checks the call budget, out-of-scope reads, repeated reads and credential probing. | In Review |
| VD-6914 | hemanta | this repo | Operator conventions are skills in `.agents/skills/`, not `.agents/rules/`. | Done |
| VD-6919 | Umesh | domain-modeling, designing, generating-dbt-model, generating-dlt-pipeline, shipping, planning, executing-the-plan; plugin layout | Build skills read the Domain's convention skills, `repo-map.json` and `test-map.json` instead of restating them: the ADR template, CONTEXT and design-record bars, audit columns, the `src_<connection>` default and PR body sections; artifact paths and the new-source footprint from `repo-map.json`; gates from `test-map.json`; the plugin root stated once. | Todo |
| VD-6920 | Pradip | generating-dbt-model, generating-dlt-pipeline, onboarding; platform duckdb_local | The duckdb_local and dlt platform facts: Arrow `TIMESTAMPTZ` and `timezone('UTC', col)`, `--full-refresh` after upstream change, `DLT_INGEST_LIMIT` bounds pages, the sandbox dbt command, no source `database:`, the `relations.sql` override, generic-test `arguments:`. | In Progress |
| VD-6921 | Pradip | generating-dlt-pipeline, add-or-update-source | File sources and custom connectors as source kinds, with `naming = "direct"` and the parquet normalizer load columns for file sources. | Todo |
| VD-6922 | Umesh | generating-semantic-model | Helper metrics for dbt Semantic Layer ratio metrics; the semantic YAML location from `repo-map.json`. | Canceled (superseded by VD-7139: the skill it changes is being retired) |
| VD-6924 | Umesh | planning, executing-the-plan, verifying, shipping | `plan.md` and `verify.md` written once per phase; base commands on the base commit; the Tier-1 dev dataset; verify figures from the landed table; the contract skip on duckdb_local; follow-up scope stays out of the PR; resume after a teardown autosave. | Todo |
| VD-6929 | Jason | install-ci | Deploy tracked paths only and install hooks safely in worktrees; run as a step of onboarding; ask for `VD_DOMAIN_SLUG`; `design_drift` accepts a `## Semantic Model` section. | Superseded by VD-7134 (tracked paths, worktree-safe hooks, onboarding step, domain slug and platform). `design_drift` `## Semantic Model` dropped as moot (VD-7139). |
| VD-6934 | Umesh | Build persona; capturing-requirements, designing, planning, shipping | Each stage stop prints its summary as a message, which stays in the transcript, then asks a short question naming the artifact and the decision. Today the whole approval content goes into the question and the card renders it as one paragraph. | Todo |
| VD-7134 | Jason | install-ci | Install and upgrade versioned Domain CI: pinned caller, `ci-config.yml`, test map, pre-commit hooks and `dependabot.yml` only; repeat runs inventory and ask before overwriting customer edits; CODEOWNERS block and opt-in branch protection; runs inside onboarding with its slug and platform. Absorbs VD-6929. | Todo |
| VD-7139 | hemanta | generating-semantic-model; semantic-model kind; verifying; generating-dbt-model; designing; planning; install-ci | Retire `generating-semantic-model` and the `semantic-model` kind: the canonical Ossie model (`logical-model/`, authored by this repo's `semantic-model` and validated by `validating-semantic-model`) is the source of truth, the dbt Semantic Layer is retired rather than exported, the `semantic_model` asset kind now denotes the Canonical Data Model, and the ontology is a new `ontology` kind. Removes the skill, playbook, kind and its `composition.order` slot, the dbt Semantic Layer time-spine templates (decision recorded), the eval cases/fixtures and the Studio suggestion/contract references; vacated gates move to `verifying` (Domain validation report), `generating-dbt-model` (canonical update, and the ontology mapping, in the same intent), `designing`/`planning` (logical-model contract) and `install-ci` (`validate`/`coverage`/`suppliers`). | Todo |
| VD-6923 | hemanta | platform (Studio cost meter) | Run cost charges cache reads at the full input price. | Done |

## Order

1. Ship the onboarding skill with its templates, and retire `init`. Nothing else depends on the content rules until the skills read them.
2. Change the skills that restate a rule to read it (`domain-modeling`, `designing`, `generating-dbt-model`, `generating-dlt-pipeline`, `shipping`), one at a time, each with its eval cases.
3. Add the new routes (`add-or-update-source` for custom sources, `generating-orchestration` for `duckdb_local`).
4. Update CI (`install-ci`, `adr_lint.py`, `design_drift.py`).

## VD-6872 journey findings (2026-10-15)

Two journeys replayed real Studio intents on this repo through to shipping (vibedata-data-engineering#797, branch `feature/vd-6872-simplify-ways-of-working`): the surcharge split and tip rate (transformation, 20 min, 160 LLM calls) and the HVFHV 2024-01 source (ingestion, 40 min, 171 LLM calls). Both shipped; each failed one judged criterion.

| Owner | Reference | Finding | Change | Status |
| --- | --- | --- | --- | --- |
| add-or-update-source | `agents/build.md` `## Sizing` | The ingestion run loaded `add-or-update-source` before `capturing-requirements`; it wrote nothing before the Requirement | None yet; watch in the next runs | not reproduced in the HVFHV run of 2026-10-16 (ea85380d), which loaded `capturing-requirements` first |
