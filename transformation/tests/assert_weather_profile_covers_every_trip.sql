-- Every in-window trip lands in exactly one borough-day of the weather profile,
-- including trips in unresolved or non-weather boroughs, which keep their row
-- with null weather rather than being dropped (ADR 0012).
with profile as (
    select sum(trip_count) as trips
    from {{ ref('agg_weather_demand_daily') }}
),

fact as (
    select count(*) as trips
    from {{ ref('fct_trip') }}
    where {{ in_report_window('pickup_datetime') }}
)

select p.trips as profile_trips, f.trips as fact_trips
from profile p
cross join fact f
where p.trips != f.trips
