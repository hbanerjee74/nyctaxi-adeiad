# Plan: Borough-to-borough trip flows Q1 2024

**Goal:** Publish `agg.agg_borough_flow_monthly`, a zero-filled month × origin borough × destination borough table of billable trips, revenue and each origin borough's cross-borough share, with its contract and its semantic-layer source.

**Requirement:** `docs/requirement/2026-11-24-borough-to-borough-trip-flows-q1-2024-cf51ad62.md`

**Constraints:**

- Grain is one row per calendar month × origin borough × destination borough; every one of the 8 `dim_zone.borough_name` values appears as both origin and destination, so the table has three months' worth of 64-pair grids.
- Billable trips only (`f.is_billable`), inside the reporting window via the `in_report_window` macro; `dim_zone` inner-joined twice, which is the only row filter.
- Revenue is `sum(f.total_amount)`; no payment method excluded.
- The share is cross-borough trips ÷ the origin borough's billable trips that month, through `safe_divide`, repeated on every row of that origin, with its denominator published beside it.
- A pair with no trips is a row of zeros, never an omitted row; no `HAVING` floor is applied at borough grain.
- Layer `agg` (boundary), materialised `table`, folder `transformation/models/marts/agg/`, schema `agg`.
- Columns listed explicitly, no `select *`; every column carries a description.
- Money comparisons are at the cent (`round(x, 2)`); counts compare exactly.

## Scope and impact

| Artifact | Kind | Action | Requirements | Design record | Gate |
| --- | --- | --- | --- | --- | --- |
| `agg.agg_borough_flow_monthly` (`transformation/models/marts/agg/agg_borough_flow_monthly.sql`, its `_agg.yml` entry, and the singular tests `transformation/tests/assert_borough_flow_*.sql`) | model | create | `R-01`, `R-02`, `R-03`, `R-04`, `R-05`, `R-06`, `R-08` | `docs/design/models/agg/agg_borough_flow_monthly.md` | `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit` |
| `contracts/agg/agg_borough_flow_monthly.odcs.yaml` | contract | create | `R-07` | `docs/design/models/agg/agg_borough_flow_monthly.md` | `python3 .agents/skills/data-contract/scripts/odcs.py check` |
| `logical-model/nyc_taxi_analytics.ossie.yaml` | logical-model | modify | `R-07` | `docs/design/models/agg/agg_borough_flow_monthly.md` | `python3 .agents/skills/semantic-model/scripts/ossie.py validate logical-model/` |

**Change impact:** `none downstream` — `agg_borough_flow_monthly` is a new leaf. No existing model's SQL, properties or contract changes; `agg_od_flow_matrix` and its 25-trip floor are untouched. `fct_trip` and `dim_zone` are read, not changed. The one shared file that changes is `transformation/models/marts/agg/_agg.yml`, which gains one model entry and no edits to any existing entry. `/data/cache` is not read: the dbt card's `## Defer` section says no production manifest is published for this Domain.

## Tasks

### Task 1: `agg_borough_flow_monthly` with its contract

**Requirements:** `R-01` … `R-06`, `R-08` · **Design:** `docs/design/models/agg/agg_borough_flow_monthly.md` · **Skill:** `data-contract` for the contract, then `generating-dbt-model` · **Depends on:** none

- [ ] Author `contracts/agg/agg_borough_flow_monthly.odcs.yaml` with `data-contract`, `status: proposed`: the relation `agg.agg_borough_flow_monthly`, `primaryKey` on the three grain columns, and every column the design names — `trip_month` (DATE), `origin_borough` (VARCHAR), `dest_borough` (VARCHAR), `is_intra_borough` (BOOLEAN), `trip_count` (BIGINT), `total_revenue` (DOUBLE), `origin_trip_count` (BIGINT), `cross_borough_trip_count` (BIGINT), `cross_borough_trip_share` (DOUBLE) — each with a description that states its rule, `trip_month` the reference to the calendar month. Run `python3 .agents/skills/data-contract/scripts/odcs.py check`; expect exit 0 with the proposed-status warnings only.
- [ ] Author `transformation/models/marts/agg/agg_borough_flow_monthly.sql` in the shape the design fixed: two `with` blocks for the spine (the window's `dim_date.month_start_date` values cross-joined to `dim_zone`'s distinct borough list twice, inner-joined for the row set) and the trips (billable, in window, `dim_zone` joined twice on pickup and dropoff zone keys, carrying `total_amount`, `origin_borough`, `dest_borough`, `trip_month`), then a `full outer`-free `left join` of trips onto the spine, grouped to the grain. The share and its numerator and denominator come from one grouped pass over the trips (`count(*) filter (where origin_borough <> dest_borough)` and `count(*)` per origin and month), joined back on origin and month with `safe_divide`. A borough or month pair with no trips must show `trip_count = 0`, `total_revenue = 0` and `cross_borough_trip_count = 0`, with the share still carrying its origin's value (`0` when the origin had trips but none crossed, null when the origin had none at all).
- [ ] Author the model's `_agg.yml` entry with `contract: {enforced: true}`, the description, and the column list; then write the enforcement keys with `python3 .agents/skills/data-contract/scripts/odcs.py generate` rather than by hand, and re-read the entry it wrote.
- [ ] Author the singular tests, each returning the violating rows:
  - `transformation/tests/assert_borough_flow_grid_is_complete.sql` — full outer join of the three window months × the 8 boroughs × the 8 boroughs against the table; returns any missing or extra grain combination, so a zero-trip pair can never be silently absent.
  - `transformation/tests/assert_borough_flow_one_row_per_grain.sql` — `group by trip_month, origin_borough, dest_borough having count(*) > 1`.
  - `transformation/tests/assert_borough_flow_covers_every_resolved_trip.sql` — `sum(trip_count)` and `round(sum(total_revenue), 2)` against an independently aggregated `fct_trip` (billable, in window, both zone keys resolved), using `is distinct from` so an empty table fails rather than passes.
  - `transformation/tests/assert_borough_flow_share_matches_its_denominator.sql` — recomputes the share from `cross_borough_trip_count` and `origin_trip_count` on the row, and checks one share value per origin and month across its destination rows.
  - `transformation/tests/assert_borough_flow_zero_rows_are_zero.sql` — every row with `trip_count = 0` has `total_revenue = 0` and `cross_borough_trip_count = 0`, and every row with `trip_count > 0` has a positive revenue.
- [ ] Run `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit`; expect the model and all five singular tests to pass, the model reporting 192 rows.
- [ ] Set the contract to `status: active`, re-run `odcs.py generate`, and re-run `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit`; expect pass at the active contract.
- [ ] Run `python3 .agents/skills/data-contract/scripts/odcs.py check --relations`; expect exit 0 and no `relations/mismatch`.
- [ ] Load `validating-data-contract` and record its report.
- [ ] Commit and push `transformation/models/marts/agg/agg_borough_flow_monthly.sql`, `transformation/models/marts/agg/_agg.yml`, the five singular tests, and `contracts/agg/agg_borough_flow_monthly.odcs.yaml`.

### Task 2: the semantic-layer source and the ontology re-run

**Requirements:** `R-07` · **Design:** `docs/design/models/agg/agg_borough_flow_monthly.md` (`## Logical Model`) · **Skill:** `semantic-model` · **Depends on:** Task 1

- [ ] Add `LTS10_borough_flow_monthly` to the `trips` dataset's `logical_sources` in `logical-model/nyc_taxi_analytics.ossie.yaml`, `priority_group: 0`: `physical_table: agg_borough_flow_monthly`, `content_grain: ["trip_month", "origin_borough", "dest_borough"]`, `column_map` binding `billable_trip_count` to `trip_count` and `billable_revenue` to `total_revenue`, `content_levels` naming `trips_to_date` at `month` on `trip_month`, `trips_to_pickup_zone` at `borough` on `origin_borough`, and `trips_to_dropoff_zone` at `borough` on `dest_borough`, and a `content_filter` stating the model's `WHERE` and the two inner joins' null exclusions as literals bounded by the dbt vars' dates. Its `note` names `assert_semantic_content_holds` and refuses `origin_trip_count`, `cross_borough_trip_count`, `cross_borough_trip_share` and `is_intra_borough`, each with why.
- [ ] Regenerate the Ossie tests with `python3 .agents/skills/semantic-model/scripts/ossie.py generate-tests logical-model/ transformation/tests`; never edit them by hand.
- [ ] Run the structural gates, expecting exit 0 from each: `python3 .agents/skills/semantic-model/scripts/ossie.py validate logical-model/`, `... coverage logical-model/ transformation/models/marts/` (with `--exclude` for each relation `repo-map.json` lists under `semantic_exclusions`), `... suppliers logical-model/`, `... notes logical-model/ transformation/tests docs/adr/`, and `... generate-tests logical-model/ transformation/tests --check`.
- [ ] Run `python3 .agents/skills/semantic-model/scripts/ossie.py refs ontology/nyc_taxi.ontology.yaml logical-model/` against the edited document; expect exit 0.
- [ ] Run `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit` again so the regenerated content test runs against the built table; expect pass.
- [ ] Load `validating-semantic-model` and record its report.
- [ ] Commit and push `logical-model/nyc_taxi_analytics.ossie.yaml`, the regenerated tests, and any contract change `odcs.py check` requires after the document edit.

## Execution evidence
