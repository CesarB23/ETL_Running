select r.activity_id, r.activity_date,
    cast(date_trunc('week', r.activity_date) as date) as week_start,
    case when w.week_start is null then 'no_plan'
         else 'unplanned_extra' end as status
from {{ ref('fct_runs') }} r
left join (select distinct week_start from {{ ref('stg_planned_workouts') }}) w
    on cast(date_trunc('week', r.activity_date) as date) = w.week_start
left join {{ ref('int_plan_activity_match') }} m on r.activity_id = m.activity_id
where not r.is_manual and m.activity_id is null
