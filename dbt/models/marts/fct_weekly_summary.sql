select d.week_start,
    count(r.activity_id) as run_count,
    coalesce(sum(r.distance_m), 0) as distance_m,
    coalesce(sum(r.duration_s), 0) as duration_s,
    coalesce(sum(r.elev_gain_m), 0) as elev_gain_m,
    round(coalesce(sum(r.distance_m), 0) / 1000.0, 2) as distance_km
from {{ ref('dim_date') }} d
left join {{ ref('fct_runs') }} r on r.activity_date = d.activity_date and not r.is_manual
group by d.week_start
