# Data slice: The trip fact

Supporting design evidence for [`docs/requirement/2026-08-29-the-trip-fact.md`](../../requirement/2026-08-29-the-trip-fact.md) `R-01@1` to `R-06@1`. Reconstructed against the seeded Domain (January 2024) for demonstration; the counts are January's, not the three-month load the design records quote.

## fct_trip (with int_trips_conformed, int_trips_enriched, int_trip_quality_flags)

**Requirements:** `R-01@1`, `R-02@1`, `R-03@1`, `R-04@1`, `R-05@1`, `R-06@1`.

**Candidate input.** `bronze.yellow_tripdata` and `bronze.green_tripdata` through their staging views, conformed in `int_trips_conformed`. No existing table is at the trip grain across both fleets, so the conformed intermediate is the build input; bronze is read again only for the fleet-specific extras.

**Profiling** (`lakehouse_query`, target `domain`):

| Probe | Result |
| --- | --- |
| Bronze rows | yellow 2,964,624; green 56,551 |
| Conformed trips by fleet | yellow 2,964,624 (2,964,624 distinct `trip_key`); green 56,551 (56,551 distinct) |
| Bronze rows lost or added by conforming | 0 |
| `fct_trip` rows and distinct keys | 3,021,175 and 3,021,175 |
| Billable / not billable | 2,985,029 / 36,146 |
| Pickups outside January | 20 (earliest 2002-12-31, latest 2024-02-01 00:01) |
| Null pickup zone, dropoff zone, vendor | 5, 5, 5 (pickup timestamps before any zone or vendor version) |
| Fleet-attributed trips | 147,434 |
| `airport_fee_status` | present 2,824,462; missing 140,162; not_applicable 56,551 |
| Zone versions / zones | 272 / 265 |

**Slice.** Complete table. January's 3,021,175 trips build in under a minute in the sandbox, so no sample is needed; the minority classes the requirements depend on (green trips, refunds, missing fees, unattributed trips, out-of-window and malformed pickups) are all present in full.

**Joins.**

| Join | Expectation | Evidence |
| --- | --- | --- |
| Conformed trip → yellow or green extras on `trip_key` | Mandatory one-to-one within the fleet | `assert_enrichment_rejoin_matches_every_trip` returns no rows |
| Trip → `dim_zone` (pickup, dropoff) as of pickup date | Many-to-one, optional at the 5 malformed timestamps | `relationships` tests; `assert_scd2_zone_intervals_do_not_overlap` |
| Trip → `dim_vendor` as of pickup date | Many-to-one, optional at the same 5 | `relationships` test |
| Trip → `stg_ops__trip_assignments` | Optional many-to-one: 147,434 of 3,021,175 trips | `is_fleet_attributed` agrees with driver, vehicle and shift in every row |

**Export shape.** `select * from intermediate.int_trips_conformed` plus the two extras views, no filter: the requirement keeps every trip (`R-01@1`, `R-03@1`).

**Findings.**

- Confirms `R-01@1`: no trip is lost or added between bronze, conformed and the fact.
- Confirms `R-02@1`: every conformed trip finds its fleet's extras row.
- Supporting detail: the 5 malformed pickups keep null zone and vendor keys and stay in the fact, as `R-03@1` and ADR 0015 require.
- Supporting detail: 20 pickups fall outside the month; the fact keeps them and the marts' reporting window excludes them.

**Readiness:** ready.
