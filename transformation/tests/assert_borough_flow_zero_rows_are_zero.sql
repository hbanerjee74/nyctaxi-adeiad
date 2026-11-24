-- A zero-filled row is a measurement of nothing, not a hole: no trips means no
-- revenue, and the row's own counts are zero. `cross_borough_trip_count` and
-- `origin_trip_count` are the origin borough's figures repeated on the row, so
-- they are checked against the row's pair count and against the share's null
-- rule rather than against the row itself (design D-07, ADR 0016).
with zero_rows as (
    select trip_month, origin_borough, dest_borough, total_revenue, cross_borough_trip_count, origin_trip_count
    from {{ ref('agg_borough_flow_monthly') }}
    where trip_count = 0
),

positive_rows as (
    select trip_month, origin_borough, dest_borough, total_revenue, origin_trip_count, trip_count
    from {{ ref('agg_borough_flow_monthly') }}
    where trip_count > 0
),

share_null_rule as (
    select
        trip_month,
        origin_borough,
        dest_borough,
        cross_borough_trip_share,
        cross_borough_trip_count,
        origin_trip_count
    from {{ ref('agg_borough_flow_monthly') }}
)

select trip_month, origin_borough, dest_borough, 'zero-trip row carries revenue' as violation
from zero_rows
where total_revenue <> 0

union all

select trip_month, origin_borough, dest_borough, 'positive-trip row carries no revenue' as violation
from positive_rows
where total_revenue <= 0

union all

select trip_month, origin_borough, dest_borough, 'pair count exceeds its origin total' as violation
from positive_rows
where trip_count > origin_trip_count

union all

select trip_month, origin_borough, dest_borough, 'empty origin carries cross-borough trips' as violation
from share_null_rule
where origin_trip_count = 0 and cross_borough_trip_count <> 0

union all

select trip_month, origin_borough, dest_borough, 'share null-ness contradicts its denominator' as violation
from share_null_rule
where
    (origin_trip_count = 0) <> (cross_borough_trip_share is null)
