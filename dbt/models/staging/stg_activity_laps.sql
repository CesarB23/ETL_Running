select
    activity_id, lap_index, start_utc, end_utc,
    distance_m, duration_s, elapsed_s, avg_speed_mps,
    avg_hr, max_hr, avg_cadence_spm, elev_gain_m,
    lap_trigger, intensity, wkt_step_index
from {{ source('silver', 'activity_laps') }}
