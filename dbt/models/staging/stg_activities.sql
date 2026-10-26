select
    activity_id, activity_type, is_manual, has_gps,
    start_utc, start_local, local_date, tz_local,
    distance_m, duration_s, moving_s, elapsed_s,
    avg_speed_mps, avg_hr, max_hr, avg_cadence_spm,
    stride_m, elev_gain_m, elev_loss_m, calories, lap_count,
    moderate_intensity_min, vigorous_intensity_min
from {{ source('silver', 'activities') }}
