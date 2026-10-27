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
| `planned_workouts` | `planned_workout_id` (`week_start/date`) | Sesión planificada: título, `plan_hash`, `garmin_workout_id` si existe en uploads local. |
| `planned_steps` | `(planned_workout_id, step_seq)` | Pasos expandidos por repetición: tipo, objetivo y rango de ritmo. `step_order` Garmin puede repetirse entre series; `candidate_fit_index` es una hipótesis verificada por lap antes de usarla. |
| `_quarantine/*` | — | Filas rechazadas con `reason` y `source_path`. |

Los FIT (etapa 3) se descargan **solo para actividades running elegibles** desde
`GarminPersonalApiClient.download_activity(activity_id)`: devuelve un ZIP original
con un `.fit`, conservado inmutable en bronze. `activity_laps.parquet` tiene `lap_index`,
`start_utc`, `end_utc`, `distance_m`, `duration_s`, `avg_speed_mps`, `avg_hr`, `max_hr`,
`avg_cadence_spm`, `lap_trigger`, `intensity`, `wkt_step_index` (NULL sin workout).
`activity_records.parquet` usa `(activity_id, ts_utc)` único y conserva distancia,
velocidad m/s, FC, cadencia, altitud, coordenadas en grados (locales) y `timer_running`.
No se interpolan huecos. `lake/silver/_fit_build.json` registra discrepancias de
distancia de laps respecto a la actividad (tolerancia por defecto: 1 %). El FIT
sintético de tests nunca contiene datos personales.

Las actividades no running no se guardan en silver; el reporte de silver las cuenta
como `out_of_scope` para poder reconciliar con bronze.

### Diccionario Garmin → `silver.activities` (etapa 2)

| Campo Garmin | Columna silver | Regla |
| --- | --- | --- |
| `activityId` | `activity_id` | Clave entera única; última versión por `ingested_at` |
| `activityType.typeKey` | `activity_type` | Solo `RUNNING_TYPE_KEYS` |
| `manualActivity` / `isManualActivity` | `is_manual` | Booleano; ausencia → `false` |
| `startTimeGMT` | `start_utc` | Timestamp UTC (con zona) |
| `startTimeLocal` | `start_local`, `local_date` | Hora de pared, sin zona; fecha para particionar |
| Diferencia local − GMT | `utc_offset_min`, `tz_local` | Offset por actividad (`-06:00`, `+01:00`…), **no** identificador IANA; respeta DST sin inferir la región |
| `startLatitude`, `startLongitude` | `start_lat`, `start_lon`, `has_gps` | Solo local; nulos en cinta, sin coordenadas o par (0, 0) |
| `distance`, `duration`, `movingDuration`, `elapsedDuration` | `distance_m`, `duration_s`, `moving_s`, `elapsed_s` | Metros y segundos; duración obligatoria > 0 |
| `averageSpeed`, `maxSpeed` | `avg_speed_mps`, `max_speed_mps` | m/s |
| `averageHR`, `maxHR` | `avg_hr`, `max_hr` | 30–230 o NULL; fuera de rango → NULL con aviso |
| `averageRunningCadenceInStepsPerMinute` | `avg_cadence_spm` | pasos/min |
| `avgStrideLength` | `stride_m` | Garmin lo entrega en cm; /100 |
| `elevationGain`, `elevationLoss` | `elev_gain_m`, `elev_loss_m` | m |
| `calories`, `lapCount` | `calories`, `lap_count` | Sin métricas de salud adicionales |
| `moderateIntensityMinutes`, `vigorousIntensityMinutes` | `moderate_intensity_min`, `vigorous_intensity_min` | Insumo de carga; ausencia → NULL, no 0 |

Cada fila guarda `source_path`, `bronze_run_id`, `bronze_ingested_at` para linaje. Registros
inválidos van a `lake/silver/_quarantine/activities.parquet` con motivo y ruta de origen;
no se copian payloads ni datos personales a los logs. Tanto silver como bronze y el warehouse
están ignorados por git. Para agrupar por **semana local**, preferir `local_date` a `start_utc`
(DuckDB convierte TIMESTAMPTZ a la zona de la sesión).
Los Parquet de Silver se escriben **sin compresión** para poder abrirlos en visores
básicos de VS Code; con este volumen personal la diferencia de tamaño es pequeña.
Decisiones confirmadas: conservar `start_lat`/`start_lon` en Silver, sin publicarlas
en gold ni en la UI por defecto; `treadmill_running` cuenta como running con `has_gps = false`.

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

### Etapa 5: plan vs real (sin asociaciones ficticias)

`plan load` guarda cada JSON semanal original como nueva versión inmutable de
`plan/weekly_plan` en Bronze. Solo se cargan los JSON que existen. Silver crea
`planned_workouts.parquet` y `planned_steps.parquet` con `plan_hash` y pasos
expandidos (trabajo/recuperación por repetición, `step_seq` único y
`step_order` Garmin 1-based). Los `workoutId` y nombres de uploads se leen
**opcionalmente** de `../Garmin/data/uploads.json`: permanecen solo en Silver,
nunca se copia el archivo original al repositorio.

`plan link-workouts` consulta `get_activity_workouts` únicamente para carreras
cerca de una fecha con upload. Solo crea una asociación en
`silver/activity_workout_links.parquet` si el nombre API coincide **exactamente**
con un único upload (ignorando mayúsculas) dentro de ±1 día; entonces el ID
procede del upload, no se inventa desde el FIT.

`plan confirm --date YYYY-MM-DD --activity-id N` guarda una confirmación manual
local en `silver/plan_confirmations.parquet`, ligada al `plan_hash` de la sesión.
Permite aceptar un entreno desplazado ±1 día sin subir la confianza de los laps
ni reescribir los JSON originales. Si el plan cambia de hash, la confirmación deja
de aplicar.

Reglas en Gold:

1. `int_plan_activity_match` prioriza confirmación manual (`confirmed_by_user`),
   luego asociación por nombre API, luego fecha. Si no existe confirmación,
   elige carrera no manual en la misma fecha, o ±1 día con menor confianza.
   Usa duración/distancia estimadas para desempatar y no asigna una actividad a
   dos sesiones. Sin carrera: `missed`; si el día aún no ha llegado: `upcoming`.
2. `fct_plan_vs_actual` intenta emparejar cada paso con un lap cuyo
   `wkt_step_index` coincida con el **índice candidato** `step_order - 1` y la
   repetición ordinal, comprobando distancia/duración (20 % o 30 m/30 s). Si el
   reloj agrupa varias repeticiones bajo el mismo `wkt_step_index`, agrupa los
   laps contiguos en un tramo (`workout_step_group`) y usa el ritmo medio del
   tramo; acepta que el tramo equivalga de 1 a 5 veces el objetivo y elige el
   más cercano al ritmo prescrito. Después prueba segmentación por distancia
   acumulada (solo si todas las distancias previas son conocidas) y, para una
   sesión continua con un único bloque con ritmo, el total de la actividad.
3. Un paso de ritmo es `met` si el ritmo real cae en `[fast-5, slow+5]` s/km,
   `not_met` si es medible y queda fuera, y `unverifiable` si no hay evidencia.
   Pasos sin ritmo objetivo (`recovery`, warmup) son `not_targeted`.
   `confidence=high` exige asociación confirmada o por nombre API **y** un lap
   plausible; un tramo agrupado es `medium`; segmentación o total de actividad
   es `low`. Ningún paso sin lap puede ser `high`.
4. `fct_plan_sessions` da un estado por sesión (`done`, `partial`, `missed`,
   `upcoming`); `fct_unplanned_runs` distingue `no_plan` (sin JSON semanal) de
   `unplanned_extra`. `fct_weekly_summary` excluye del denominador sesiones
   futuras y muestra **NULL** en `plan_compliance_pct` cuando hay 0 bloques
   verificables, en lugar de atribuir un 0 % engañoso.

En etapa 4 los modelos dbt residen en el esquema `gold` de
`lake/warehouse.duckdb`. `stg_activities`, `stg_activity_laps` y
`stg_activity_records` son vistas sobre Parquet Silver (sources dbt); excluyen
coordenadas GPS y otros datos personales del almacén Gold. Los marts se
materializan como tablas y pueden reconstruirse con `make dbt-build`.

`fct_runs.pace_min_km = 1000 / avg_speed_mps / 60` (NULL sin velocidad, y
no se calcula para actividades manuales). `aerobic_efficiency` es
`avg_speed_mps / avg_hr` solo con FC válida; `cardiac_drift_pct` compara
la relación velocidad/FC de las mitades de records válidos sin contar pausas.
La carga diaria es `moderate_intensity_min + 2 * vigorous_intensity_min`:
**0** en días sin carrera y **NULL** si en una carrera falta algún minuto
necesario, sin inventar cero. ACWR = media móvil 7 d / media móvil 28 d;
`is_reliable` solo es cierto con 28 días válidos y carga crónica positiva.
Ningún valor de ACWR debe interpretarse como diagnóstico de lesión.

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
