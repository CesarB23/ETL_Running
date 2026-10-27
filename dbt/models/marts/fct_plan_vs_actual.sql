-- Una fila por paso expandido. Prioriza lap exacto; si el reloj agrupa
-- repeticiones en un mismo wkt_step_index, mide el tramo completo y lo marca
-- como confianza media. Nunca declara alta una confianza sin lap respaldado.
with ordered_steps as (
    select s.*, m.activity_id, m.scheduled_date, m.week_start,
        m.match_method as activity_match_method, m.confidence as activity_confidence,
        row_number() over (partition by s.planned_workout_id, s.candidate_fit_index
            order by s.step_seq) as repetition_number,
        sum(case when s.target_distance_m is null then 1 else 0 end) over (
            partition by s.planned_workout_id order by s.step_seq
            rows between unbounded preceding and current row) as unknown_distance_before,
        coalesce(sum(s.target_distance_m) over (
            partition by s.planned_workout_id order by s.step_seq
            rows between unbounded preceding and 1 preceding), 0) as start_distance_m,
        count(*) filter (where s.pace_fast_s_km is not null) over (
            partition by s.planned_workout_id) as paced_steps_in_session
    from {{ ref('stg_planned_steps') }} s
    join {{ ref('int_plan_activity_match') }} m using (planned_workout_id)
), ordered_laps as (
    select l.*,
        row_number() over (partition by activity_id, wkt_step_index
            order by lap_index) as repetition_number
    from {{ ref('stg_activity_laps') }} l
    where wkt_step_index is not null
), lap_groups as (
    select l.*,
        case when l.wkt_step_index is distinct from
            lag(l.wkt_step_index) over (partition by l.activity_id order by l.lap_index)
            then 1 else 0 end as new_island
    from {{ ref('stg_activity_laps') }} l
    where l.wkt_step_index is not null
), island_ids as (
    select l.*,
        sum(new_island) over (partition by activity_id order by lap_index
            rows between unbounded preceding and current row) as island_id
    from lap_groups l
), islands as (
    -- Tramo contiguo de laps que el reloj atribuye al mismo paso del workout.
    select activity_id, island_id, min(wkt_step_index) as wkt_step_index,
        min(lap_index) as first_lap, max(lap_index) as last_lap,
        sum(distance_m) as distance_m, sum(duration_s) as duration_s,
        sum(distance_m) / nullif(sum(duration_s), 0) as speed_mps
    from island_ids group by 1, 2
    having sum(duration_s) > 0 and sum(distance_m) > 0
), indexed as (
    select s.*,
        l.lap_index, l.distance_m as lap_distance_m, l.duration_s as lap_duration_s,
        l.avg_speed_mps as lap_speed_mps,
        (l.lap_index is not null and
         (s.target_distance_m is null or
          abs(l.distance_m - s.target_distance_m) <= greatest(30, s.target_distance_m * 0.20))
         and (s.target_duration_s is null or
          abs(l.duration_s - s.target_duration_s) <= greatest(30, s.target_duration_s * 0.20))
        ) as lap_plausible
    from ordered_steps s
    left join ordered_laps l on s.activity_id = l.activity_id
        and s.candidate_fit_index = l.wkt_step_index
        and s.repetition_number = l.repetition_number
), island_candidates as (
    -- El FIT agrupa repeticiones bajo el mismo índice: se acepta un tramo de
    -- 1 a 5 veces el objetivo y se elige el de ritmo más cercano. Bandas amplias
    -- solo para localizar; el cumplimiento usa después la tolerancia estricta.
    select s.planned_workout_id, s.step_seq, i.wkt_step_index, i.first_lap,
        i.distance_m as island_distance_m, i.duration_s as island_duration_s,
        i.speed_mps as island_speed_mps,
        row_number() over (partition by s.planned_workout_id, s.step_seq
            order by abs(i.speed_mps - (s.speed_min_mps + s.speed_max_mps) / 2),
                     i.first_lap) as island_rank
    from ordered_steps s
    join islands i on i.activity_id = s.activity_id
    where s.pace_fast_s_km is not null
      and i.distance_m >= 50
      and i.speed_mps between 0.75 * s.speed_min_mps and 1.30 * s.speed_max_mps
      and (
        (s.target_distance_m is not null and s.target_distance_m > 0
         and i.distance_m / s.target_distance_m between 0.8 and 5.5
         and abs(i.distance_m / s.target_distance_m
                 - round(i.distance_m / s.target_distance_m)) <= 0.15)
        or (s.target_distance_m is null and s.target_duration_s is not null
         and abs(i.duration_s - s.target_duration_s)
             <= greatest(30, s.target_duration_s * 0.20))
      )
), best_island as (
    select * from island_candidates where island_rank = 1
), segments as (
    -- Respaldo de baja confianza: solo cuando TODOS los pasos previos tienen distancia.
    select i.planned_workout_id, i.step_seq,
        avg(r.speed_mps) as segmented_speed_mps,
        count(*) as sample_count
    from indexed i
    join {{ ref('stg_activity_records') }} r on r.activity_id = i.activity_id
        and r.timer_running and r.distance_m >= i.start_distance_m
        and r.distance_m < i.start_distance_m + i.target_distance_m
        and r.speed_mps > 0
    where (not i.lap_plausible or i.lap_plausible is null)
        and i.unknown_distance_before = 0 and i.target_distance_m > 0
    group by 1, 2
), activity_fallback as (
    -- Sesión continua sin laps de workout: solo si hay UN bloque con ritmo y
    -- la actividad completa coincide en distancia/duración con ese bloque.
    select o.planned_workout_id, o.step_seq, a.avg_speed_mps as activity_speed_mps
    from ordered_steps o
    join {{ ref('stg_activities') }} a on a.activity_id = o.activity_id
    where o.paced_steps_in_session = 1 and o.pace_fast_s_km is not null
      and not a.is_manual and a.avg_speed_mps > 0
      and (o.target_distance_m is null
           or abs(a.distance_m - o.target_distance_m)
              <= greatest(500, o.target_distance_m * 0.15))
      and (o.target_duration_s is null
           or abs(a.duration_s - o.target_duration_s)
              <= greatest(120, o.target_duration_s * 0.20))
), selected as (
    select i.*,
        case when i.lap_plausible then i.lap_speed_mps
             when b.island_speed_mps is not null then b.island_speed_mps
             when g.sample_count >= 2 then g.segmented_speed_mps
             when f.activity_speed_mps is not null then f.activity_speed_mps end
            as actual_speed_mps,
        case when i.lap_plausible then 'wkt_step'
             when b.island_speed_mps is not null then 'workout_step_group'
             when g.sample_count >= 2 then 'distance_segmentation'
             when f.activity_speed_mps is not null then 'activity_total'
             else 'none' end as match_method,
        case when i.lap_plausible then i.lap_index end as matched_lap_index,
        b.first_lap as matched_island_lap
    from indexed i
    left join best_island b on b.planned_workout_id = i.planned_workout_id
        and b.step_seq = i.step_seq
    left join segments g on g.planned_workout_id = i.planned_workout_id
        and g.step_seq = i.step_seq
    left join activity_fallback f on f.planned_workout_id = i.planned_workout_id
        and f.step_seq = i.step_seq
)
select planned_workout_id || '-' || cast(step_seq as varchar) as planned_step_id,
    planned_workout_id, step_seq, step_order, kind, repetition,
    scheduled_date, week_start, activity_id, target_distance_m, target_duration_s,
    pace_fast_s_km, pace_slow_s_km, speed_min_mps, speed_max_mps,
    matched_lap_index, matched_island_lap, match_method,
    case when match_method = 'none' then 'none'
         when match_method = 'wkt_step' and activity_confidence = 'high' then 'high'
         when match_method in ('wkt_step', 'workout_step_group')
              and activity_confidence in ('high', 'medium') then 'medium'
         else 'low' end as confidence,
    {{ pace_min_km('actual_speed_mps') }} * 60 as actual_pace_s_km,
    case when pace_fast_s_km is not null and pace_slow_s_km is not null
        and actual_speed_mps > 0 then
        {{ pace_min_km('actual_speed_mps') }} * 60 - (pace_fast_s_km + pace_slow_s_km) / 2
    end as deviation_s_km,
    case when pace_fast_s_km is null then 'not_targeted'
         when actual_speed_mps is null or actual_speed_mps <= 0 then 'unverifiable'
         when {{ pace_min_km('actual_speed_mps') }} * 60
              between pace_fast_s_km - {{ var('pace_tolerance_s_km', 5) }}
                  and pace_slow_s_km + {{ var('pace_tolerance_s_km', 5) }} then 'met'
         else 'not_met' end as pace_status
from selected
