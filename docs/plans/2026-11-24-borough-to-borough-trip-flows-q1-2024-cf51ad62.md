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
- Columns listed explicitly, no `select *`; every column carries a description; every output is cast to its contract `data_type`, because DuckDB does not coerce to a declared type.
- Money comparisons are at the cent (`round(x, 2)`); counts compare exactly.
- The contract is `status: proposed` until an Ossie document names the relation, because `odcs.py check` fails `boundary/undeclared` on an `active` boundary contract no canonical document names.

## Scope and impact

| Artifact | Kind | Action | Requirements | Design record | Gate |
| --- | --- | --- | --- | --- | --- |
| `agg.agg_borough_flow_monthly` (`transformation/models/marts/agg/agg_borough_flow_monthly.sql`, its `_agg.yml` entry, its `_unit_tests.yml` unit test, and the five singular tests `transformation/tests/assert_borough_flow_*.sql`) | model | create | `R-01`, `R-02`, `R-03`, `R-04`, `R-05`, `R-06`, `R-08` | `docs/design/models/agg/agg_borough_flow_monthly.md` | `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit` |
| `contracts/agg/agg_borough_flow_monthly.odcs.yaml` | contract | create | `R-07` | `docs/design/models/agg/agg_borough_flow_monthly.md` | `python3 .agents/skills/data-contract/scripts/odcs.py check --relations` |
| `logical-model/nyc_taxi_analytics.ossie.yaml` | logical-model | modify | `R-07` | `docs/design/models/agg/agg_borough_flow_monthly.md` | `python3 .agents/skills/semantic-model/scripts/ossie.py validate logical-model/` |

**Change impact:** `none downstream` — `agg_borough_flow_monthly` is a new leaf. No existing model's SQL, properties or contract changes; `agg_od_flow_matrix` and its 25-trip floor are untouched. `fct_trip` and `dim_zone` are read, not changed. The one shared file that changes is `transformation/models/marts/agg/_agg.yml`, which gains one model entry and no edits to any existing entry. `/data/cache` is not read: the dbt card's `## Defer` says no production manifest is published for this Domain.

## Tasks

### Task 1: `agg_borough_flow_monthly`, its tests and its proposed contract

**Requirements:** `R-01` … `R-06`, `R-08` · **Design:** `docs/design/models/agg/agg_borough_flow_monthly.md` · **Skill:** `data-contract` for the contract, then `generating-dbt-model` · **Depends on:** none

- [ ] Author `contracts/agg/agg_borough_flow_monthly.odcs.yaml` with `data-contract`, `status: proposed`, `version: 1.0.0`: the relation `agg.agg_borough_flow_monthly`, `primaryKey` on the three grain columns (`trip_month` position 1, `origin_borough` position 2, `dest_borough` position 3), `dataGranularityDescription` stating the zero-filled borough grid, and every column the design names — `trip_month` (date/DATE), `origin_borough` (string/VARCHAR), `dest_borough` (string/VARCHAR), `is_intra_borough` (boolean/BOOLEAN), `trip_count` (integer/BIGINT), `total_revenue` (number/DOUBLE), `cross_borough_trip_count` (integer/BIGINT), `origin_trip_count` (integer/BIGINT), `cross_borough_trip_share` (number/DOUBLE) — each with a description stating its rule, `required: true` on every column except the share, whose null case is the empty-origin rule. Run `python3 .agents/skills/data-contract/scripts/odcs.py check`; expect exit 0, with no finding naming this contract.
- [ ] Author `transformation/models/marts/agg/agg_borough_flow_monthly.sql` in the shape the design fixed: `window_months` (distinct `dim_date.month_start_date` inside `in_report_window`), `boroughs` (distinct `dim_zone.borough_name`), `spine` (their two cross joins), `trips` (billable, in window, `dim_zone` inner-joined twice on `pickup_zone_key` and `dropoff_zone_key`, `dim_date` joined on `pickup_date_key`, carrying `total_amount`), `pair_totals` (trips grouped to the grain), `origin_totals` (`count(*)` and `count(*) filter (where origin_borough <> dest_borough)` per month and origin), then the spine left-joined to both with `coalesce(..., 0)` and `safe_divide('o.cross_borough_trip_count', 'o.origin_trip_count')`. Every output cast to its contract type. A pair with no trips shows `trip_count = 0` and `total_revenue = 0`; the share is the origin's value, `0` when the origin had trips but none crossed and null when it had none at all.
- [ ] Author the model's `_agg.yml` entry with the description and the column list (`contract: {enforced: true}` and every `data_type` come from `generate` in Task 2, not from hand).
- [ ] Author the unit test `borough_flow_zero_fills_pairs_and_publishes_the_origin_share` in `transformation/models/marts/agg/_unit_tests.yml` with `given` rows for `dim_date`, `dim_zone` and `fct_trip` covering: a crossing pair, a self pair, a pair with no trips, an origin with trips but none crossing (share `0`), an origin with no trips at all (share null), and three rows that must stay outside the counts — a non-billable trip, an out-of-window trip and a trip whose dropoff zone key resolves to no zone.
- [ ] Author the five singular tests, each returning the violating rows:
  - `transformation/tests/assert_borough_flow_grid_is_complete.sql` — the window months × 8 boroughs × 8 boroughs against the table in both directions, so a missing or an extra grain combination shows.
  - `transformation/tests/assert_borough_flow_one_row_per_grain.sql` — `group by trip_month, origin_borough, dest_borough having count(*) > 1`.
  - `transformation/tests/assert_borough_flow_covers_every_resolved_trip.sql` — `sum(trip_count)` and `round(sum(total_revenue), 2)` against an independently aggregated `fct_trip` (billable, in window, both zone keys non-null), using `is distinct from` so an empty table fails rather than passes.
  - `transformation/tests/assert_borough_flow_share_matches_its_denominator.sql` — recomputes the share from the row's own numerator and denominator, checks one share value per origin and month, and reconciles both columns with an independent aggregation of `fct_trip` and `dim_zone`.
  - `transformation/tests/assert_borough_flow_zero_rows_are_zero.sql` — a zero-trip row carries zero revenue, a positive-trip row carries positive revenue, a pair count never exceeds its origin total, and the share's null-ness matches its denominator.
- [ ] Run `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit`; expect the model and all five singular tests to pass, the model reporting 192 rows, and no failure in the rest of the selection.
- [ ] Run `cd transformation && dbt test --select agg_borough_flow_monthly,test_type:unit`; expect the unit test to pass.
- [ ] Run `python3 .agents/skills/data-contract/scripts/odcs.py check`; expect exit 0.
- [ ] Commit and push the model, its `_agg.yml` entry, its `_unit_tests.yml` unit test, the five singular tests, and the proposed contract.

### Task 2: the semantic-layer source, the contract's activation and the ontology re-run

**Requirements:** `R-07` · **Design:** `docs/design/models/agg/agg_borough_flow_monthly.md` (`## Logical Model`) · **Skill:** `semantic-model`, then `data-contract` for the activation · **Depends on:** Task 1

- [ ] Add `LTS10_borough_flow_monthly` to the `trips` dataset's `logical_sources` in `logical-model/nyc_taxi_analytics.ossie.yaml`, `priority_group: 0`: `physical_table: agg_borough_flow_monthly`, `content_grain: ["trip_month", "origin_borough", "dest_borough"]`, `column_map` binding `billable_trip_count` to `trip_count` and `billable_revenue` to `total_revenue`, `content_levels` naming `trips_to_date` at `month` on `trip_month`, `trips_to_pickup_zone` at `borough` on `origin_borough`, and `trips_to_dropoff_zone` at `borough` on `dest_borough`, and a `content_filter` stating the model's window and its two inner joins as literals bounded by the dbt vars' dates. Its `note` names `assert_semantic_content_holds` and refuses `origin_trip_count`, `cross_borough_trip_count`, `cross_borough_trip_share` and `is_intra_borough`, each with why.
- [ ] Set `contracts/agg/agg_borough_flow_monthly.odcs.yaml` to `status: active` and write its enforcement keys with `python3 .agents/skills/data-contract/scripts/odcs.py generate`; re-read the `_agg.yml` entry it wrote.
- [ ] Regenerate the Ossie tests with `python3 .agents/skills/semantic-model/scripts/ossie.py generate-tests logical-model/ transformation/tests`; never edit them by hand.
- [ ] Run the structural gates, expecting exit 0 from each: `python3 .agents/skills/semantic-model/scripts/ossie.py validate logical-model/`, `python3 .agents/skills/semantic-model/scripts/ossie.py coverage logical-model/ transformation/models/marts/` (with `--exclude` for each relation `repo-map.json` lists under `semantic_exclusions`), `python3 .agents/skills/semantic-model/scripts/ossie.py suppliers logical-model/`, `python3 .agents/skills/semantic-model/scripts/ossie.py notes logical-model/ transformation/tests docs/adr/`, and `python3 .agents/skills/semantic-model/scripts/ossie.py generate-tests logical-model/ transformation/tests --check`.
- [ ] Run `python3 .agents/skills/semantic-model/scripts/ossie.py refs ontology/nyc_taxi.ontology.yaml logical-model/`; expect exit 0.
- [ ] Run `python3 .agents/skills/data-contract/scripts/odcs.py check --relations`; expect exit 0 with no `relations/mismatch` and no `boundary/undeclared`.
- [ ] Run `cd transformation && dbt build --select +agg_borough_flow_monthly+ --exclude test_type:unit`; expect pass at the active, enforced contract with the regenerated content test in the selection.
- [ ] Load `validating-semantic-model` and `validating-data-contract` and record their reports.
- [ ] Commit and push `logical-model/nyc_taxi_analytics.ossie.yaml`, the regenerated tests, the activated contract, and the generated `_agg.yml` keys.

## Execution evidence
