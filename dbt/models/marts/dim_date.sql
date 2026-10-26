with dates as (
    {{ dbt_utils.date_spine(
        datepart='day',
        start_date="cast('" ~ env_var('START_DATE', '2026-08-17') ~ "' as date)",
        end_date='(current_date + interval 1 day)'
    ) }}
)
select
    cast(date_day as date) as activity_date,
    cast(date_trunc('week', date_day) as date) as week_start,
    cast(strftime(date_day, '%G') as integer) as iso_year,
    cast(strftime(date_day, '%V') as integer) as iso_week,
    cast(date_trunc('month', date_day) as date) as month_start
from dates
