---
kinds: [project-config, documentation]
---

# Requirement: Open Data Contract Standard contracts for every relation in the Domain

## Ask

The Domain has two canonical artifacts — the Domain Data Model and the ontology — and neither states the shape a consumer is promised, nor what a build must refuse to break. Define an ODCS `v3.2.0` data contract for every relation the maps declare, and make the contract the thing that is authored first: profile the data, write the contract, generate the enforcement from it, then write the code to satisfy it.

The contract is not a rendering of what the code happens to do. It is the published promise, and dbt and dlt refuse a change that breaks it. Reverse engineering is the onboarding path only.

The same work ships as a Domain convention skill so every customer repo inherits it. The plugin port is tracked separately (R-13), because VD-7139 owns the seeding mechanism for Domain convention skills and this work depends on it.

## Scope

In scope: one contract per relation across the schemas `repo-map.json` declares; the generated dbt and dlt enforcement; `tools/odcs.py` with `check` and `check --relations`; the `data-contract` authoring skill and the `validating-data-contract` review; the vendored pinned schema; the `repo-map.json` and `test-map.json` registrations; the pre-commit and CI wiring; the reverse-engineered first pass; the forward demonstration and its cases.

Out of scope: the ODCS sections that assert nothing here (`price`, `support`, `team`, `roles`, `slaProperties`); a contract UI, viewer or catalog sync; a converter from a contract into any format; a MetricFlow export; any change to the dbt models, seeds or macros beyond the enforcement the contracts generate.

## Requirements

- [x] `R-01` The ODCS JSON schema is vendored at `v3.2.0` at a pinned upstream commit beside the authoring skill, resolved offline, and never edited — accept when `check` validates a document with no schema changes and no network access, and the vendored file carries its upstream commit — source: `semantic-model/scripts/ossie_vendor/`, same rule for the Ossie schemas

- [x] `R-02` Every relation in every schema `repo-map.json` declares has exactly one contract at `artifact_paths.data_contract`, and no contract names a relation that does not exist; the loader's own `_dlt_*` relations and columns are excluded, because they describe the loader and not the table — accept when `check` reports zero relations without a contract and zero orphan contracts across all ten declared schemas, and no contract declares a `_dlt_` name, except the five dbt models that propagate `_dlt_load_id`, which an enforced contract cannot omit — source: user answer, the Task 4 ruling, "every table should have a defined contract"

- [x] `R-03` A contract carries the four sections that assert something: fundamentals, `servers`, `authoritativeDefinitions`, and one `schema[]` element with `properties`, `relationships` and `quality` — and it states its grain in `schema[].dataGranularityDescription`, the standard's own field, required by this decision, because a contract without it promises nothing a reader can refuse — accept when every contract validates against the vendored schema, no contract carries a section outside that set, and `check` reports a missing `dataGranularityDescription` as a warning that names the relation and leaves the exit code at 0, while the review refuses a contract a shipped intent presents as complete — source: ODCS v3.2.0 schema; `quality` has no root-level key and nests inside a schema element

- [x] `R-04` `servers` names the Domain as the server and the platform as the type: the native ODCS type where the enum has one and every field it requires can be told truthfully, `custom` with the platform kind in `customProperties` otherwise. The DuckDB type's required `database` carries the platform's own database identifier — the warehouse file for `duckdb_local`, the database name for `motherduck` — and never a sandbox copy's name — accept when `duckdb_local` and `motherduck` carry `type: duckdb`, `bigquery`, `databricks`, `redshift` and `snowflake` carry their own type, `fabric_lakehouse` and `fabric_warehouse` carry `custom` with the kind in `customProperties`, and every `database` value traces to the platform declaration — source: user answers; ODCS Server enum and the DuckDB server's required `database`

- [x] `R-05` A section is absent or it asserts something: no present-but-empty `servers`, `quality`, `tags` or `authoritativeDefinitions`, no key outside the standard (`additionalProperties` is `false`), and no key the standard does not define — the vendored schema rejects both an unknown section and a `logicalTypeOptions` key it documents for no such logical type (`timeZone` is invalid, `timezone` is valid, verified against the vendored file, so no hand-kept allow-list is needed) — accept when `check` fails a contract carrying `servers: []`, an empty `quality`, or an unknown key — source: ODCS v3.2.0 schema and "Logical Type Options", verified against `null`, `{}` and an unknown key

- [x] `R-06` The forward path is the authoring path: a new or changed relation is profiled, the contract is written, the enforcement is generated, and the code is written to satisfy them — accept when the authoring skill states that order, names the profile command, and `check` fails a change whose enforcement was not regenerated — source: user answer, "profile data and define contract and then write tests to enforce contract"

- [x] `R-07` Enforcement is generated from the contract and never hand-written: a properties file per layer carrying `contract: enforced`, `data_type` and the `quality` rules as `data_tests` for dbt, and `columns=` hints under the existing `schema_contract` for each dlt resource — accept when regenerating produces no diff on a clean tree, and a contract edit changes both generated artifacts — source: user answer, "the dbt and dlt tests will enforce the contract"

- [x] `R-08` A gold contract agrees with its canonical document **for the fields that document declares**, and declares every one of them: the Ossie `datatype` becomes `logicalType`, the declared keys become `primaryKey`/`unique`, and the declared relationships become `relationships[]`. A field the document declares and the contract omits is an error, so a gold contract cannot pass by promising nothing. A property the document does not declare takes its `logicalType` from the physical type and is not compared — the model is curated, and its 149 declared fields sit on 17 of gold's 34 tables. Disagreement on a declared field fails and is resolved by changing whichever of the two the intent changed, in the same commit — accept when `check` fails a gold contract whose declared-field name, logical type, key or relationship diverges from the document named in its `authoritativeDefinitions`, fails one that omits a field the document declares, names both sides, and reports zero errors for the 392 properties no document declares — source: `docs/adr/0220-...` and `0222-...`; the model is the source of truth for the analytical layer

- [x] `R-08a` `logicalType` is the Ossie `DataType` reduced onto the ODCS enum — `String`→`string`, `Integer`→`integer`, `Decimal` and `Float`→`number`, `Boolean`→`boolean`, `Date`→`date`, `Time`→`time`, `DateTime` and `DateTimeTz`→`timestamp`, `Opaque`→absent — with `logicalTypeOptions.timezone: true` for `DateTimeTz`, and `physicalType` written on every property because the standard makes it the carrier for source-specific types and because neither the enum nor the options express `Decimal` precision — accept when a gold property's `logicalType` equals its field's `datatype` under that reduction, a `DateTimeTz` field carries the timezone option and a `DateTime` field does not, every property carries a `physicalType`, and an `Opaque` property carries no `logicalType` — source: user answer, "logical type should get the OSSIE definition"; Ossie `DataType` enum; ODCS "Logical Type Options" and "Expressing Date / Datetime / Timezone information"

- [x] `R-09` `tools/odcs.py check` runs the file-only checks; `check --relations` adds the comparison against the built relation and fails when no catalog resolves rather than skipping — accept when the file-only mode passes with no warehouse, `--relations` fails with no warehouse, and both are declared in `repo-map.json` `commands` — source: user answer, an intent with resources always has an ephemeral warehouse

- [x] `R-10` The contract checks run where the artifacts are: `tools/ossie_lint.py` calls the file-only checks so the existing `.githooks/pre-commit` and `.github/workflows/repo-checks.yml` cover contracts with no new hook and no second command list, and `verifying` runs `--relations` — accept when a malformed contract fails pre-commit, `repo-checks.yml` still runs one repo command, and the verification procedure names `--relations` — source: `install-ci` rule, one script for the hook and CI

- [x] `R-11` The authoring skill is generic — it resolves every location from `repo-map.json` and names no repo path, layer or domain term — and the review covers what no script sees: grain, honest `required`, a quality rule that encodes the real business answer, whether a declared change is actually breaking, and whether a gold contract means what its document means — accept when neither skill contains a literal path or a taxi term and each review item has a rule the script cannot check — source: the `ontology` and `validating-semantic-model` split

- [x] `R-12` The forward path is demonstrated, not asserted: a dbt model change that leaves its contract behind fails the build, and a source column added without a contract update fails the dlt run — accept when both cases fail with a message naming the contract and the relation — source: user answer

- [x] `R-13` VD-7139 is extended rather than duplicated: its description and acceptance criteria gain the contract artifact, both skills, the vendored schema and the script, the onboarding reverse pass with its review artifact, and the plugin's `verifying` and `install-ci` obligations — and this repo's plan does not modify the plugin — accept when VD-7139's description names each of those and its acceptance criteria reference the artifacts this repo built, with no claim about a skill or gate that does not exist here — source: user answer; VD-7139, "Onboarding (in-repo, seeded)"

- [ ] `R-14` The first pass is reverse-engineered and says so: the contracts describe what the code does today, and the demonstration of value is the quality rules that encode a standing business answer — the billable rule, the 25-trip floor, the SCD2 keys — so at least those contracts assert something the SQL alone does not — accept when each named rule appears as a `quality` entry citing its ADR in `authoritativeDefinitions` — source: `docs/adr/0003`, `0017`, `0009`

- [x] `R-15` The onboarding path declares only what it can ground — the catalog's columns and types, the existing dbt tests, the existing relationships, and the descriptions already written — and invents no quality rule, no key and no nullability it has not established — accept when `reverse` on a relation whose only evidence is a column list emits a contract with no `quality` entry, no `primaryKey` and no `required: true`, and the contract still validates — source: user answer, "finding the contract from data might not be very accurate"

- [x] `R-16` Every doubt the reverse pass cannot settle is written to the review artifact path as a finding naming the relation, the table or column, the doubt and the question that settles it — accept when a fresh reverse run writes one finding per unsettled grain, undescribed column, unproven key, open enum, unproven relationship and violated candidate rule, and writes none for a relation it settled — source: user answer, "any doubts will show up under docs/review for later triaging"

- [ ] `R-17` Contract completion is triage of those findings, not bulk authoring: an answered finding either adds the quality rule or key it names or records why the answer is "no rule", and adding a promise moves the contract's `version` — accept when the review artifact's finding count reaches zero and every answer is traceable to the contract entry or the reason it was declined — source: user answer

- [x] `R-18` Neither path creates tests for their own sake: a quality rule exists because a dbt test, a standing business answer or a profile raised it, never because a column exists — accept when the contract set's `quality` entries all cite a test, an ADR or a recorded finding — source: user answer, "we cannot create 100s of tests"

- [x] `R-19` Both skills state their path: `data-contract` states the forward order and the onboarding reverse-plus-review order, and `validating-data-contract` reviews a contract against its findings list so an unsettled doubt is visible rather than absent — accept when neither skill presents a contract with no quality rules as complete, and the onboarding skill creates `contracts/`, registers it in both maps, and writes the review artifact — source: R-15 to R-18

- [x] `R-20` The `workarounds` skill carries the three gaps the plugin does not cover — a contract written before the code, a reverse pass on an adopted repo with its findings queued, and the structural gate before `verify.md` — each naming the change that retires it — accept when the three rules are in `workarounds`, each has a `Remove when:` naming the plugin skill that must carry it, and `AGENTS.md`'s index row lists them — source: user answer

- [x] `R-21` `docs/setup/skill-changes.md` carries the gaps derived from what was actually built, and VD-7139 is updated from that document and from the skills rather than from this plan — accept when every plugin obligation has a row naming the skill, the reference and the suggested change, and VD-7139's text matches those rows one for one — source: user answer

## Business decisions

| Decision | Value | Source |
| --- | --- | --- |
| What one contract covers | One per relation, every declared schema, so dbt and dlt jobs can read it when changing code | user answer |
| Which is authored | The contract. Schema, required, keys and quality terms are written first; enforcement is generated | user answer |
| Where the schema duplication is resolved | Not duplicated: the contract is authored, and for gold the fields the canonical document declares are compared against it | user answer, `docs/adr/0220-...` |
| The logical type's provenance | The semantic model's `datatype`, reduced onto the ODCS enum; the physical type when the model declares no field. `physicalType` always, so the reduction is reversible | user answer |
| Optional sections | Omitted. `null` and `{}` are invalid or assert nothing, so absence is the only honest "no promise" | ODCS v3.2.0 schema |
| Platform in the contract | Domain as server; native type where true, `custom` otherwise | user answer |
| Table agreement | Checked by the build, not by pre-commit alone; `--relations` is mandatory in `verifying` | user answer |
| Reverse engineering | Onboarding and adoption only, and partial by design: it declares what the catalog, the existing tests and the glossary establish, and queues the rest as review findings | user answer |
| Plugin port tracking | VD-7139 is extended, not duplicated, and its text is derived from the skills and `skill-changes.md` once they exist | user answer |
| Test volume | A rule exists because a test, a standing business answer or a profile raised it; never one per column | user answer |
| Where an unsettled doubt lives | `docs/review/`, triaged later; never guessed into the contract | user answer |

## Out of scope

- `price`, `support`, `team`, `roles`, `slaProperties`, `context`, `variables`.
- Any contract UI, viewer, registry or catalog synchronisation.
- A converter that reads a contract and produces anything.
- Contracts for relations outside the schemas the maps declare.

## Open questions

None. The section set, the platform mapping and the check placement are settled above.

## Approvals

- 2026-10-24 — requirement drafted for review — design agreed in session: contract-first authoring, generated enforcement, one lint extended for contracts, platform mapping by the ODCS enum — pending approval and commit
- 2026-10-25 — closed out: every gate green (`pytest` 291, `ruff`, `ossie_lint` 0 blocking, `dbt build --full-refresh` PASS=223 ERROR=0). R-01 to R-21 are ticked against that evidence except two. **R-14** is partly met: the rules exist and trace to dbt tests, but a contract cites its canonical document rather than each rule citing its ADR, because `reverse` grounds `quality` only in generic tests and the three named rules are singular tests. **R-17** is not met: 1501 findings are queued in the review artifact and none is triaged — that is the next intent's work
