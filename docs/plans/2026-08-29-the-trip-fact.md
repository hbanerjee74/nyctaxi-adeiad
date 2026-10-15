# Plan: The trip fact

Reconstructed from the repository for demonstration and context, like its [Requirement](../requirement/2026-08-29-the-trip-fact.md). The tasks describe the models as they stand; the execution evidence was gathered on 2026-10-15 against the seeded Domain (January 2024).

**Goal:** One trip-level fact across yellow and green, keeping every trip, with its quality verdicts, conformed dimensions and optional fleet attribution.

**Approach:** Conform the two fleets onto one grain in `int_trips_conformed`, rejoin the fleet-specific columns in `int_trips_enriched`, derive the quality verdicts in `int_trip_quality_flags`, and assemble `fct_trip` with as-of joins to the Type 2 dimensions. The trip key comes from one macro on every side ([trip identity](../design/trips/trip-identity.md)).

**Tech Stack:** dbt Core 1.12 with dbt-duckdb, DuckDB 1.5, dlt-loaded bronze.

## Global Constraints

- Grain of `fct_trip`: one row per distinct TLC trip (`R-01@1`).
- Billable trip: a positive total, applied where revenue and flows are reported ([ADR 0003](../adr/0003-billable-trip-definition-and-where-it-applies.md)).
- Quality verdicts flag trips and never delete them ([ADR 0004](../adr/0004-quality-verdicts-flag-trips-and-never-delete-them.md)).
- Unmatched dimension keys stay null, with no placeholder member ([ADR 0015](../adr/0015-unmatched-dimension-keys-stay-null.md)).
- `trip_key` has one definition, the `trip_natural_key` macro ([ADR 0007](../adr/0007-trip-key-has-one-definition.md)).

---

## Scope and impact

Requirement: [`docs/requirement/2026-08-29-the-trip-fact.md`](../requirement/2026-08-29-the-trip-fact.md), revision 1.

| Artifact | Kind | Layer | Action | requirements and acceptance criteria | Design record | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `trip_natural_key` | macro | n/a | create | `R-06@1` | [trip identity](../design/trips/trip-identity.md) | the only definition of `trip_key` |
| `int_trips_conformed` | model | intermediate | create | `R-01@1`, `R-06@1` | [`int_trips_conformed.md`](../design/models/intermediate/int_trips_conformed.md) | one row per distinct trip across fleets |
| `int_trips_enriched` | model | intermediate | create | `R-02@1` | [`int_trips_enriched.md`](../design/models/intermediate/int_trips_enriched.md) | fleet-specific columns and the airport-fee state |
| `int_trip_quality_flags` | model | intermediate | create | `R-03@1` | [`int_trip_quality_flags.md`](../design/models/intermediate/int_trip_quality_flags.md) | every verdict per trip, including `is_billable` |
| `fct_trip` | model | mart | create | `R-01@1`, `R-03@1`, `R-04@1`, `R-05@1` | [`fct_trip.md`](../design/models/core/fct_trip.md) | the trip contract |
| `assert_fct_trip_matches_conformed_rowcount` | test | n/a | create | `R-01@1` | — code is contract | |
| `assert_enrichment_rejoin_matches_every_trip` | test | n/a | create | `R-02@1` | — code is contract | added by the [airport-fee case](../cases/2026-10-14-airport-fee-rejoin-matches-nothing.md) |

**Source mapping.** `bronze.yellow_tripdata` and `bronze.green_tripdata` → `stg_tlc__*_tripdata` (staging, views) → `int_trips_conformed` (intermediate) → `int_trips_enriched` and `int_trip_quality_flags` → `fct_trip` (core). The extras come from bronze through `stg_tlc__*_trip_extras`; zones and vendors from `mdm_raw` through `dim_zone` and `dim_vendor`; fleet attribution from `ops_raw` through `stg_ops__trip_assignments`.

**Change impact.** All new; nothing existing is touched. `dbt ls --select fct_trip+` lists the marts and aggregates built on the fact, which arrive in later intents.

---

## Tasks

### Task 1: The trip key and the conformed trips

**Requirement refs:** `R-01@1`, `R-06@1`

**Files:**

- Create: `transformation/macros/trip_keys.sql`
- Create: `transformation/models/intermediate/int_trips_conformed.sql`
- Test: `transformation/models/intermediate/_unit_tests.yml` (`trips_conformed_keeps_one_row_per_distinct_trip`, `trips_conformed_distinguishes_fleets_with_the_same_natural_columns`)

- [x] **Step 1: Write the unit tests, run them, see them fail**
- [x] **Step 2: Author the macro and the model; run the unit tests**

Run: `dbt test --select "test_type:unit,+fct_trip" --target dev`
Expected: `PASS=3`

- [x] **Step 3: Commit**

### Task 2: Fleet-specific columns and quality verdicts

**Requirement refs:** `R-02@1`, `R-03@1`

**Files:**

- Create: `transformation/models/intermediate/int_trips_enriched.sql`, `transformation/models/intermediate/int_trip_quality_flags.sql`
- Test: `transformation/tests/assert_enrichment_rejoin_matches_every_trip.sql`

- [x] **Step 1: Author both models and the rejoin test**
- [x] **Step 2: Build them with their tests**

Run: `dbt build --select +fct_trip --exclude test_type:unit --target dev`
Expected: every node passes

- [x] **Step 3: Commit**

### Task 3: The trip fact

**Requirement refs:** `R-01@1`, `R-03@1`, `R-04@1`, `R-05@1`

**Files:**

- Create: `transformation/models/marts/core/fct_trip.sql`, its entry in `transformation/models/marts/core/_core.yml`
- Test: `transformation/tests/assert_fct_trip_matches_conformed_rowcount.sql`

- [x] **Step 1: Author the model and the row-count test**
- [x] **Step 2: Build with the singular tests**

Run: `dbt test --select assert_fct_trip_matches_conformed_rowcount assert_enrichment_rejoin_matches_every_trip assert_scd2_zone_intervals_do_not_overlap assert_airport_fee_only_on_yellow --target dev`
Expected: `PASS=4`

- [x] **Step 3: Commit**

## Execution evidence

- [x] Task 1: `dbt test --select "test_type:unit,+fct_trip" --target dev` — exit 0 — PASS=3 — `transformation/macros/trip_keys.sql` sha256:c8f9b8f44f99dbc7…, `transformation/models/intermediate/int_trips_conformed.sql` sha256:5cf1721f8fb108c5…
- [x] Task 2: `dbt build --select +fct_trip --exclude test_type:unit --target dev` — exit 0 — PASS=82 — `int_trips_enriched.sql` sha256:4a801d608befe8df…, `int_trip_quality_flags.sql` sha256:e33a8febee5a2d54…
- [x] Task 3: the four singular tests above — exit 0 — PASS=4 — `fct_trip.sql` sha256:3dceea49fce62d13…, `assert_fct_trip_matches_conformed_rowcount.sql` sha256:8b9fa528519ea9dd…

## Approvals

None: no breaking-contract stop arose.
