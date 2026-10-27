select planned_step_id from {{ ref('fct_plan_vs_actual') }}
where confidence = 'high' and (matched_lap_index is null or
    (activity_id not in (select activity_id from {{ ref('stg_activity_workout_links') }})
     and activity_id not in (select activity_id from {{ ref('stg_plan_confirmations') }})))
