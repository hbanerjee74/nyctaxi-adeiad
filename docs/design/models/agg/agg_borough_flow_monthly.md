---
artifacts: [agg_borough_flow_monthly]
---

# agg_borough_flow_monthly

Trips and revenue from each pickup borough to each dropoff borough, by month, with the origin borough's share of trips that leave it.

## Grain

One row per calendar month × origin borough × destination borough, every borough pair present in every month of the reporting window. The alternatives — only pairs with at least one trip, and applying the 25-trip floor per month — were rejected in ADR 0018 and in the Requirement's `row_set` answer.

## Schema

- `transformation/models/marts/agg/`: `agg` (default). Source: requirement `R-07`, user answer on `schema_choice`.

## Decisions

- `D-01` Materialise as a `table` in `agg`, matching every other model in the folder; the relation is `agg.agg_borough_flow_monthly`. Source: `transformation/dbt_project.yml` `marts.agg` settings.
- `D-02` Month is taken from the calendar, not from the trip's own arithmetic: the spine's months are `dim_date.month_start_date`, and a trip's month is the `month_start_date` of its `pickup_date_key`. The calendar is the Domain's declaration of where a month begins, and it already carries the reporting window. Source: `R-01`, `CONTEXT.md` "Date" and `dim_date`.
- `D-03` Build the row set as a cross join of the window's months with the distinct `dim_zone.borough_name` values, twice, then left join the trips. Every published borough pair therefore exists whether or not it carried a trip, which is what ADR 0018 requires, and the borough list comes from the dimension rather than being inferred from the trips. Source: `R-05`, [ADR 0018](../../../adr/0018-borough-flows-report-every-pair-and-publish-no-25-trip-floor.md).
- `D-04` Population: billable trips (ADR 0003) inside the reporting window, with `dim_zone` inner-joined twice. An inner join is a filter, and it keeps exactly the trips whose pickup and dropoff zone keys resolve; those are the trips a borough pair can place. The Verification records how many that drops today. Source: `R-02`, `R-06`, [ADR 0003](../../../adr/0003-billable-trip-definition-and-where-it-applies.md).
- `D-05` Revenue is `sum(f.total_amount)` over the row's billable trips, with no payment method excluded, so a no-charge or disputed trip with a positive total is inside it. Source: `R-03`, `revenue_def` answer, [ADR 0013](../../../adr/0013-no-charge-and-dispute-payments-are-not-excluded-by-the-billable-rule.md).
- `D-06` The share of trips that leave a borough is computed per origin borough and month and repeated on each of that borough's destination rows: cross-borough trips divided by all that borough's billable trips, through `safe_divide`, so an origin with no trips yields null rather than a measured zero. Source: `R-04`, `share_def` answer, [ADR 0016](../../../adr/0016-rates-are-rebuilt-from-summed-numerators-and-denominators.md).
- `D-07` Publish the denominator beside the share as `origin_trip_count`, the origin borough's billable trips that month, repeated on its rows, so the share can be recomputed from the row alone without a second query. Source: `R-04`, [ADR 0016](../../../adr/0016-rates-are-rebuilt-from-summed-numerators-and-denominators.md) "A new aggregate carries its numerators and denominators".
- `D-08` Carry `is_intra_borough` (origin borough equals destination borough) on every row, because the self-pairs are half of what makes the grid readable and a reader who has to derive it will get the null case wrong. Source: `R-01`, `CONTEXT.md` "Cross-borough trip".
- `D-09` Build from `fct_trip` with `dim_zone` joined twice rather than from `agg_od_flow_matrix`: the published matrix is cut by its 25-trip floor (ADR 0017), so rolling it up would lose exactly the pairs and trips this table must publish. No other published model sits at or below this grain. Source: `R-02`, `reuse` decision, [ADR 0017](../../../adr/0017-published-flows-have-a-25-trip-floor.md).
- `D-10` Publish every `dim_zone.borough_name` value as a real group, including `EWR` and the unresolved `Unknown` and `N/A`, and filter none of them: the glossary says an unresolved zone pollutes a borough rollup unless its consumer filters, and the consumer here is the city, who is owed the trips that exist. Source: `R-08`, [ADR 0012](../../../adr/0012-unresolved-zones-are-retained-and-flagged.md).
- `D-11` Route the relation to the semantic layer as an aggregate logical source of the `trips` dataset, mapping `trip_count` to `billable_trip_count` and `total_revenue` to `billable_revenue`, with `content_levels` on the month and on both zone roles at the borough level. This follows `agg_weather_demand_daily`, the existing spine-fed borough aggregate, which is mapped the same way. The share and the denominator are refused in the source's `note` because a precomputed rate column is refused on every source and `origin_trip_count` has no metric; `is_intra_borough` is refused for want of a metric. Source: `R-07`, `semantic_exclusions` absences, `agg_weather_demand_daily`'s mapping in `logical-model/nyc_taxi_analytics.ossie.yaml`.
- `D-12` The relation is on the contract boundary and carries an ODCS contract drafted `status: proposed` until the table is first built, then set `active`. Source: `R-07`, `repo-map.json` `contracts` and `layers.agg.role`.

## Logical Model

```yaml
documents:
  - logical-model/nyc_taxi_analytics.ossie.yaml
datasets: []
metrics: []
logical_sources:
  - LTS10_borough_flow_monthly: added
```

`logical-model/nyc_taxi_analytics.ossie.yaml` gains one aggregate logical source on its existing `trips` dataset; no dataset, metric or relationship is added or changed, and no new document is written, because the table's rows are the star's at a coarser grain and both zone roles and the month already exist there. `ontology/nyc_taxi_analytics.mapping.yaml` maps the `Trip` and `Zone` concepts through `trips.*` and `zone.*` expressions that this change does not move, so no concept is added and no mapping changes; the ontology `refs` gate is re-run because the document edits.

## Rejected

- Building from `agg_od_flow_matrix` — its 25-trip floor is exactly the cut this table must not have.
- Deriving the borough list from the trips — a month in which a borough carried nothing would then silently lose all eight of its rows.
- Publishing the share as a per-row slice of the origin's traffic — answered at `share_def`: the city asked how much traffic crosses a line, which is one number per borough.
- Filling the zero rows in the semantic-layer mapping only — the table is what a reader queries, and a hole there is a hole.

## Consumers

- Mobility Planning, reading the table directly for the city's question; no model in this repository reads it.
- The semantic layer: `trips` dataset aggregate source, reachable for `billable_trip_count` and `billable_revenue` at month × origin borough × destination borough.

## History

- 2026-11-24 — new-intent-cf51ad62 — design record written — D-01 … D-12 — terms: added Borough flow, Cross-borough trip
