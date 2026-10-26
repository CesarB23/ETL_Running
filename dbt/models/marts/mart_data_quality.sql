select 'silver/activities' as dataset, count(*) as row_count,
       count(distinct activity_id) as distinct_keys,
       cast(max(local_date) as date) as max_activity_date,
       (select count(*) from {{ source('silver', 'activities_quarantine') }}) as rejected_count
from {{ ref('stg_activities') }}
union all
select 'silver/activity_laps', count(*), count(distinct (activity_id, lap_index)),
       cast(max(start_utc) as date), cast(null as bigint)
from {{ ref('stg_activity_laps') }}
union all
select 'silver/activity_records', count(*), count(distinct (activity_id, ts_utc)),
       cast(max(ts_utc) as date), cast(null as bigint)
from {{ ref('stg_activity_records') }}
