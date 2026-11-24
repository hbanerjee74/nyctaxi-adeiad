-- The share is recomputable from the row it sits on: cross-borough trips over
-- the origin borough's billable trips that month, through the same
-- zero-denominator rule as the model (ADR 0016). It is one value per origin
-- borough and month across that origin's destination rows, its numerator and
-- denominator are the origin's own figures rather than the row's pair count,
-- and both reconcile with an independent aggregation of fct_trip and dim_zone.
with recomputed as (
    select
        t.trip_month,
        t.origin_borough,
        t.dest_borough,
        t.cross_borough_trip_share as actual,
        t.cross_borough_trip_count as numerator,
        t.origin_trip_count as denominator,
        case when coalesce(t.origin_trip_count, 0) = 0 then null
             else t.cross_borough_trip_count / t.origin_trip_count::double end as expected
    from {{ ref('agg_borough_flow_monthly') }} t
),

rate_mismatch as (
    select trip_month, origin_borough, dest_borough, 'share does not match its columns' as violation
    from recomputed
    where actual is distinct from expected
),

one_value_per_origin as (
    select trip_month, origin_borough, dest_borough, 'origin and month carry more than one share' as violation
    from (
        select
            trip_month,
            origin_borough,
            count(distinct cross_borough_trip_share) as share_values,
            min(dest_borough) as dest_borough
        from {{ ref('agg_borough_flow_monthly') }}
        group by 1, 2
        having count(distinct cross_borough_trip_share) > 1
    ) x
),

independent as (
    select
        dd.month_start_date as trip_month,
        oz.borough_name as origin_borough,
        count(*) as origin_trip_count,
        count(*) filter (where oz.borough_name <> dz.borough_name) as cross_borough_trip_count
    from {{ ref('fct_trip') }} f
    join {{ ref('dim_zone') }} oz on f.pickup_zone_key = oz.zone_key
    join {{ ref('dim_zone') }} dz on f.dropoff_zone_key = dz.zone_key
    join {{ ref('dim_date') }} dd on f.pickup_date_key = dd.date_key
    where {{ in_report_window('f.pickup_datetime') }} and f.is_billable
    group by 1, 2
),

column_mismatch as (
    select distinct
        t.trip_month,
        t.origin_borough,
        t.dest_borough,
        'numerator or denominator does not match the trips' as violation
    from {{ ref('agg_borough_flow_monthly') }} t
    left join independent i
        on t.trip_month = i.trip_month and t.origin_borough = i.origin_borough
    where
        t.origin_trip_count is distinct from coalesce(i.origin_trip_count, 0)
        or t.cross_borough_trip_count is distinct from coalesce(i.cross_borough_trip_count, 0)
)

select * from rate_mismatch
union all
select * from one_value_per_origin
union all
select * from column_mismatch
