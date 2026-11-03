# Base setup

What every onboarded repo has, so the first build intent does not spend its calls discovering the environment. It comes from how agents, the sandbox and the CI bundle work, not from the repo's code.

## Inherited DuckDB views

For DuckDB-local, check the untouched sandbox copy before any ingestion, `dbt build`, or other database write. This is an onboarding assessment, not an upload gate or a repair of the uploaded Domain database. A build can replace broken inherited views and hide the evidence.

1. Through the supported sandbox SQL tools (`lakehouse_query` with `target=ephemeral`), enumerate all non-internal views in the sandbox's own catalog: `SELECT schema_name, view_name FROM duckdb_views() WHERE database_name = current_database() AND NOT internal`. Include views outside the dbt project and views without tests. Record the sandbox catalog and that it is a renamed copy of the Domain database.
2. Attempt `SELECT * FROM "schema"."view" LIMIT 0` for each view, quoting identifiers correctly. This checks binding without fetching rows; it does not prove data correctness. Keep the check read-only: do not rewrite views, attach the old catalog to make them pass, or access the protected Domain file directly. Existing dbt data tests are not a substitute for checking every view.
3. Record totals checked, failed and unchecked, plus each failing `schema.view` and its missing catalog or other dependency, in this intent's verification record. Use bounded tool calls; external-file views may require metadata access. A timeout, unavailable tool, truncated inventory or previously modified sandbox makes the assessment incomplete, never a pass. Do not infer an untouched baseline from rebuilt views.
4. File failures as onboarding review findings, distinguishing missing catalogs from missing files/extensions or access failures. Report names and safe reasons, not raw SQL, credentials or filesystem paths. Continue the remaining onboarding work with the findings visible. Explain that sandbox changes do not repair the uploaded Domain database, so later Intents may inherit the same failures; recommend rebuilding a portable file outside this onboarding and creating a new Domain.

No user-defined views means the view check is not applicable; record that explicitly. It does not establish that tables or the rest of onboarding are valid.

## Empty Domain database

After the inherited-view check, inspect the sandbox for tables. When the Domain database has no tables, every Intent's sandbox (a copy of it) starts empty, and the base commands, data tests and dry run have nothing to read. Load it in this sandbox before the base commands: a sample load of every source (`DLT_INGEST_LIMIT`), then `dbt build`.

When that cannot be done, or is a lot of work (missing source credentials, very large sources, run scripts that fail), do not attempt it: write a proposal under `docs/proposal/` for seeding the Domain database (the sources, their size, the steps, what blocks it) and continue without data.

Either way the data stays in this sandbox: the Domain database is still empty for later Intents. Say so in the PR description.

## Base commands

Put these in `repo-map.json` `commands`, using the repo's own paths: `dbt_deps`, `dbt_parse`, `dbt_build`, `python_tests`, `python_lint`, plus the run scripts if the repo has them, one entry per CI check script an agent should run rather than read (for example `adr_lint` for `.github/scripts/adr_lint.py`), and `odcs_check` and `odcs_check_relations` once `data-contract` is seeded.

In the design phase, after the inherited-view check and before the inventory, run each once in the sandbox: dbt through the runtime wrapper with `--target dev`, after `dbt deps` when `packages.yml` exists. Record every result. A failure you cannot fix with a change from the two lists below is a review finding, `platform` or `bug`.

## Pipelines and their runner

`repo-map.json` `orchestrators` names what starts the pipelines, and `sources` names the pipelines themselves. Both are needed because dbt's artifact covers everything below the raw layer and stops there: without `orchestrators`, nothing in the repo says what re-runs a raw table, and a runner outside the repo leaves no trace at all.

- One entry per runner: `kind` (`python`, `airflow`, `fabric`, `custom`), `runs` (the source names it starts), and either `path` for a runner in the repo or `location` for one outside it. `runs` is a set; the runner's own code holds the order.
- A source declares `produces` (its table names) only once a second source shares its `dataset`. A single owner's module already holds the list, and a copy would drift.
- `built_by` is `dlt`, `dbt` or `custom`. `custom` covers a stack no skill has a procedure for, and must say what builds it in `notes`. A runner that starts the dlt pipelines is an orchestrator, never a layer builder; one that also builds dbt still lists only the sources it starts.
- When a brownfield repo has pipelines and no `orchestrators`, ask one grilling question: is anything outside the repo starting them? Record the answer as a `location` entry, or as a `python` entry whose `path` is the repo's own script.
- When a source's tables cannot be read off its module — a producer outside the repo — ask which tables it lands and record them in `produces`. Without that, a table has no pipeline to trace back to.

## Changes the build needs

The only edits to existing files. List each in the PR description.

| File | Change | Why |
| --- | --- | --- |
| `dbt_project.yml` | `profile: "{{ env_var('DBT_PROFILE_NAME', '<current name>') }}"` | The sandbox wrapper selects its profile through `DBT_PROFILE_NAME`; a fixed name means no dbt command runs in the sandbox. Local and CI runs keep the current name. |
| `_sources.yml` (every sources file) | Remove each source's `database:` and any var that feeds it or its `schema:`; give the schema as a literal. Remove the then-unused vars from `dbt_project.yml`. | The Studio sandbox is a byte copy of the Domain file under another name, so its catalog differs and a source that names one fails with `Catalog ... does not exist`. Schemas carry over unchanged. |
| `profiles.yml` (the repo's own, used locally and to seed the Domain) | One `dev` target whose `path` is `"{{ env_var('VD_EPHM_DUCKDB_LOCAL_PATH') }}"`, no literal path; run scripts set the variable. | Matches the runtime profile the sandbox uses, so local runs and Intents build the same way; Studio ignores this file in an Intent. |
| `dbt_project.yml` | Under `models:` and `seeds:`, `dbt_project_evaluator: +enabled: "{{ var('dbt_project_evaluator_enabled', false) }}"` | Keeps the evaluator out of normal builds; the CI quality workflow and `verifying` switch it on. Only with the `packages.yml` entry below. |

## Behaviour-free cleanups

Make the base parse clean, so agents have no warnings to chase. Prove each change leaves the test list and the compiled SQL of every test identical (`dbt ls --resource-type test` and `dbt compile --select resource_type:test`, before and after), and list it in the PR.

- Generic-test arguments nested under `arguments:` (`- relationships: {arguments: {to: ..., field: ...}}`), which removes `MissingArgumentsPropertyInGenericTestDeprecation`.
- `dbt_project.yml` config paths that apply to no resource (for example a `snapshots:` block with no snapshots) removed.

Any other warning the parse shows is a `style` finding.

## Files onboarding adds

Only when the repo has none. When the repo has its own that conflicts, leave it and file the difference.

| File | Content |
| --- | --- |
| `macros/relations.sql` (dbt) | Copy [templates/dbt/relations.sql](../templates/dbt/relations.sql) into the project's macro path. It overrides `ref()` and `source()` to render `schema.table`. If the project already overrides either macro, merge the `.include(database=False)` into it and say so in the PR. | dbt-duckdb writes the catalog name into every view it stores; in the renamed sandbox copy those views fail with `Catalog ... does not exist`. Part of setting up the dbt models, not a review finding. |
| `packages.yml` entry | `dbt-labs/dbt_project_evaluator`, `version: [">=1.1.0", "<2.0.0"]`, added to an existing `packages.yml` or a new one. The CI quality workflow builds it. |
| `tests/test_adr_links.py` | Copy [templates/tests/test_adr_links.py](../templates/tests/test_adr_links.py): every design record that cites an ADR is in that ADR's `## Affected designs`, and every record listed there exists and cites it. `adr_lint` checks only numbering and dangling citations. |
| `tests/test_maps.py` | Every map path exists; every source is registered; every source is named by an orchestrator; every dataset with more than one producer declares `produces`; every `test-map.json` dbt selector resolves to a test. Its dbt calls name the repo's own profile (`--profiles-dir <dbt project> --profile <name>`) and run `dbt deps` once when `dbt_packages/` is missing, so they pass locally, in the sandbox and in CI. |
| `ruff.toml` | `[lint] select = ["E4", "E7", "E9", "F"]`, and `extend-exclude` with any paths the repo's documented lint command or CI already excludes (for example `--extend-exclude ingestion/sources`). Ruff's default selection changes between releases. Fix nothing it reports; file the findings as `style`. |
| `.gitignore` lines | Appended to the existing `.gitignore` (or a new one), only the lines missing from [`gitignore-fragment`](../templates/repo/gitignore-fragment), with the repo's own dlt preview path. If `.user.yml` files are tracked, `git rm --cached` them. |

## Repo checks

The map tests and the ADR link test are the Domain's own checks; the CI bundle does not run them. Ask the user where they run, as one grilling question. Recommended: a repo workflow, [templates/repo/repo-checks.yml](../templates/repo/repo-checks.yml) at `.github/workflows/repo-checks.yml`, which installs `requirements-dev.txt` and runs `python_tests` on every pull request. A pre-commit hook is the other option; if the user wants one, say that setting `core.hooksPath` stops git reading `.git/hooks`, where the CI bundle installs its own hooks, so the repo hook must call them.

## Layers, roles and the contract boundary

The model is the plugin's semantic ownership design; onboarding applies it and invents none of it.

- **Layers are the Domain's, roles are the rule.** `repo-map.json` `layers` declares every layer with `schema`, `built_by`, `path` and an explicit `role`: `input` (landed by a loader), `internal` (built for the Domain's own use) or `boundary` (read by a consumer outside the repo). Names come from the inventory and the user; medallion names (`bronze`, `silver`, `gold`) are only the default for a greenfield Domain, never a rule, so a brownfield repo keeps the names it has. Write no `gold_layers`: it is the legacy way to say `boundary`, and a second declaration beside `role` can only drift. The role definitions are the plugin's `layer-roles.md`.
- **The contract boundary is `input` and `boundary` layers** (ADR-0225). An `internal` layer owes no contract, so a staging view built over a loader relation has none; `contract_layers` (an optional `repo-map.json` key naming the layers that owe a contract) overrides this and is set only when the user asks. A boundary relation is a candidate for the semantic layer; an internal one never is.
- **A contract may come before its table** with `status: proposed`: `check` shape-checks it, `generate` writes no dbt keys for it (a proposed input still gets its dlt `COLUMNS`), and it becomes `active` once the table is built. Adopting an existing table writes it `active`.
- **Grain comes from keys, not prose.** A contract's `primaryKey` states the grain, and a star member's contract carries no `dataGranularityDescription` and no column descriptions: the Ossie dataset and fields own them, and `generate` copies them into dbt. A non-star relation states its grain by a `primaryKey`, or by one `dataGranularityDescription` sentence where it has no key or the key would mislead (a snapshot, a file with no identifier). Verify a candidate key is unique, and never null, on the landed data before declaring it; a relation with neither key nor sentence raises `contract/no-grain` and a review question, and nothing invents the answer.
- **Bespoke boundary tables are routed, not modelled.** `semantic-model` owns the routing table: a rollup, filter or window of a star's rows is an aggregate source; a filter on an existing measure is a filtered metric; a different population or method (a `HAVING` floor, a lossy join, an unpivot) is listed in `semantic_exclusions` with its reason and keeps its contract; a new business process is a new star. A standalone Ossie document is retired, and a dimension copied into several documents names its owner with `conformed_from`.
- **`semantic_exclusions: [{relation, reason}]` sits in the map beside the layers.** The gates read no Domain file, so the lint passes the list as arguments (below).
- **No MetricFlow and no dbt Semantic Layer.** The Ossie documents plus the ontology are the semantic layer. A repo that has `_semantic.yml` files is a review finding to delete them once the Ossie documents carry their metrics.

## Semantic layer, ontology and contracts

Every repo gets the `ontology` and `validating-ontology` skills, and an `ontology/` directory registered in `repo-map.json` and `test-map.json`: the ontology renders the confirmed vocabulary as concepts and relationships, and it is the only artifact that states an object is the same object across the Ossie documents. Its validation is its own step. Mappings are written only for Ossie documents that exist, so a repo with no boundary marts gets the ontology and no mapping, and its `repo-map.json` still declares both artifact paths. The template `test-map.json` registers the `ontology` module with no command: `ossie.py validate` refuses an empty directory (`cli/no-files`), so the first concept adds the module's `structural` command (`validate`, `refs` and `glossary` from the gates table).

The `semantic-model` and `validating-semantic-model` skills belong to a repo with boundary marts. They are seeded when `logical-model/` is registered; a repo with no boundary mart yet gets neither skill, because a declared path that does not exist fails the map tests. It still gets `semantic-model/scripts/` (the checker `ossie.py` and its vendored Ossie schemas, no `SKILL.md`), because the ontology validates through it. `data-contract` and `validating-data-contract` are always seeded, with `data-contract/scripts/` (`odcs.py` and its vendored schema), and `contracts/` is declared as `artifact_paths.data_contract` and as a module in both maps.

Seed each skill with its `scripts/`, `references/` and `examples/` from the plugin (`plugins/vibedata-data-engineering/skills/<name>/`, delivered by VD-7139) or by copying the reference Domain's `.agents/skills/`, which tracks the plugin's text. Take the directory whole: `semantic-model/scripts/` holds the checker and its vendored Ossie schemas, and the dlt `COLUMNS` and dbt keys are only as current as `odcs.py`. The map declares `data_platform` before any contract is written, because `servers[].type` in every contract derives from it.

The loader's columns are derived, never assumed. A repo's dlt version decides which of them it adds, so ask the catalog which relations the loader created, take the layer from the map's `layers[].built_by`, and read the dbt model's SQL to see whether a model selects a `_dlt_*` column through. A contract on a relation the loader creates declares none of them; one on a dbt output that propagates one must declare it, because the enforced contract rejects an undeclared output column.

A repo that already has contracts keeps them. Adopting existing tables is: rebuild with `--full-refresh`, run `odcs.py reverse` once with no flag (it leaves a contract that exists alone; `--force` rewrites every authored version and description and is only for a deliberate rewrite), triage its findings, run `generate`, then `check`. The findings are the review artifact of type `contracts` at `artifact_paths.review`, and the contracts stay partial until an engineer triages them: say so in that artifact and in the PR description. Two questions the reverse pass cannot answer are findings, not content: a relation whose key and descriptions say nothing about its grain, and a rule no existing test expresses. Both go to the review artifact as questions.

### The gates, as commands

Record each command and its exit code in this intent's verification. `<boundary root>` is a boundary layer's `path`, one per layer with that role.

| Artifact | Command | Proves |
| --- | --- | --- |
| Ossie documents | `ossie.py validate <model-dir>` | Schema, `conformed_from`, cross-document drift |
| | `ossie.py coverage <model-dir> <boundary root>... --exclude <schema.table>...` | Every boundary dbt model is named by a dataset or listed in `semantic_exclusions` (one `--exclude` per entry) |
| | `ossie.py suppliers <model-dir>`, `ossie.py notes <model-dir> <tests-dir> <adr-dir>` | Every declared field is supplied; every note pointer resolves |
| | `ossie.py generate-tests <model-dir> <tests-dir> --check` | The generated singular tests are current (run without `--check` to write them) |
| | `ossie.py bindings <model-dir> <manifest.json>` | After a build: each aggregate binding agrees with the compiled SQL |
| Ontology | `ossie.py validate <ontology-dir>`, `refs <ontology-dir> <model-dir>`, `glossary <ontology-dir> CONTEXT.md` | Structure, mapping refs, term names |
| Contracts | `odcs.py check` | Shape, agreement with the map and the Ossie documents, `boundary/*`, `contract/no-grain`, `contract/undescribed`, `generated/stale`; after a build also `contract/active-unbuilt` |
| | `odcs.py generate` | Writes the dbt keys and descriptions and the dlt `COLUMNS` (never by hand) |
| | `odcs.py diff <base-ref>`, `check --relations`, `profile` | The version moved far enough; contract against the built relations; every data claim against the data |

Each `ossie.py` and `odcs.py` command above is run from the repo root as `python3 .agents/skills/<skill>/scripts/<script>.py`; the commands the repo gates on belong in `repo-map.json` `commands` and `test-map.json`.

## Convention skills

Copy these from [templates/skills/](../templates/skills/) as they are, each `<name>.md` becoming `.agents/skills/<name>/SKILL.md` (the templates are not named `SKILL.md`, so the agent does not load them as skills); only examples may change to the repo's own. When the repo's confirmed inventory says otherwise (its own commit format, for example), the inventory wins for that line.

| Skill | What it holds |
| --- | --- |
| `context` | What goes in `CONTEXT.md` and what does not. |
| `design-records` | What goes in a design record: decisions with sources, consumers from lineage; no evidence (that is for verification). |
| `adr` | The three tests, what is not an ADR, content, supersession. |
| `git-and-prs` | Commit format, staging named files (never `git add .`), the four PR-body sections the `shipping` skill fills. |
| `workarounds` | The open platform gaps, each with what removes it: the sandbox dbt command (and never opening `profiles.yml`), `plan.md` and `verify.md` written once per phase, large files changed by script, verify from the landed table and saved profile, the Tier-1 dev dataset, sample loads that land whole pages. |

Write these into the repo's own convention skills beside its conventions:

| Skill | Rule |
| --- | --- |
| `dlt` | Sample loads (`DLT_INGEST_LIMIT`) while a pipeline is written; one full load at most per intent, at the end, only when the requirement asks for loaded data. `replace` is proven with two sample loads (the limit's row count and one load package), never a second full load. |
| `dlt` | Profile a remote source file once per intent into `.agents_tmp/<source>-profile.json`, and take every later figure from it. |
| `dlt` | To see whether a source exists, read `repo-map.json` `sources`; query the lakehouse only for data questions. |
| `dlt` | A new source joins its runner's `orchestrators.<name>.runs`; a dataset with more than one producing pipeline declares `produces` on each. |
| `dbt-models` | Sources name a schema and tables, never a database, and no var feeds either. |
| `dlt` | Mirror the repo's existing source of the same kind for batching and file handling. |
| `dlt` | A pipeline's `columns=` hint is the generated `COLUMNS` from `ingestion/contracts.py` (`from contracts import COLUMNS`, `columns=COLUMNS[<resource>]`), never written by hand. |
| `adr` | Check citations with the `adr_lint` command (or the repo's equivalent) and the two-way links with `tests/test_adr_links.py`; run them, do not read the scripts. |
| `dbt-models` | dlt lands naive Arrow timestamps as `TIMESTAMPTZ` and the sandbox session is not UTC: staging converts every dlt-loaded timestamp with `timezone('UTC', col)`. |
| `dbt-testing` | A left join on a derived key gets a singular test that every left row finds its match, or that the unmatched rows are the expected ones. |
| `dbt-testing` | Rebuilt values are compared at the cent for money and at a stated tolerance otherwise, never by hashing raw doubles: DuckDB float aggregation is not reproducible bit for bit. |

## Agent entry points

- `AGENTS.md` starts with a Startup section: before a task, invoke the convention skill for the task (`dlt` to add a source, `dbt-models` for a model); do not read README, CONTRIBUTING or other human documents for a pipeline or model change. Read `repo-map.json` whole, once: its `modules`, `artifact_paths` and `sources` are the index of the repo, so do not list directories or read it again in parts.
- The Startup section also says not to read the installed source of dbt, dlt or any other library: the repo's own models, pipelines and tests are the reference, and the library's documentation covers the rest. Agents otherwise read dbt's package source to answer questions such as how a unit test overrides a var.
- Material that is not for build tasks (setup or maintenance notes, demo or evaluation prompts, answer keys) is declared in `key_directories` and `notes_for_agents` as not read. Prompts used to test agents are an answer key: file a `gap` finding recommending a move into the maintenance folder.
- Artifact paths: no `## Artifact Paths` table in `AGENTS.md`. The plugin has no default locations, so `repo-map.json` `artifact_paths` declares every class it writes: `requirement`, `plan`, `verification` and `case_record` (each with the `{intent}` name the plugin gives an intent), `design_record_model`, `design_record_pipeline` and `design_record_area`. A repo without them makes the build agent stop and ask for onboarding.
- `repo-map.json` `notes_for_agents` has at least: `startup`; `new_source` (a new source mirrors an existing `sources` entry, creates every artifact it lists, and joins its runner's `orchestrators.<name>.runs`); `reviews_and_proposals`; and, when pipelines use the Vibedata dlt package, the environment variables they need outside Studio.

## Checks for the onboarding review

File each as a finding when it fails; change nothing.

| Check | Kind when it fails |
| --- | --- |
| Parquet or Arrow sources stamp `_dlt_load_id` and `_dlt_id` (`[normalize.parquet_normalizer] add_dlt_load_id`, `add_dlt_id`) | `platform` |
| Staging reads an input relation only through `source()` | `platform` |
| Staging converts dlt-loaded timestamps to UTC | `bug` if a key or join depends on them, else `convention` |
| Run scripts install dbt packages before building | `bug` |
| `.sqlfluff` (or the SQL lint config) resolves its profile and project paths | `gap` |

## Verify

The base commands pass, or each failure is a filed finding. `tests/test_maps.py` passes in the sandbox. The gates in [the gates table](#the-gates-as-commands) pass against what onboarding wrote, or each failure is a finding. For DuckDB-local, check every user-defined view and run the data tests on a renamed copy of the built database, without rebuilding it. Keep this post-build portability result separate from the inherited-view assessment: neither a successful rebuild nor a passing renamed-copy check clears a finding about the uploaded Domain database.
