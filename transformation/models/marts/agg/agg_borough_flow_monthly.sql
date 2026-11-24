-- Borough-to-borough flow, by calendar month.
--
-- The row set is the month x origin borough x destination borough grid, taken
-- from the calendar and the zone dimension rather than from the trips: a pair
-- that carried nothing in a month is a row of zeros, so "no trips" and "not
-- reported" stay distinguishable (ADR 0018). The 25-trip floor of ADR 0017 is
-- a zone-pair rule and is not applied here.
--
-- Both zone roles are the same dimension joined twice on the trip's own zone
-- keys, so a re-designation does not reassign history (ADR 0009). Population is
-- the billable trips of the window (ADR 0003), and revenue is their
-- total_amount with no payment method excluded (ADR 0013).
--
-- The share is the origin borough's cross-borough trips over all its billable
-- trips that month, through safe_divide, so it is one value per origin and
-- month repeated on that origin's rows and null when the borough carried
-- nothing (ADR 0016). Its denominator is published beside it.
with window_months as (
    select distinct month_start_date
    from {{ ref('dim_date') }}
    where {{ in_report_window('calendar_date') }}
),

boroughs as (
    select distinct borough_name
    from {{ ref('dim_zone') }}
),

spine as (
    select
        m.month_start_date as trip_month,
        o.borough_name as origin_borough,
        d.borough_name as dest_borough
    from window_months m
    cross join boroughs o
    cross join boroughs d
),

trips as (
    select
        dd.month_start_date as trip_month,
        oz.borough_name as origin_borough,
        dz.borough_name as dest_borough,
        f.total_amount
    from {{ ref('fct_trip') }} f
    join {{ ref('dim_zone') }} oz on f.pickup_zone_key = oz.zone_key
    join {{ ref('dim_zone') }} dz on f.dropoff_zone_key = dz.zone_key
    join {{ ref('dim_date') }} dd on f.pickup_date_key = dd.date_key
    where
        {{ in_report_window('f.pickup_datetime') }}
        and f.is_billable
),

pair_totals as (
    select
        trip_month,
        origin_borough,
        dest_borough,
        count(*) as trip_count,
        sum(total_amount) as total_revenue
    from trips
    group by 1, 2, 3
),

origin_totals as (
    select
        trip_month,
        origin_borough,
        count(*) as origin_trip_count,
        count(*) filter (where origin_borough <> dest_borough) as cross_borough_trip_count
    from trips
    group by 1, 2
)

select
    cast(s.trip_month as date) as trip_month,
    cast(s.origin_borough as varchar) as origin_borough,
    cast(s.dest_borough as varchar) as dest_borough,
    cast(s.origin_borough = s.dest_borough as boolean) as is_intra_borough,
    cast(coalesce(p.trip_count, 0) as bigint) as trip_count,
    cast(coalesce(p.total_revenue, 0) as double) as total_revenue,
    cast(coalesce(o.cross_borough_trip_count, 0) as bigint) as cross_borough_trip_count,
    cast(coalesce(o.origin_trip_count, 0) as bigint) as origin_trip_count,
    cast({{ safe_divide('o.cross_borough_trip_count', 'o.origin_trip_count') }} as double)
        as cross_borough_trip_share
from spine s
left join pair_totals p
    on
        s.trip_month = p.trip_month
        and s.origin_borough = p.origin_borough
        and s.dest_borough = p.dest_borough
left join origin_totals o
    on s.trip_month = o.trip_month and s.origin_borough = o.origin_borough
order by 1, 2, 3
