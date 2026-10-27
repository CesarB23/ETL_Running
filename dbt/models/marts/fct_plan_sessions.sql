with summary as (
    select planned_workout_id,
        count(*) filter (where pace_fast_s_km is not null) as targeted_steps,
        count(*) filter (where pace_status = 'met') as steps_met,
        count(*) filter (where pace_status in ('met', 'not_met')) as verified_steps,
        count(*) filter (where pace_status = 'unverifiable') as steps_unverifiable,
        count(*) filter (where match_method in ('wkt_step', 'workout_step_group')) as indexed_steps
    from {{ ref('fct_plan_vs_actual') }} group by 1
)
select p.planned_workout_id, p.week_start, p.scheduled_date, p.title,
    p.garmin_workout_id, p.plan_hash, m.activity_id, m.activity_date,
    m.date_offset_days, (m.match_method = 'confirmed_by_user') as confirmed_by_user,
    m.match_method, m.confidence,
    coalesce(s.targeted_steps, 0) as targeted_steps,
    coalesce(s.steps_met, 0) as steps_met,
    coalesce(s.verified_steps, 0) as verified_steps,
    coalesce(s.steps_unverifiable, 0) as steps_unverifiable,
    coalesce(s.indexed_steps, 0) as indexed_steps,
    case when p.scheduled_date >= current_date and m.activity_id is null then 'upcoming'
         when m.activity_id is null then 'missed'
         when coalesce(s.targeted_steps, 0) = 0 then 'done'
         when s.steps_met = s.targeted_steps then 'done'
         else 'partial' end as status
from {{ ref('stg_planned_workouts') }} p
join {{ ref('int_plan_activity_match') }} m using (planned_workout_id)
left join summary s using (planned_workout_id)
