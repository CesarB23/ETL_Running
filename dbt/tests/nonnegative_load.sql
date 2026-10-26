select activity_date from {{ ref('fct_training_load') }}
where training_load < 0 or acute_7d < 0 or chronic_28d < 0 or acwr < 0
    or (not is_reliable and acwr is not null)
