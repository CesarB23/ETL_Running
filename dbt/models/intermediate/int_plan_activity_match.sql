{{ config(materialized='view') }}
-- Sin ID de workout en actividades: primero misma fecha; ±1 día solo con menor confianza.
-- Nunca reclamar un match por workoutId sin evidencia directa de la API.
with expected as (
    select planned_workout_id,
        sum(target_duration_s) as planned_duration_s,
        sum(target_distance_m) as planned_distance_m
    from {{ ref('stg_planned_steps') }} group by 1
), candidates as (
    select p.planned_workout_id, p.week_start, p.scheduled_date,
        a.activity_id, a.activity_date,
        case when c.activity_id is not null then 0
             when l.activity_id is not null then 1 else 2 end as link_priority,
        abs(date_diff('day', p.scheduled_date, a.activity_date)) as days_apart,
        abs(a.duration_s - e.planned_duration_s) as duration_delta,
        abs(a.distance_m - e.planned_distance_m) as distance_delta,
        row_number() over (partition by a.activity_id
            order by case when c.activity_id is not null then 0
                          when l.activity_id is not null then 1 else 2 end,
                     abs(date_diff('day', p.scheduled_date, a.activity_date)),
                     p.scheduled_date, p.planned_workout_id) as activity_rank
    from {{ ref('stg_planned_workouts') }} p
    left join expected e using (planned_workout_id)
    left join {{ ref('fct_runs') }} a
        on abs(date_diff('day', p.scheduled_date, a.activity_date))
            <= {{ var('match_window_days', 1) }} and not a.is_manual
    left join {{ ref('stg_activity_workout_links') }} l
        on l.activity_id = a.activity_id and l.planned_workout_id = p.planned_workout_id
        and l.garmin_workout_id = p.garmin_workout_id
    left join {{ ref('stg_plan_confirmations') }} c
        on c.activity_id = a.activity_id and c.planned_workout_id = p.planned_workout_id
        and c.plan_hash = p.plan_hash
), activity_first as (
    -- Descartar candidatos asignados a otra sesión ANTES de elegir el preferido del plan.
    select * from candidates where activity_rank = 1
), plan_ranked as (
    select *, row_number() over (partition by planned_workout_id
        order by link_priority, days_apart, duration_delta nulls last,
                 distance_delta nulls last, activity_id) as planned_rank
    from activity_first
)
select p.planned_workout_id, p.week_start, p.scheduled_date,
    c.activity_id, c.activity_date,
    date_diff('day', p.scheduled_date, c.activity_date) as date_offset_days,
    case when c.activity_id is null then 'none'
         when c.link_priority = 0 then 'confirmed_by_user'
         when c.link_priority = 1 then 'workout_name'
         when c.days_apart = 0 then 'same_date'
         else 'adjacent_date' end as match_method,
    case when c.activity_id is null then 'none'
         when c.link_priority in (0, 1) then 'high'
         when c.days_apart = 0 then 'medium'
         else 'low' end as confidence
from {{ ref('stg_planned_workouts') }} p
left join plan_ranked c on c.planned_workout_id = p.planned_workout_id
    and c.planned_rank = 1
