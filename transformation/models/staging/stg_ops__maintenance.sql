select
    maintenance_id,
    vehicle_id,
    cast(timezone('UTC', started_date) as date) as started_date,
    down_days,
    cast(timezone('UTC', started_date) + to_days(cast(down_days as integer)) as date) as ended_date,
    maintenance_type,
    cost_usd
from {{ source('ops_raw', 'maintenance_event') }}
