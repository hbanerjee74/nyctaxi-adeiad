-- The grain is one row per month, origin borough and destination borough.
select
    trip_month,
    origin_borough,
    dest_borough,
    count(*) as row_count
from {{ ref('agg_borough_flow_monthly') }}
group by 1, 2, 3
having count(*) > 1
