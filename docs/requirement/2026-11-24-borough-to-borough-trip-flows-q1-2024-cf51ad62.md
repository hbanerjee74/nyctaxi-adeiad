---
kinds: [transformation]
---

# Requirement: Borough-to-borough trip flows Q1 2024

## Ask

Leila Haddad (Mobility Planning Lead) reports for the city: "The city asked how much of our traffic crosses borough lines. For each month of Q1 2024, I need the trips and the revenue from each borough to each borough, and the share of trips that leave the borough they started in." The result is a new table in this project that a mobility-planning reader consumes directly.

## Requirements

- [ ] `R-01` One boundary table at month × origin borough × destination borough grain covering Q1 2024, every borough pair present in every month — accept when the built relation has exactly 192 rows (3 months × 8 boroughs × 8 boroughs) and a uniqueness test passes on `(trip_month, origin_borough, dest_borough)` — source: request, answer on `row_set`
- [ ] `R-02` Each row carries the billable trips from origin borough to destination borough in that month — accept when, summed over all rows, `trip_count` equals the 95,958 billable trips of the Q1 2024 window in `fct_trip` whose pickup and dropoff zone keys resolve to a zone, a figure recomputed independently of the table — source: `docs/adr/0003-billable-trip-definition-and-where-it-applies.md`, "Gold marts that report revenue or flows apply it, inside the reporting window"
- [ ] `R-03` Each row carries the revenue of those trips as the sum of `total_amount` over billable trips, no payment method excluded — accept when, per origin borough and month, the table's summed revenue equals an independently computed `sum(total_amount)` from `fct_trip`, and the quarter's total is 2,629,185.82 — source: answer on `revenue_def`, `docs/adr/0013-no-charge-and-dispute-payments-are-not-excluded-by-the-billable-rule.md`
- [ ] `R-04` Each row carries its origin borough's share of trips that leave that borough, repeated on every row of the same origin and month, and null where the borough had no billable trip that month — accept when the column equals cross-borough trips ÷ that borough's billable trips for every origin and month, checked against an independent recomputation, and every row of one origin and month carries one value — source: answer on `share_def`
- [ ] `R-05` A borough pair with no billable trip in a month is published as a row of zeros, never omitted — accept when the row count of `R-01` holds with no pair missing, and each zero row's `trip_count` and revenue are exactly 0 — source: answer on `row_set`, `docs/adr/0018-borough-flows-report-every-pair-and-publish-no-25-trip-floor.md`
- [ ] `R-06` The trip rows excluded from the table are the ones with no resolving borough and nothing else — accept when, in Q1 2024, that count is 0 (measured: `fct_trip` has 0 null pickup and 0 null dropoff zone keys across 95,958 billable trips), so `R-02`'s reconciliation closes with no residual — source: answer on `null_borough`
- [ ] `R-07` The table is a boundary relation with an enforced dbt contract, its design record, an ODCS contract and its semantic-layer binding — accept when `dbt build` on the selection passes, `validating-data-contract` and `validating-semantic-model` report no findings, and the relation is either bound in an Ossie document or listed in `semantic_exclusions` with its reason — source: `repo-map.json`, which declares `agg` a `boundary` layer and places every gold relation under contract
- [ ] `R-08` The unresolved borough values (`Unknown`, `N/A`) reach the table as their own origin and destination groups, and `EWR` with them, because the dimension holds them as real boroughs — accept when the table's borough list equals the 8 distinct `dim_zone.borough_name` values and no group is filtered out — source: `docs/adr/0012-unresolved-zones-are-retained-and-flagged.md`, "a borough rollup includes an unresolved group unless its consumer filters"

## Business decisions

| Decision | Value | Source |
| --- | --- | --- |
| Grain of the new table | One row per month × origin borough × destination borough; month is the calendar month of the trip's pickup date | request; `CONTEXT.md` "Trips are reported on the day they started" |
| Edge periods | Not applicable: the Q1 2024 window's first and last days are 2024-01-01 and 2024-03-31, and all three months are complete in the data (31, 29 and 31 calendar days carry trips), so no period is cut short | query over `core.fct_trip` — 31/29/31 distinct pickup dates per month |
| Population: which trips count | Billable trips (positive total) inside the reporting window, as every revenue and flow mart does | `docs/adr/0003-...`, the same ADR's list of marts |
| Revenue measure | Sum of `total_amount` over those trips; no-charge and dispute payments included | answer on `revenue_def`; ADR 0013 |
| Row set | Every borough pair every month, zero-filled; the 25-trip floor of ADR 0017 is not applied at borough grain | answer on `row_set`; `docs/adr/0018-...` |
| Cross-borough share | Per origin borough: cross-borough trips ÷ all that borough's billable trips that month, repeated on each of its rows | answer on `share_def` |
| NULLs in the revenue measure | Not applicable: a billable trip has a positive total by definition, and the window holds 0 null and 0 zero totals among its 95,958 billable trips | definition of billable, ADR 0003; query over `core.fct_trip` |
| Revenue coverage column | Not applicable: no billable trip lacks the measure, so a coverage count would repeat `trip_count` | ADR 0003 definition; measured 0 nulls |
| Reuse | Build from `fct_trip` with `dim_zone` joined twice; no published model serves borough × borough × month, and `agg_od_flow_matrix` cannot serve it because its floor removes pairs | code of `agg_od_flow_matrix`, `agg_trip_zone_daypart_dow`, `mart_daily_zone_revenue`; ADR 0018 |
| Unmatched and null keys | Every billable trip in the window resolves on both zone joins (0 unresolved), so an inner join keeps every row; the measure is the trips that do resolve | queries over `core.fct_trip` and `core.dim_zone`; answer on `null_borough` |
| Borough groups published | All 8 `dim_zone.borough_name` values, including `EWR`, `Unknown` and `N/A` | ADR 0012 |
| Extended scope | Not a question: no schedule, no new source | transformation playbook |

## Out of scope

- Any change to `fct_trip`, `dim_zone` or another published model; `agg_od_flow_matrix` and its 25-trip floor stay as they are.
- Zone-grain or daypart-grain versions of this flow.
- A schedule or orchestration item; the table is built by the project's normal `dbt build`.
- Statistical significance, normalisation by population or distance: the ask is trips, revenue and a share.

## Open questions

None. Every branch the transformation playbook asks about is settled above; the design questions (materialisation, the Ossie document placement, whether the table extends an existing star) are for the design stop.

## Approvals
- 2026-11-24T08:13:56Z — requirement approved — "Approve, continue to design" — 7c62db00345130ea493261734067f17575ab0f5d
- 2026-11-24T08:26:37Z — design approved — "Approve, continue to planning" — 1fe8854ad5220db02fd677eac34076116f9b0cbd
