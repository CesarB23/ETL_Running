select activity_id from {{ ref('int_plan_activity_match') }}
where activity_id is not null
group by 1 having count(*) > 1
