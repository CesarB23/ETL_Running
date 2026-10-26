select
    cast(activity_id as varchar) || '-' || cast(lap_index as varchar) as lap_key,
    activity_id, lap_index, start_utc, end_utc,
    distance_m, duration_s, avg_speed_mps, avg_hr, intensity,
    lap_trigger, wkt_step_index,
    {{ pace_min_km('avg_speed_mps') }} as pace_min_km
from {{ ref('stg_activity_laps') }}
