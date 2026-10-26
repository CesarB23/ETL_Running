select activity_id, lap_index from {{ ref('stg_activity_laps') }}
group by 1, 2 having count(*) > 1
