{{ config(materialized='table') }}

-- Yellow-only columns that conforming drops. Recomputes the trip natural key so
-- the fleet-specific fee can be rejoined to a trip.
--
-- Bronze is not deduplicated, so the same natural key can appear more than
-- once; taking the first occurrence keeps this one-row-per-trip and stops the
-- rejoin multiplying the fact.
select
    trip_key,
    airport_fee,
    pickup_location_id,
    pickup_datetime
from (
    select
        {{ trip_natural_key("'yellow'", 'y.vendor_id', 'y.pickup_datetime',
           'y.dropoff_datetime', 'y.pickup_location_id', 'y.dropoff_location_id',
           'y.trip_distance', 'y.total_amount') }}       as trip_key,
        y.airport_fee,
        y.pickup_location_id,
        y.pickup_datetime,
        row_number() over (
            partition by {{ trip_natural_key("'yellow'", 'y.vendor_id', 'y.pickup_datetime',
               'y.dropoff_datetime', 'y.pickup_location_id', 'y.dropoff_location_id',
               'y.trip_distance', 'y.total_amount') }}
            order by y._dlt_load_id
        )                                                 as dup_rank
    from {{ ref('stg_tlc__yellow_tripdata') }} y
) d
where dup_rank = 1
