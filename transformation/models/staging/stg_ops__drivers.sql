select
    driver_id,
    hack_licence_no,
    driver_ref,
    engagement_type,
    home_garage_id,
    cast(timezone('UTC', hire_date) as date) as hire_date,
    cast(timezone('UTC', termination_date) as date) as termination_date,
    is_wav_certified,
    driver_status
from {{ source('ops_raw', 'driver') }}
