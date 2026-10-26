select activity_id, ts_utc from {{ ref('stg_activity_records') }}
group by 1, 2 having count(*) > 1
