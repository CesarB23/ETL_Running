with expected as (
    select cast(date_trunc('week', local_date) as date) as week_start,
        round(sum(distance_m) / 1000.0, 2) as distance_km
    from {{ ref('stg_activities') }}
    where not is_manual
    group by 1
)
select w.week_start from {{ ref('fct_weekly_summary') }} w
join expected e using (week_start)
where abs(w.distance_km - e.distance_km) > 0.01
