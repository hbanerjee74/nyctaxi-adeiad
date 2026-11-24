-- Every billable trip of the window whose pickup and dropoff zones resolve is
-- counted once in the table (R-02, R-06), and its revenue is the sum of
-- total_amount over those trips (R-03). The fact side is aggregated from
-- fct_trip alone -- billable, inside the window, both zone keys present -- so a
-- dropped or double-counted trip shows here. Money is compared at the cent;
-- `is distinct from` fails on an empty table instead of passing on a null.
with published as (
    select
        sum(trip_count) as trip_count,
        round(sum(total_revenue), 2) as total_revenue
    from {{ ref('agg_borough_flow_monthly') }}
),

fact as (
    select
        count(*) as trip_count,
        round(sum(total_amount), 2) as total_revenue
    from {{ ref('fct_trip') }}
    where
        {{ in_report_window('pickup_datetime') }}
        and is_billable
        and pickup_zone_key is not null
        and dropoff_zone_key is not null
)

select
    p.trip_count as published_trips,
    f.trip_count as fact_trips,
    p.total_revenue as published_revenue,
    f.total_revenue as fact_revenue
from published p
cross join fact f
where
    p.trip_count is distinct from f.trip_count
    or p.total_revenue is distinct from f.total_revenue
