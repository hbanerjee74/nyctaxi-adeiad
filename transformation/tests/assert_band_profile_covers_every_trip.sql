-- Every in-window trip appears in the band profile exactly once, including the
-- ones no band covers: a refund (negative total) or a negative duration is
-- 'unbanded', never dropped. ADR 0004 keeps every trip, so the profile's
-- trip_count must sum to the fact's.
with profile as (
    select sum(trip_count) as trips
    from {{ ref('agg_trip_band_profile') }}
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
