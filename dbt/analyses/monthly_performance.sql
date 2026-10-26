select date_trunc('month', activity_date)::date as month_start,
    count(*) filter (where is_valid_for_pace) as runs_with_valid_pace,
    round(avg(pace_min_km) filter (where is_valid_for_pace), 2) as avg_pace_min_km,
    round(avg(aerobic_efficiency), 4) as avg_aerobic_efficiency
from gold.fct_runs
group by 1 order by 1;
