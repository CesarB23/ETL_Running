-- Seis semanas ficticias: carga 10 cada lunes y 0 el resto.
with days as (
    select cast(activity_date as date) as activity_date,
        cast(training_load as double) as training_load,
        cast(expected_acute_7d as double) as expected_acute_7d,
        cast(expected_chronic_28d as double) as expected_chronic_28d,
        cast(expected_acwr as double) as expected_acwr
    from {{ ref('synthetic_training_days') }}
), windows as (
    select *,
        {{ rolling_avg('training_load', 7) }} as actual_acute,
        {{ rolling_avg('training_load', 28) }} as actual_chronic,
        count(training_load) over (order by activity_date rows between 27 preceding and current row)
            as chronic_days
    from days
)
select activity_date from windows
where (expected_acute_7d is not null and abs(actual_acute - expected_acute_7d) > 0.000001)
    or (expected_chronic_28d is not null and
        abs(actual_chronic - expected_chronic_28d) > 0.000001)
    or (expected_acwr is not null and
        (chronic_days != 28 or abs(actual_acute / nullif(actual_chronic, 0) - expected_acwr) > 0.000001))
