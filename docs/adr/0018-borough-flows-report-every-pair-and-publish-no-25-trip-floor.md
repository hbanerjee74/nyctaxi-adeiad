---
status: decided
date: 2026-11-24
---

# A borough flow reports every borough pair, zero-filled, with no trip floor

The 25-trip floor of ADR 0017 is a rule about zone pairs. It exists because the 265 × 265 zone grid is almost entirely ones and twos, so a reader cannot tell a corridor from a rounding. Borough grain is a different population: across the eight borough values in `dim_zone` there are 64 possible origin-destination pairs a month, and the month's traffic concentrates in a few of them. Applying the floor there would delete real structure rather than noise — over Q1 2024 it drops 66 of the 122 observed borough pairs and 253 of 95,958 billable trips — and, worse, it would make a pair that happens to fall under 25 trips in a month indistinguishable from a pair that carried none. A borough rollup therefore reports every borough pair for every month, and a pair with no billable trip in that month is published as a row of zeros.

The share of trips that cross a borough line is measured per origin borough against all of that borough's billable trips, not against the sum of the published rows, so it stays correct whatever the row set is.

## Considered options

- **Apply the 25-trip floor per month** — rejected: it answers "which borough pairs are busy" when the question is "how much traffic crosses which lines", and its missing rows cannot be told apart from empty ones.
- **Publish only pairs with at least one trip** — rejected: a reader cannot distinguish "no trips this month" from "not reported", and a trend over a pair breaks whenever a thin month loses its row.
- **Publish every pair, zero-filled** (chosen): a fixed grid per month, so a share, a difference and a trend all have a denominator on every row.

## Consequences

- The relation carries every borough pair for every month in its window, and a row of zeros is a measurement, not a missing value.
- ADR 0017 is unaffected: `agg_od_flow_matrix` keeps its floor at zone grain, and a "published flow" is still a zone pair that clears it. A borough flow is a different, complete population and must not be read as a coarser published flow.
- Zero fill happens at the pair grain after the fact, so it can only be defended while the borough list is complete: the table cross-joins the borough list instead of inferring the grid from the trips.
- A share column exists beside the pair's trip count, because a zero-filled grid gives every row a trip count but not every row the same denominator.

## Affected designs

None yet: the code this decision governs lands with the intent that records it.
