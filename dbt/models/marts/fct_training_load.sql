with by_day as (
    select d.activity_date,
        case when count(a.activity_id) = 0 then 0
             when count(a.activity_id) filter (where
                 a.moderate_intensity_min is null or a.vigorous_intensity_min is null) > 0
             then null
             else sum(a.moderate_intensity_min + 2 * a.vigorous_intensity_min)
        end as training_load
    from {{ ref('dim_date') }} d
    left join {{ ref('stg_activities') }} a on a.local_date = d.activity_date
    group by d.activity_date
), windows as (
    select activity_date, training_load,
        {{ rolling_avg('training_load', var('acute_days')) }} as acute_7d,
        {{ rolling_avg('training_load', var('chronic_days')) }} as chronic_28d,
        count(training_load) over (order by activity_date
            rows between {{ var('chronic_days') | int - 1 }} preceding and current row)
            as chronic_valid_days
    from by_day
)
select activity_date, training_load, acute_7d, chronic_28d,
    (chronic_valid_days = {{ var('chronic_days') }} and chronic_28d > 0) as is_reliable,
    case when chronic_valid_days = {{ var('chronic_days') }} and chronic_28d > 0
        then acute_7d / chronic_28d end as acwr
from windows
