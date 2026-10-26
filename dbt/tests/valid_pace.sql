select activity_id from {{ ref('fct_runs') }}
where is_valid_for_pace and (pace_min_km not between 2.5 and 12 or pace_min_km is null)
