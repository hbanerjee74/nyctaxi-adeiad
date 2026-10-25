# ODCS data contracts — implementation plan

**Goal:** an ODCS `v3.2.0` contract for every relation the maps declare, authored first and enforced by generated dbt and dlt tests, with the onboarding path declaring only what it can ground and every doubt queued as a review finding.

**Architecture:** vendor the pinned schema beside a new convention skill; one tool with four verbs (`check`, `check --relations`, `reverse`, `generate`); the contracts are the authored artifact and the dbt and dlt enforcement is generated into the files those tools already read. The automated half proves schema and structure; the review skill proves quality, completeness and correctness — the split below is deliberate and each half must stay out of the other's territory.

**Spec:** [`docs/requirement/odcs-data-contracts.md`](../requirement/odcs-data-contracts.md). Product decision: `accelerate-data/studio` `docs/adr/0222-...` beside `0220-ossie-canonical-artifacts-are-the-semantic-source-of-truth.md`. The plugin port is tracked in a Linear issue linked to VD-7139 and is **not** part of this plan.

## Where each check runs

| Check | Owner | Class |
| --- | --- | --- |
| ODCS schema validity against the vendored file | `odcs.py check` | structure |
| one contract per relation, no orphans, `_dlt_*` excluded | `odcs.py check` | structure |
| no present-but-empty section, no key outside the standard | `odcs.py check` | structure |
| `servers` matches the platform declaration | `odcs.py check` | structure |
| gold agreement, declared fields only | `odcs.py check` | structure |
| generated dbt keys and dlt hints are current | `odcs.py check` | structure |
| the built relation matches the contract | `odcs.py check --relations` | structure |
| a model or source that drifts fails its build | dbt `contract: enforced`, dlt `columns: freeze` | structure |
| the grain is stated and true; `required` is honest; a rule encodes the real business answer; a declared change is actually breaking; a gold contract means what its document means; every finding is either answered or visibly open | `validating-data-contract` | judgement |
| no vacuous rule, no rule contradicting an ADR, no description that says nothing | `validating-data-contract` | judgement |

Nothing in the left column may be pushed into the review ("the agent will notice"), and nothing in the right column may be automated into a pass/fail the tool cannot actually judge.

## Global constraints

- ODCS `v3.2.0`, JSON schema pinned to an upstream commit. Never edit a vendored file. Where the published standard and the JSON schema differ, **the standard wins** — `logicalTypeOptions` is that case.
- Skill text is generic: artifact locations resolve from `repo-map.json`; no repo path, layer name or domain term inside a skill.
- The contract is the only hand-written contract artifact. Generated keys are never hand-edited, and `check` proves they are current.
- No change to a model's SQL, a seed, or a macro. The enforcement the contracts generate is the only transformation-side change.
- Commands: `python3 -m pytest tests/test_odcs.py tests/test_odcs_contracts.py -q`, `python3 -m pytest tests/test_maps.py tests/test_adr_links.py -q`, `python3 tools/ossie_lint.py`, `cd transformation && dbt build`.

### Findings that shape the tasks — each verified, do not re-derive

| Finding | Consequence |
| --- | --- |
| dbt rejects two properties entries for one model: *"dbt found two schema.yml entries for the same resource named m"* | A generated properties file per model is impossible. The generator **augments** the existing layer file. |
| `contract: enforced` fails when an output column is undeclared: *"missing in contract"* | The generator adds one `columns[]` entry per contract property. |
| dlt `columns=` hints with `columns: freeze` reject an undeclared column: *"Contract on `columns` with `contract_mode=freeze` is violated"* | The dlt half needs only a generated hints module. |
| dbt contracts are model-only | The 4 seeds get generated tests and `check --relations`; the build cannot hold them. |
| `NON_GOLD_LAYERS` names `staging`, `intermediate` and `seeds`, so `gold/undeclared` infers the gold layers by exclusion | Another Domain may name its layers differently. Task 11 declares the gold layers in the map instead, and the tuple goes. |
| `servers[].type` is a 44-value enum; `duckdb` requires `database`; `motherduck` and `fabric_*` are absent | `duckdb_local` and `motherduck` → `duckdb`; `bigquery`/`databricks`/`redshift`/`snowflake` → native; `fabric_lakehouse`/`fabric_warehouse` → `custom` + `customProperties`. |
| `quality` has no root-level key; it nests in a `schema[]` element and on a property | Layout is `schema: [{name, properties, relationships, quality}]`. |
| `DataQuality` needs `type`; `library` needs `metric` ∈ {nullValues, missingValues, invalidValues, duplicateValues, rowCount} plus one operator; `sql` needs `query` | The five translations in Task 5. |
| `logicalTypeOptions` is an open object in the schema, but the docs define `timezone` and `defaultTimezone` | `DateTimeTz` carries `{timezone: true}`; the docs win. |
| `physicalType` is a documented optional field — "the physical element data type in the data source" — and the standard names it as the carrier for source-specific types | Written on every property; it is also the only home for `DECIMAL(p,s)` precision. |
| The canonical model is curated: 149 declared fields across 17 datasets against 541 gold columns; a dataset names its table as `source: <schema>.<table>` | Gold agreement compares declared fields only. |
| The Domain has **no** `verifying` skill — verification is a plugin skill | The gate lands in `odcs.py` + `ossie_lint.py`, and the plugin's `verifying` gap is a `skill-changes` row, not a file here. |
| The existing test set is exactly four generic kinds and 13 singular tests: `not_null` 62, `unique` 44, `relationships` 11, `accepted_values` 6 | Task 5's mapping is complete at five translations; the before/after count is the proof. |
| The built warehouse at `studio/data/duckdb/74dd3bba-…/nyc_taxi.duckdb` predates the current models | Task 4 rebuilds from a copy of it; a stale catalog produces a wrong contract. |

Scope: **93 relations** — 63 dbt models, 4 seeds, 26 dlt-loaded raw tables across ten declared schemas.

## Review focus

1. A contract that states `required: true` the data does not support — the reverse pass must never promote a nullable column.
2. A quality rule that passes because it is vacuous, or that encodes a filter the mart does not have.
3. A generated key hand-edited in a properties file — `check` must fail it, not regenerate over it silently.
4. A gold contract that disagrees with its canonical document on a declared field — must name both sides.
5. A review finding that reads as a judgement rather than a question the triager can answer.

---

### Task 1: Vendor the ODCS schema

**Files:** Create `.agents/skills/data-contract/scripts/odcs_vendor/odcs-json-schema-v3.2.0.json`, `.../odcs_vendor/README.md`; Test `tests/test_odcs.py`

**Interfaces:** `odcs.py._schema()` returns the parsed schema, resolved from the vendored file only.

- [ ] **Step 1: Write the failing test** — `check` on a directory holding one minimal valid contract resolves the schema with no network.
- [ ] **Step 2: Run it — expect a failure naming the missing vendored file.**
- [ ] **Step 3: Vendor the file** at the pinned commit; record the commit and upstream URL in the README.
- [ ] **Step 4: Re-run the test — passes.**
- [ ] **Step 5: Commit** `chore: vendor the ODCS 3.2.0 schema beside the contract skill`.

### Task 2: `odcs.py check` — the structural gate

**Files:** Create `.agents/skills/data-contract/scripts/odcs.py`; Test `tests/test_odcs.py`

**Interfaces:** `check` prints `[{severity, code, message}]` and exits 1 on any error, with `--root` to point it at another tree. Codes owned here: `schema/invalid`, `contract/missing`, `contract/orphan`, `contract/empty-section`, `contract/no-grain` (warning, exit 0), `contract/unconfigured`, `gold/divergent`, `gold/omits-declared`, `gold/undeclared`.

**Scope split, ruled during pre-flight.** The codes that need another task's output move to the task that produces it, so no task's tests wait on three others: `generated/stale` joins Task 3 (one computation, one owner), and `relations/mismatch`, `relations/no-catalog` and `servers/mismatch` become Task 2b, after Tasks 3, 4 and 11. `contract/unknown-key` and `options/undocumented` are dropped: the vendored schema is closed on root keys and constrains `logicalTypeOptions` per logical type, so both would duplicate `schema/invalid`.

- [ ] **Step 1: Write the failing tests, one per code** — including a gold contract that omits a field its document declares (the empty-promise case), a repo whose map declares no `artifact_paths.data_contract`, a gold contract whose table no document declares, a gold contract whose declared field's logical type diverges, a `DateTimeTz` field missing its timezone option, `--relations` with no catalog, and a contract with no `dataGranularityDescription` that must warn and still exit 0.
- [ ] **Step 2: Run them — the failures and the warning case.**
- [ ] **Step 3: Implement.** Resolve every location from `repo-map.json` (`artifact_paths.data_contract`, `layers`, `logical_model`, the `_dlt_` exclusion). Identify a contract's relation from its path — `contracts/{schema}/{table}.odcs.yaml` — and confirm it matches `schema[].name`. Read the relation set from the contracts for the file-only mode and from the catalog for `--relations`. Resolve a gold contract's document through `dataset.source = <schema>.<table>`, compare **only declared fields**, and require every one of them to be present. Do not re-implement the schema's option rules: the vendored v3.2.0 schema already constrains `logicalTypeOptions` per logical type (verified: `timeZone` is rejected, `timezone` accepted), so an allow-list here would be a second copy that drifts on a re-pin.
- [ ] **Step 4: Run the tests and the warning case — pass.**
- [ ] **Step 5: Commit** `feat: gate the data contracts — schema, coverage, gold agreement`.
- [x] Done: 14 tests, suite 218.

### Task 3: `odcs.py generate` — dbt keys and dlt hints

**Files:** Modify `.agents/skills/data-contract/scripts/odcs.py`; Create `ingestion/contracts.py` (generated); Modify the six model properties files (owned keys only); Test `tests/test_odcs.py`

**Interfaces:** Also owns `check`'s `generated/stale`: `generate` computes the owned keys and `check` diffs them against the files, one computation with no second copy. For each contracted dbt model: `contract: {enforced: true}` at model level, `data_type` on every column entry, adding an entry where one is missing, never touching `description`, `unit_tests` or any key it does not own. For a seed: generated `data_tests` in its `columns[]` and nothing else. For dlt: `COLUMNS: dict[table, dict[column, dict]]`.

- [ ] **Step 1: Write the failing test** — generate over a two-model fixture: `contract` and a `data_type` per column appear, an undeclared column gains an entry, and the fixture's hand-written `description` is byte-identical afterwards.
- [ ] **Step 2: Run it — fails.**
- [ ] **Step 3: Implement.** Emit owned keys only; preserve ordering and every other key. Refuse to run when a contract's `servers` disagrees with the map.
- [ ] **Step 4: Run the test, then `dbt parse` — both pass.**
- [ ] **Step 5: Commit** `feat: generate dbt contract keys and dlt column hints from the contracts`.

### Task 4: Rebuild the warehouse and draft all 93 contracts

**Files:** Create `contracts/{schema}/{table}.odcs.yaml` ×93; Test the gate over the real tree

**Interfaces:** `reverse <catalog>` writes a draft per relation with grounded fields only.

- [ ] **Step 1: Rebuild.** Copy the studio warehouse in as `domain.duckdb`, then `python3 orchestration/run_transform.py`. Record the exit code; do not proceed on a red build.
- [ ] **Step 2: Write the failing test** — a fixture catalog with one nullable, undescribed column produces a contract with no `quality`, no `primaryKey`, no `required: true`, and validates.
- [ ] **Step 3: Implement `reverse`.** Columns and types from the catalog; `logicalType` from the canonical model's field `datatype` where declared, reduced onto the enum, from the physical type otherwise; `logicalTypeOptions: {timezone: true}` for `DateTimeTz`; `physicalType` on every property; `schema[].dataGranularityDescription` from an existing model, column or dataset description, and a review finding where none exists rather than an invented sentence; `required` only where physically `NOT NULL`; `primaryKey`/`unique` only where a `unique` test exists; `relationships` only from `relationships` tests; `description` only from an existing description; `quality` only from an existing test (Task 5); `servers` from the platform declaration; `authoritativeDefinitions` to the canonical document for gold. Mint `id` once and never regenerate it — a re-run reproduces the same file byte for byte.
- [ ] **Step 4: Run `reverse`, then `check`** — zero errors, and a non-zero count of review findings (Task 7).
- [ ] **Step 5: Commit** `feat: declare a contract for every relation in the Domain`.

### Task 5: Move the quality rules into the contracts

**Files:** Modify the six model properties files (their `tests:` lists move out) and `contracts/**`; Test `dbt build`

**Interfaces:** `unique` → `{type: library, metric: duplicateValues, mustBe: 0}`; `not_null` → `{type: library, metric: nullValues, mustBe: 0}`; `accepted_values` → `{type: library, metric: invalidValues, arguments: {valid_values: [...]}, mustBe: 0}`; `relationships` → the property's `relationships[]`; a singular test → `{type: sql, query: "select count(*) from (<test sql>)"}` with `mustBe: 0`.

- [ ] **Step 1: Write the failing test** — each of the five translations produces the expected rule, and `generate` then emits a `tests:` list byte-identical to the one removed.
- [ ] **Step 2: Run it — fails.**
- [ ] **Step 3: Implement both directions**, and delete the `tests:` lists from the properties files in the same commit so no rule is declared twice.
- [ ] **Step 4: Run the test, then `dbt build` — the same test count (62 / 44 / 11 / 6 / 13), all green.**
- [ ] **Step 5: Commit** `refactor: the contracts own the quality rules, dbt tests are generated from them`.

### Task 6: Wire the dlt enforcement

**Files:** Modify `ingestion/{tlc,ops,mdm}_pipeline.py`; Test `tests/test_odcs_contracts.py`

**Interfaces:** Each resource calls `apply_hints(columns=COLUMNS[table], schema_contract=CONTRACT)`; `CONTRACT` stays `{"columns": "freeze", "tables": "evolve", "data_type": "freeze"}`.

- [ ] **Step 1: Write the failing test** — a run yielding an undeclared column raises the freeze violation; a run yielding exactly `COLUMNS` succeeds.
- [ ] **Step 2: Run it — fails.**
- [ ] **Step 3: Wire the hints** from `ingestion/contracts.py`; never inline a column list in a pipeline.
- [ ] **Step 4: Run the test and one real sample load — both pass.**
- [ ] **Step 5: Commit** `feat: the ingest pipelines freeze against their contracts`.

### Task 7: The review artifact and its triage rules

**Files:** Create `docs/review/2026-10-24-contracts-nyc-taxi.md`; the format is defined by Task 8's skill

**Interfaces:** Each finding carries relation, table or column, the doubt, the question that settles it, and the evidence already gathered.

- [ ] **Step 1: Have `reverse` emit findings** for six doubt classes: no grain statement; an undescribed table or column; a nullable column with no evidence either way; a candidate key that repeats in the data; an enum-shaped column whose value set may be open; a column that looks like a foreign key with no `relationships` test. Nothing settled becomes a finding.
- [ ] **Step 2: Write the artifact** with the counts, one section per class, every finding answerable from data or business.
- [ ] **Step 3: Check it** — unique per relation+column+class, and no finding names a field the contract does not declare.
- [ ] **Step 4: Commit** `docs: queue the contract questions the reverse pass could not settle`.

### Task 8: The `data-contract` skill — under `writing-skills`

**Files:** Create `.agents/skills/data-contract/SKILL.md`; Modify `AGENTS.md` (skill index); Test the scenario transcript below

**REQUIRED BACKGROUND:** the `writing-skills` skill. No skill text until the baseline is recorded and kept. One skill at a time — Task 9 does not start until this one is verified.

- [ ] **Step 0: RED — baseline.** Dispatch a subagent to "add a `tip_is_captured` flag to `dim_payment_method` and ship it", using the repo as it stands with no `data-contract` skill. Record verbatim how it fails: edits the SQL and the properties file, writes no contract, never regenerates, and if told "the tests enforce the contract" hand-writes a dbt test instead of a `quality` rule.
- [ ] **Step 1: Micro-test the wording** if the runtime allows single-shot calls: the scenario prompt against a no-guidance control, 5+ reps, every flagged output read manually. If it does not, say so and rely on Step 3's rerun.
- [ ] **Step 2: GREEN — write the minimal skill** that addresses exactly those failures. Description is triggers only — a new or changed relation, a quality expectation, a breaking shape change, adoption of an existing repo — never a summary of the workflow. Body covers the forward order (profile → contract → generate → code), the onboarding order (reverse → review → triage), the owned-versus-generated split, what may never be invented, version bumping, the no-empty-section rule, the review finding format, and that the published standard wins over the JSON schema.
- [ ] **Step 3: Re-run the Step 0 scenario** with the skill present. It must write the contract first, run `generate`, and finish with `check --relations`; any other order is a fail, not a pass.
- [ ] **Step 4: REFACTOR.** Record each new rationalization verbatim, add the counter that kills it, add a red-flags list, and re-run until it complies twice in a row.
- [ ] **Step 5: Read it end to end** and remove any repo-specific path or term; confirm every location resolves from `repo-map.json`.
- [ ] **Step 6: Commit** `docs: add the data-contract skill`.

### Task 9: The `validating-data-contract` skill — under `writing-skills`

**Files:** Create `.agents/skills/validating-data-contract/SKILL.md`; Modify `AGENTS.md`; Test the scenario transcript

**Interfaces:** It owns judgement only — quality, completeness, correctness — and never re-runs what `check` already proves. Every item must be one a script cannot decide.

- [ ] **Step 0: RED — baseline.** Dispatch a subagent to review three contracts against their models: one with a stated grain that is wrong, one with `required: true` on a mostly-null column, one whose rule encodes a narrower population than its ADR. Record verbatim which it misses and why — the expected baseline is that it re-reports what `check` prints and approves the rest.
- [ ] **Step 1: Micro-test the wording** as in Task 8, Step 1.
- [ ] **Step 2: GREEN — write the minimal skill** that catches those three. Items: is the grain stated and true; is `required` honest against the profile; does each rule encode the standing business answer rather than a convenient filter; **does the contract promise anything at all** — the one question no structural check can ask on a relation with no canonical document; is a declared change actually breaking for a consumer; does a gold contract mean what its document means, not merely resolve; is every finding answered or still visibly open; does any rule pass vacuously.
- [ ] **Step 3: Re-run the Step 0 scenario** — all three defects must be found and named.
- [ ] **Step 4: REFACTOR** until compliant twice in a row, and add a red-flags list that includes "the script is green, so the contract is fine".
- [ ] **Step 5: Read it end to end**; remove repo-specific paths and terms.
- [ ] **Step 6: Commit** `docs: add the data-contract review`.

### Task 10: Onboarding creates the contracts

**Files:** Modify `.agents/skills/onboarding/SKILL.md` (Build row), `references/base-setup.md`, `references/greenfield.md`

- [ ] **Step 0: Baseline.** Ask a subagent to onboard a repo with gold marts using the onboarding skill as it stands. Record that it creates no `contracts/` and registers neither artifact path.
- [ ] **Step 1: Add the step** — declare `contracts/` in both maps, seed both skills with their scripts, run `reverse`, write the review artifact, and state that the contracts are partial until the findings are triaged.
- [ ] **Step 2: Extend the seeded-skills paragraph** — both skills are always seeded; a repo with no gold marts still has raw and staging relations to contract.
- [ ] **Step 3: Re-run the Step 0 scenario** — onboarding must create `contracts/`, register both paths, and write a review artifact with at least one finding.
- [ ] **Step 4: Commit** `docs: onboarding declares the contracts and queues what it cannot settle`.

### Task 11: Register the artifacts and the gate

**Files:** Modify `repo-map.json`, `test-map.json`, `tests/test_maps.py`

- [ ] **Step 1: Write the failing map test** — assert `artifact_paths.data_contract`, `modules.contracts`, `commands.odcs_check`, `commands.odcs_check_relations`, and the `key_directories` line exist; every path exists on disk; the module appears in `test-map.json`.
- [ ] **Step 2: Run it — fails.**
- [ ] **Step 3: Add the entries** in the same shape as `logical_model` and `ontology`, including the
  `key_directories` line, and declare the gold layers explicitly so `odcs.py` stops inferring them
  from the three names in `NON_GOLD_LAYERS`.
- [ ] **Step 4: Run `tests/test_maps.py` — passes.**
- [ ] **Step 5: Commit** `chore: register the contracts and their gate`.

### Task 2b: the checks that need a catalog and a platform

**Files:** Modify `.agents/skills/data-contract/scripts/odcs.py`; Test `tests/test_odcs.py`

**Depends on:** Task 3 (`generate`), Task 4 (`contracts/`), Task 11 (the map's artifact paths and its gold layers).

**Interfaces:** Adds `relations/mismatch` (a contract disagrees with the built relation), `relations/no-catalog` (`--relations` asked for and no catalog resolves — a failure, never a skip), and `servers/mismatch` (the declared `servers.type` disagrees with the platform the map declares). The six library audit relations are visible only here.

- [ ] **Step 1: Write the failing tests** — a catalog column the contract dropped, a contract property the catalog does not have, `--relations` with no catalog, and a `servers.type` that disagrees with the map.
- [ ] **Step 2: Run them — four failures.**
- [ ] **Step 3: Implement.** Resolve the catalog from `VD_EPHM_DUCKDB_LOCAL_PATH` first and `domain.duckdb` at the repo root second, never a literal; compare `information_schema` to the contract; resolve the platform from the map's declaration.
- [ ] **Step 4: Run them — pass, then `check` and `check --relations` on the real repo.**
- [ ] **Step 5: Commit** `feat: check contracts against the built relation and the platform`.

### Task 12: Put the gate in the hook and in CI

**Files:** Modify `tools/ossie_lint.py`; Test `tests/test_ossie_lint.py`

**Interfaces:** `ossie_lint.py` calls `odcs.py check` and treats an error as blocking; `.githooks/pre-commit` and `.github/workflows/repo-checks.yml` are **not** modified. There is no Domain `verifying` skill to edit — the plugin's is a `skill-changes` row, and `check --relations` is named in Task 9's review instead.

- [ ] **Step 1: Write the failing test** — `ossie_lint.py` exits 1 on a malformed contract, and exits 0 when `contracts/` is absent.
- [ ] **Step 2: Run it — fails.**
- [ ] **Step 3: Wire it.** Keep `glossary` non-blocking; the contract check is blocking.
- [ ] **Step 4: Run the test, then `python3 tools/ossie_lint.py` — green, and a deliberately broken contract makes it red.**
- [ ] **Step 5: Commit** `feat: the canonical lint gates the contracts too`.

### Task 13: The three failure demonstrations

**Files:** Create `tests/test_odcs_contracts.py`; Modify `test-map.json`

- [ ] **Step 1: Case A** — a dbt model gaining a column with no contract entry fails `dbt build`, naming the column. Prove it on a scratch copy.
- [ ] **Step 2: Case B** — a dlt source yielding an undeclared column fails the load with the freeze violation.
- [ ] **Step 3: Case C** — `check --relations` fails when the catalog holds a column the contract dropped, naming both.
- [ ] **Step 4: Run all three and record the exact message each produces** in the commit body.
- [ ] **Step 5: Commit** `test: prove each enforcement path fails on drift`.

### Task 14: The workarounds rows and the plugin gaps

**Files:** Modify `.agents/skills/workarounds/SKILL.md`, `AGENTS.md:39`, `docs/setup/skill-changes.md`

- [ ] **Step 1: Add the three workarounds rows** — "Write the contract first, and update it in the same intent"; "Reverse the contracts when you adopt a repo, and queue what you cannot settle" (the onboarding path, naming the review artifact and that nothing invented goes into the contract); "Run the contract gate before you write `verify.md`". Each ends with its `Remove when:` line naming the plugin skill that must carry it.
- [ ] **Step 2: Update the `AGENTS.md` index row** listing what the workarounds skill covers.
- [ ] **Step 3: Add five plugin rows** to `skill-changes.md` — `generating-dbt-model`; `generating-dlt-pipeline` + `add-or-update-source`; `verifying` (it must run `check --relations` and read the gate from `test-map.json`, VD-6919); `install-ci` (the bundle runs the gate and skips cleanly without `contracts/`); `onboarding` (seeds both skills, creates `contracts/`, writes the review artifact, states that the contracts are partial until triaged, **and carries the three contract rows in its `templates/skills/workarounds.md` template** — otherwise a freshly onboarded repo inherits the gaps with no rule). Add the note that the canonical-artifacts and contract rows collapse into one when the plugin lands.
- [ ] **Step 4: Add the Linear row** for each gap, all under VD-7139.
- [ ] **Step 5: Commit** `docs: carry the contract rule in workarounds and queue the plugin gaps`.
- [ ] **Step 6: Correct ADR-0222 in the studio repo** — a new branch there, one commit, its own PR at the close-out. The ADR's bullet claims the schema leaves `logicalTypeOptions` an open object, so the gate needs its own allow-list of documented option keys. That is false: the vendored `v3.2.0` schema constrains the option keys per logical type (`timeZone` is rejected, `timezone`, `defaultTimezone` and `format` are accepted, verified against the vendored file), so no allow-list exists or will. Rewrite the clause to "where the two disagree the standard wins, and the vendored schema already constrains `logicalTypeOptions` per logical type, so the gate keeps no allow-list of its own", and make the two-halves bullet say the option keys are proven *through the schema*, not by a separate check. This is a correction to a stated mechanism, not to the decision: validating against the standard's schema is unchanged.

### Task 15: Extend VD-7139 from the built artifacts

**Files:** Modify VD-7139's description and acceptance criteria in Linear; Modify `docs/requirement/odcs-data-contracts.md` (approval line)

**Interfaces:** The issue text is written **from** the two skills, the `skill-changes.md` rows and this plan's traceability — never from memory of the design discussion. Every claim must name an artifact that exists in this repo.

- [ ] **Step 1: Wait for the artifacts.** Tasks 8, 9, 10 and 14 must be complete; the issue describes what was built, so it cannot be written earlier.
- [ ] **Step 2: Draft the description** in VD-7139's existing shape — Problem, Scope in this repo, Scope in the plugin, Acceptance criteria — carrying the five `skill-changes` rows verbatim in intent, plus the seeding dependency on 7139's existing item 6.
- [ ] **Step 3: Check every claim against the repo** — each named skill exists at the seeded path, each named command exists in `repo-map.json` `commands`, and no claim describes a plugin mechanism that does not exist.
- [ ] **Step 4: Update the issue** and record its revision in the requirement's approval line.
- [ ] **Step 5: Commit** `docs: record that VD-7139 now carries the contract port`.

---

## Traceability

| Requirement | Tasks |
| --- | --- |
| R-01 vendored offline schema | 1 |
| R-02 one contract per relation, no orphans | 2, 4, 11 |
| R-03 the four sections, and only those | 2, 4 |
| R-04 `servers` platform rule | 2b, 4 |
| R-05 absence, not blanks; no unknown keys | 2 |
| R-06 forward path is the authoring path | 3, 8 |
| R-07 enforcement generated, never hand-written | 3, 5, 6 |
| R-08 gold agreement, declared fields only | 2 |
| R-08a `logicalType` from the model; timezone option; `physicalType` | 2, 4 |
| R-09 `check` and `check --relations` | 2, 2b, 11 |
| R-10 one lint for hook and CI; `--relations` at verify | 9, 12 |
| R-11 generic skills | 8, 9 |
| R-12 forward path demonstrated | 13 |
| R-13 plugin port tracked | 14 |
| R-14 reverse first pass, ADR-backed rules | 4, 5, 7 |
| R-15 reverse declares only what it can ground | 4 |
| R-16 doubts become review findings | 7 |
| R-17 triage completes the contracts | 7, 9 |
| R-18 no rule for a rule's sake | 5, 8 |
| R-19 both skills state their path; onboarding writes the artifact | 8, 9, 10 |
| R-20 `workarounds` carries the three plugin gaps | 14 |
| R-21 `skill-changes` rows, and VD-7139 updated from them | 14, 15 |

## Execution mode

Use the `subagent-driven-development` skill. Each task is dispatched to a subagent with its Files, Interfaces and Steps intact, and its output is checked against the task's own acceptance step before the next task starts. Two subagents never edit the same file; the generator-owned properties files and `contracts/**` are serialised through the tasks as written.

**No PR per task.** Every task commits to one branch, and the pull request is raised only at the close-out below. A task that fails its own acceptance step is fixed before the next one starts; nothing is pushed as a draft PR to be finished later.

## Close-out — the gated finish, once every task is ticked

None of this is optional, and none of it may be skipped because the work "looks done".

1. **Run the quality gates** through `implementing-linear-issue`, with a subagent per gate group: `python3 -m pytest tests -q`, `python3 tools/ossie_lint.py`, `dbt build`, and `ruff check .`. Every failure is fixed at the cause, never by weakening a check.
2. **Reconcile with Linear.** Check off each acceptance criterion on the issue against evidence from step 1, by reading the criterion rather than the task list. A criterion with no evidence stays unticked and the reason is written on the issue.
3. **Review the diff** with a subagent running `ai-pr-review-guide`. Read its `VERDICT`.
4. **If the verdict is not ready to merge, do not raise the PR.** Bring the findings back here and discuss them — which are real, which do not apply, and what changes as a result.
5. **Only when every gate is green and the verdict is ready to merge**, raise the PRs. Two, because they are two repos: this plan's change, and the studio ADR-0222 correction from Task 14 Step 6. Neither is raised before the close-out, and the ADR correction is not folded into a task branch.

## Order and gates

1–3 and 2b build the tool; 4–6 land the artifacts and the enforcement; 7–10 are the review artifact, the two skills and onboarding; 11–12 wire the gates; 13–15 close the loop.

Task 4 needs a green `dbt build`; Task 5 cannot land before 4; Task 12 cannot land before 2; Task 2b runs after 3, 4 and 11; Task 13 cannot land before 5 and 6. Tasks 8 and 9 are sequential — each needs its baseline recorded before any text and both must pass their scenario twice before the next task starts. Task 10 needs both skills present. **Task 15 is last by construction**: VD-7139 is written from the skills and the `skill-changes` rows, so it cannot precede them.

## Settled decisions

1. **The properties files grow.** Every column carries a `data_type` so `dbt build` enforces shape. Accepted; no model opts out.
2. **The rebuild is a one-time copy.** Task 4 copies the studio warehouse and runs `dbt build` before `reverse`, with no downloads. After that, normal operation is generate → commit → the build and `--relations` catch drift, and the staleness concern does not recur.
3. **VD-7139 is extended**, not duplicated, and Task 15 writes it from the artifacts rather than the design discussion.

## Remaining unknown

`--relations` must read the same catalog the dbt profile writes. Task 2 resolves `VD_EPHM_DUCKDB_LOCAL_PATH` first and falls back to `domain.duckdb` at the repo root — never a literal — and names that resolution where a reader can find it.

## External dependency

`docs/adr/0222-...` lives in the `accelerate-data/studio` repo and does not exist yet. This plan references it as the product decision; VD-7139's update must not claim it is written until it is.

## Not in this plan

The plugin port (seed set, kind, playbooks, Studio suggestions, evals, version bump) — separate issue, blocked on VD-7139. Any contract UI, converter or catalog sync. The `price`, `support`, `team`, `roles` and `slaProperties` sections.
