with valid_records as (
    select activity_id, ts_utc, speed_mps, heart_rate,
        row_number() over (partition by activity_id order by ts_utc) as rn,
        count(*) over (partition by activity_id) as n
    from {{ ref('stg_activity_records') }}
    where timer_running and speed_mps > 0 and heart_rate between 30 and 230
), halves as (
    select activity_id,
        avg(case when rn <= n / 2 then speed_mps end) /
            nullif(avg(case when rn <= n / 2 then heart_rate end), 0) as first_efficiency,
        avg(case when rn > n / 2 then speed_mps end) /
            nullif(avg(case when rn > n / 2 then heart_rate end), 0) as second_efficiency,
        count(*) as valid_records
    from valid_records
    group by activity_id
), runs as (
    select a.*,
        {{ pace_min_km('a.avg_speed_mps') }} as pace_min_km,
        case when not a.is_manual and a.avg_hr between 30 and 230 and a.avg_speed_mps > 0
            then a.avg_speed_mps / a.avg_hr end as aerobic_efficiency
    from {{ ref('stg_activities') }} a
)
select r.activity_id, r.local_date as activity_date, r.start_utc, r.activity_type,
    r.is_manual, r.has_gps, r.distance_m, r.duration_s, r.avg_speed_mps,
    r.avg_hr, r.avg_cadence_spm, r.elev_gain_m, r.elev_loss_m,
    r.moderate_intensity_min, r.vigorous_intensity_min,
    case when r.is_manual then null else r.pace_min_km end as pace_min_km,
    r.aerobic_efficiency,
    case when not r.is_manual and h.valid_records >= 4 and h.first_efficiency > 0
        then 100.0 * (h.second_efficiency / h.first_efficiency - 1) end as cardiac_drift_pct,
    (not r.is_manual and r.distance_m > 0 and r.duration_s > 0 and
        r.pace_min_km between 2.5 and 12) as is_valid_for_pace
from runs r
left join halves h using (activity_id)
