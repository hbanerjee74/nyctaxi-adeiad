{{ config(materialized='table') }}

-- Green-only columns dropped when conforming (ADR 0006). Same natural-key
-- reconstruction as the yellow side, and the same first-occurrence rule.
select
    trip_key,
    ehail_fee,
    trip_type,
    pickup_datetime
from (
    select
        {{ trip_natural_key("'green'", 'g.vendor_id', 'g.pickup_datetime',
           'g.dropoff_datetime', 'g.pickup_location_id', 'g.dropoff_location_id',
           'g.trip_distance', 'g.total_amount') }}       as trip_key,
        g.ehail_fee,
        g.trip_type,
        g.pickup_datetime,
        row_number() over (
            partition by {{ trip_natural_key("'green'", 'g.vendor_id', 'g.pickup_datetime',
               'g.dropoff_datetime', 'g.pickup_location_id', 'g.dropoff_location_id',
               'g.trip_distance', 'g.total_amount') }}
            order by g._dlt_load_id
        )                                                 as dup_rank
    from {{ ref('stg_tlc__green_tripdata') }} g
) d
where dup_rank = 1
