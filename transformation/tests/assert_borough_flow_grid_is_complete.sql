-- The published grid is every month of the window crossed with every borough of
-- the zone dimension, twice, and nothing else (ADR 0018). A missing row is a
-- pair silently dropped; an extra row is a pair the dimension does not know.
-- Both sides of the full outer join are built from the calendar and the
-- dimension here, never from the table's own rows.
with expected as (
    select
        m.month_start_date as trip_month,
        o.borough_name as origin_borough,
        d.borough_name as dest_borough
    from (select distinct month_start_date from {{ ref('dim_date') }} where {{ in_report_window('calendar_date') }}) m
    cross join (select distinct borough_name from {{ ref('dim_zone') }}) o
    cross join (select distinct borough_name from {{ ref('dim_zone') }}) d
),

actual as (
    select trip_month, origin_borough, dest_borough
    from {{ ref('agg_borough_flow_monthly') }}
)

select
    'missing from the table' as violation,
    e.trip_month,
    e.origin_borough,
    e.dest_borough
from expected e
left join actual a
    on
        e.trip_month = a.trip_month
        and e.origin_borough = a.origin_borough
        and e.dest_borough = a.dest_borough
where a.trip_month is null

union all

select
    'not in the grid' as violation,
    a.trip_month,
    a.origin_borough,
    a.dest_borough
from actual a
left join expected e
    on
        e.trip_month = a.trip_month
        and e.origin_borough = a.origin_borough
        and e.dest_borough = a.dest_borough
where e.trip_month is null
