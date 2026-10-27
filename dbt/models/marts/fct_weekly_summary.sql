with runs as (
select d.week_start,
    count(r.activity_id) as run_count,
    coalesce(sum(r.distance_m), 0) as distance_m,
    coalesce(sum(r.duration_s), 0) as duration_s,
    coalesce(sum(r.elev_gain_m), 0) as elev_gain_m,
    round(coalesce(sum(r.distance_m), 0) / 1000.0, 2) as distance_km
from {{ ref('dim_date') }} d
left join {{ ref('fct_runs') }} r on r.activity_date = d.activity_date and not r.is_manual
group by d.week_start
), planned as (
    select week_start,
        sum(case when status != 'upcoming' then targeted_steps else 0 end) as targeted_steps,
        sum(case when status != 'upcoming' then steps_met else 0 end) as steps_met,
        sum(case when status != 'upcoming' then verified_steps else 0 end) as verified_steps
    from {{ ref('fct_plan_sessions') }} group by week_start
)
select r.*,
    p.targeted_steps, p.steps_met, p.verified_steps,
    case when p.targeted_steps > 0 and p.verified_steps > 0
        then round(100.0 * p.steps_met / p.targeted_steps, 1)
    end as plan_compliance_pct
from runs r left join planned p using (week_start)
