# Modelo de datos

Alcance: **solo actividades de running** (D15). Convenciones: `snake_case` en inglés,
tiempos en UTC (`*_utc`) más `tz_local`, distancias en metros, velocidades en m/s,
duraciones en segundos. Ausencia = `NULL`. Ventana: desde `START_DATE` = 2026-08-17.

## Bronze (archivos)

| Dataset | Origen | Partición `dt` | Formato |
| --- | --- | --- | --- |
| `garmin/activities_list` | `search_activities` | fecha de inicio de la actividad | JSON (todos los tipos, crudo) |
| `garmin/activity_fit` | descarga FIT por actividad | fecha de la actividad | `.zip`/`.fit` (solo running) |
| `garmin/calendar` | calendario de Garmin (workouts programados) | día | JSON (si el spike de la etapa 5 lo requiere) |
| `plan/weekly_plan` | `workouts/semana_*.json` de `../Garmin/` | lunes de la semana | JSON |

Manifiesto: `lake/bronze/_manifest.parquet` con
`run_id, dataset, dt, path, sha256, bytes, ingested_at, request_params, parser_version`.

## Silver (Parquet)

| Tabla | Clave | Descripción |
| --- | --- | --- |
| `activities` | `activity_id` | Solo running (`RUNNING_TYPE_KEYS`). Incluye `activity_type`, `is_manual`, `has_gps`, `start_utc`, `tz_local`, `distance_m`, `duration_s`, `moving_s`, `avg_speed_mps`, `avg_hr`, `max_hr`, `avg_cadence_spm`, `stride_m`, `elev_gain_m`, `elev_loss_m`, `calories`, `lap_count`, `moderate_intensity_min`, `vigorous_intensity_min`, `start_lat/lon` (opcional/anonimizable). |
| `activity_laps` | `(activity_id, lap_index)` | Vueltas desde FIT: tiempo, distancia, velocidad, FC, cadencia, desnivel, `trigger`, y **`wkt_step_index`** (paso del workout que el reloj ejecutaba; nulo si no se corrió un workout). |
| `activity_records` | `(activity_id, ts_utc)` | Serie segundo a segundo desde FIT: FC, velocidad, cadencia, altitud, lat/lon. |
| `planned_workouts` | `(week_start, date)` | Sesión planificada: título, tipo, notas, `plan_hash`, `garmin_workout_id` (si se subió). |
| `planned_steps` | `(planned_workout_id, step_order)` | Bloques: tipo, distancia o duración objetivo, rango de ritmo (m/s), recuperación. `step_order` es el mismo orden que usa Garmin, para casar con `wkt_step_index`. |
| `_quarantine/*` | — | Filas rechazadas con `reason` y `source_path`. |

Las actividades no running no se guardan en silver; el reporte de silver las cuenta
como `out_of_scope` para poder reconciliar con bronze.

## Gold (DuckDB / dbt)

| Modelo | Granularidad | Contenido |
| --- | --- | --- |
| `dim_date` | día | Calendario, semana ISO, mes, bloque de entrenamiento. |
| `fct_runs` | actividad | Ritmo medio (min/km), FC, cadencia, desnivel, eficiencia aeróbica, drift cardíaco, flags de calidad. |
| `fct_run_laps` | lap | Ritmo y FC por vuelta, lap vs. ritmo medio. |
| `fct_plan_vs_actual` | paso planificado | Sesión planificada ↔ actividad, ritmo objetivo vs real, desviación, series cumplidas, `match_method` (`wkt_step` / `distance_segmentation`) y `confidence`. |
| `fct_training_load` | día | Carga diaria (minutos de intensidad ponderados), aguda (7 d), crónica (28 d), ACWR, `is_reliable`. |
| `fct_weekly_summary` | semana | Km, tiempo, desnivel, nº sesiones, % cumplimiento del plan. |
| `mart_data_quality` | dataset | Frescura, volumen, rechazados. |

## Definiciones de métricas

- **Ritmo (min/km)** = `1000 / avg_speed_mps / 60`.
- **Eficiencia aeróbica** = `avg_speed_mps / avg_hr` (mayor es mejor); solo en
  actividades no manuales con FC válida.
- **Drift cardíaco** = variación % de la razón velocidad/FC entre 1.ª y 2.ª mitad
  de la actividad (requiere records).
- **Carga** = `moderate_intensity_min + 2 · vigorous_intensity_min` por actividad
  (campos de Garmin, sin parámetros del usuario, D13). Agregada por día (0 si no hubo
  entreno).
- **Carga aguda/crónica** = media móvil de la carga a 7 y 28 días; **ACWR** =
  aguda/crónica. Con < 28 días de historial: `is_reliable = false`. La ventana arranca
  el 2026-08-17, así que ACWR fiable a partir de ~2026-09-14.
- **Cumplimiento del plan** = bloques con ritmo real dentro del rango objetivo /
  bloques planificados.
- **No hay TRIMP** ni métricas que requieran FC de reposo o FCmax (D13, D15).

## Reglas de calidad

- `activity_id` único y no nulo; `distance_m >= 0`; `duration_s > 0`.
- `avg_hr` entre 30 y 230 o `NULL`.
- Actividades `is_manual` excluidas de métricas de ritmo/FC.
- Una actividad se vincula a lo sumo a una sesión planificada.
- Todo `activity_type` en silver pertenece a `RUNNING_TYPE_KEYS`.
