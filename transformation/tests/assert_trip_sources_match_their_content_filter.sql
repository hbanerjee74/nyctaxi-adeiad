-- Each trip aggregate's content_filter in logical-model/nyc_taxi_analytics.ossie.yaml
-- claims two things: every row of the source satisfies the predicate, and the
-- source holds every detail row that does. An engine relies on both when it
-- answers a trip metric from the aggregate instead of fct_trip, so this test
-- rebuilds each bound total from fct_trip under the same predicate, written in
-- the model's logical fields rather than through the marts' own macro.
--
-- The OD matrix is floored (ADR 0017), so it cannot equal the filtered detail in
-- total. It is held group by group instead: every published group equals the
-- detail rows that share its grouping values.
with detail as (
    select *
    from {{ ref('fct_trip') }}
    where
        pickup_date >= date '{{ var("report_start") }}'
        and pickup_date < date '{{ var("report_end") }}'
),

detail_totals as (
    select
        count(*) filter (
            where pickup_zone_key is not null
        ) as zone_day_trips,
        count(*) filter (
            where
            pickup_zone_key is not null
            and pickup_date_key is not null
            and daypart_code is not null
            and pickup_hour is not null
        ) as daypart_dow_trips,
        count(*) filter (
            where
            is_billable
            and pickup_zone_key is not null
            and pickup_date_key is not null
            and daypart_code is not null
            and pickup_hour is not null
        ) as daypart_dow_billable_trips,
        count(*) filter (
            where is_billable and pickup_zone_key is not null
        ) as zone_revenue_trips,
        round(sum(total_amount) filter (
            where is_billable and pickup_zone_key is not null
        ), 2) as zone_revenue,
        count(*) filter (
            where is_billable and payment_method_key is not null
        ) as service_summary_trips,
        round(sum(total_amount) filter (
            where is_billable and payment_method_key is not null
        ), 2) as service_summary_revenue,
        count(*) filter (
            where trip_quality_key is not null
        ) as quality_trips
    from detail
),

zone_daily as (
    select sum(trip_count) as trips
    from {{ ref('agg_trip_zone_daily') }}
),

daypart_dow as (
    select
        sum(trip_count) as trips,
        sum(billable_trip_count) as billable_trips
    from {{ ref('agg_trip_zone_daypart_dow') }}
),

zone_revenue as (
    select
        sum(trip_count) as trips,
        round(sum(total_revenue), 2) as revenue
    from {{ ref('mart_daily_zone_revenue') }}
),

service_summary as (
    select
        sum(trip_count) as trips,
        round(sum(total_revenue), 2) as revenue
    from {{ ref('mart_monthly_service_summary') }}
),

quality as (
    select sum(trip_count) as trips
    from {{ ref('mart_trip_quality_scorecard') }}
),

bounds as (
    select
        'agg_trip_zone_daily.trip_count' as bound,
        s.trips as source_value,
        d.zone_day_trips as detail_value
    from zone_daily as s cross join detail_totals as d
    union all
    select
        'agg_trip_zone_daypart_dow.trip_count' as bound,
        s.trips as source_value,
        d.daypart_dow_trips as detail_value
    from daypart_dow as s cross join detail_totals as d
    union all
    select
        'agg_trip_zone_daypart_dow.billable_trip_count' as bound,
        s.billable_trips as source_value,
        d.daypart_dow_billable_trips as detail_value
    from daypart_dow as s cross join detail_totals as d
    union all
    select
        'mart_daily_zone_revenue.trip_count' as bound,
        s.trips as source_value,
        d.zone_revenue_trips as detail_value
    from zone_revenue as s cross join detail_totals as d
    union all
    select
        'mart_daily_zone_revenue.total_revenue' as bound,
        s.revenue as source_value,
        d.zone_revenue as detail_value
    from zone_revenue as s cross join detail_totals as d
    union all
    select
        'mart_monthly_service_summary.trip_count' as bound,
        s.trips as source_value,
        d.service_summary_trips as detail_value
    from service_summary as s cross join detail_totals as d
    union all
    select
        'mart_monthly_service_summary.total_revenue' as bound,
        s.revenue as source_value,
        d.service_summary_revenue as detail_value
    from service_summary as s cross join detail_totals as d
    union all
    select
        'mart_trip_quality_scorecard.trip_count' as bound,
        s.trips as source_value,
        d.quality_trips as detail_value
    from quality as s cross join detail_totals as d
),

od_detail as (
    select
        o.zone_natural_key as origin_location_id,
        o.zone_name as origin_zone,
        dz.zone_natural_key as dest_location_id,
        dz.zone_name as dest_zone,
        count(*) as trip_count,
        round(sum(f.total_amount), 2) as total_revenue
    from detail as f
    join {{ ref('dim_zone') }} as o on f.pickup_zone_key = o.zone_key
    join {{ ref('dim_zone') }} as dz on f.dropoff_zone_key = dz.zone_key
    where f.is_billable
    group by 1, 2, 3, 4
),

od_published as (
    select
        origin_location_id,
        origin_zone,
        dest_location_id,
        dest_zone,
        sum(trip_count) as trip_count,
        round(sum(total_revenue), 2) as total_revenue
    from {{ ref('agg_od_flow_matrix') }}
    group by 1, 2, 3, 4
)

select
    bound,
    source_value,
    detail_value
from bounds
where source_value is distinct from detail_value

union all

select
    'agg_od_flow_matrix ' || p.origin_location_id || '->' || p.dest_location_id as bound,
    p.trip_count as source_value,
    d.trip_count as detail_value
from od_published as p
left join od_detail as d
    on
        p.origin_location_id = d.origin_location_id
        and p.dest_location_id = d.dest_location_id
        and p.origin_zone is not distinct from d.origin_zone
        and p.dest_zone is not distinct from d.dest_zone
where
    p.trip_count is distinct from d.trip_count
    or p.total_revenue is distinct from d.total_revenue
