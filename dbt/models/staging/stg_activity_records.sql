select
    activity_id, ts_utc, distance_m, speed_mps,
    heart_rate, cadence_spm, altitude_m, lat, lon, timer_running
from {{ source('silver', 'activity_records') }}
