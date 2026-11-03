---
name: dbt-models
description: "Use when creating, renaming or editing a dbt model, its properties file or its materialisation in transformation/."
---

# dbt models
<!-- onboarding
ask: no
reason: Index text; sections below carry the decisions.
-->

Operator conventions for dbt models in `transformation/`. Where files live is declared in `repo-map.json`; this file covers naming and shape.

## Layer roles (B1)
<!-- onboarding
ask: yes
question: Which layers does this domain have, what is each called, and which role does each play?
recommended: One input layer per source system, named after it (landed by dlt); `staging` and `intermediate` internal; marts split by area, boundary, `core` first. These are the default names; the roles are the rule.
alternatives: one input layer for every source; other layer names; marts not split by area.
fills: <input layers>, <boundary layers>
-->

Each layer's role is declared in `repo-map.json` `layers.<name>.role`. The names are this domain's own choice; the rules below hold by role (the plugin's `layer-roles.md` has the full definitions).

- **Input** (<input layers, one per source system>): raw data loaded by the dlt pipelines in `ingestion/`. dbt reads it as sources and never writes to it.
- **Internal** (`staging`, `intermediate`, and any seed schema): dbt models for the domain's own use. Staging renames and casts one source table. Intermediate applies business logic and joins, with no grain commitment of its own.
- **Boundary** (<boundary layers, `core` first>): dbt marts a consumer outside the repo reads: grain-committed facts, conformed dimensions, aggregates.

## Time zones (B17)
<!-- onboarding
ask: no
reason: dlt and the sandbox time zone; the same for every DuckDB-local domain.
-->

dlt lands naive Arrow timestamps as `TIMESTAMPTZ`, and the session time zone is not always UTC (the sandbox is not). Staging converts every dlt-loaded timestamp with `timezone('UTC', col)`, so later models see the wall-clock value the source recorded. A model that reads an input relation without the conversion, or hashes a key from a converted and an unconverted timestamp, matches nothing and stays green.

## Sources name no database (B18)
<!-- onboarding
ask: no
reason: The sandbox is a renamed copy of the Domain file; the same for every domain.
-->

A source in `_sources.yml` names its `schema` and tables, never a `database`, and no var feeds either. In a Studio Intent the sandbox is a copy of the Domain file under another name, so its catalog differs; a source that names one fails with `Catalog ... does not exist`. `macros/relations.sql` renders every `ref()` and `source()` without the catalog for the same reason.

## Naming (B2, B3)
<!-- onboarding
ask: yes
question: How are models named?
recommended: Prefixes `stg_`, `int_`, `fct_`, `dim_`, `agg_`, `mart_`; staging `stg_<source>__<entity>`.
alternatives: suffixes instead of prefixes; a single underscore in staging names.
-->

| Prefix | Layer | Responsibility |
| --- | --- | --- |
| `stg_` | staging | One source table: rename and cast only |
| `int_` | intermediate | Business logic and joins, no grain commitment |
| `fct_` | boundary | Grain-committed events |
| `dim_` | boundary | Descriptive entities, conformed across facts |
| `agg_` | boundary | Aggregates built from facts |
| `mart_` | boundary | Consumption-shaped marts |

- Staging models are `stg_<source>__<entity>` (double underscore).
- Intermediate and boundary models name the entity directly.
- No `_fact` or `_dimension` suffix: the prefix carries it.

A new boundary model starts with its contract (`data-contract` skill, `status: proposed` until the table is built) and is routed by the `semantic-model` skill: it joins a star, or it is listed in `semantic_exclusions` with a reason.

## Properties files (B6)
<!-- onboarding
ask: yes
question: How are properties files organised?
recommended: One `_<folder>.yml` per folder; unit tests in `_unit_tests.yml` beside the dbt models.
alternatives: one YAML file per model.
-->

One YAML file per folder, named `_<folder>.yml`. Unit tests sit in `_unit_tests.yml` beside the dbt models they cover. Generic-test arguments go under `arguments:`.

## Columns (B8)
<!-- onboarding
ask: yes
question: May marts select every column?
recommended: No: marts list their columns.
alternatives: allow `select *` in marts.
-->

List columns explicitly. No `select *` in a mart.

## Audit columns (B12)
<!-- onboarding
ask: yes
question: Do models carry audit columns?
recommended: None unless a requirement asks; then boundary models only, all of `_loaded_at`, `_dbt_invocation_id`, `_git_sha`.
alternatives: audit columns on every boundary model.
-->

None unless a requirement asks for them. When one does: boundary models only, all or none of `_loaded_at`, `_dbt_invocation_id`, `_git_sha`.

## Materialisation (B15)
<!-- onboarding
ask: yes
question: How is each layer materialised?
recommended: Staging views; intermediate tables, or views at the grain of a fact that stores it; boundary tables.
alternatives: intermediate always tables; incremental facts from the start.
-->

| Role | Default |
| --- | --- |
| internal, staging | view |
| internal, intermediate | table; a view when it is at the grain of a fact that stores it, so the grain is stored once |
| boundary | table |
