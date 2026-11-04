select
    vehicle_id,
    medallion_number,
    vin,
    make,
    model,
    model_year,
    fuel_type,
    wheelchair_accessible,
    garage_id,
    cast(timezone('UTC', in_service_date) as date) as in_service_date,
    cast(timezone('UTC', retired_date) as date) as retired_date,
    retired_date is null as is_in_service
from {{ source('ops_raw', 'vehicle') }}
