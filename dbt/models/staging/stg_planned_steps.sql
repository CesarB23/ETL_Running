select planned_workout_id, step_seq, step_order, candidate_fit_index,
       kind, repetition, target_distance_m, target_duration_s,
       pace_fast_s_km, pace_slow_s_km, speed_min_mps, speed_max_mps
from {{ source('silver', 'planned_steps') }}
