select planned_workout_id, step_seq from {{ ref('stg_planned_steps') }}
group by 1, 2 having count(*) > 1
