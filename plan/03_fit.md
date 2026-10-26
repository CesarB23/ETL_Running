# Etapa 3 — FIT → laps y records

**Estado:** HECHA (2026-10-26; datos locales y tests verificados) · **Depende de:** etapas 1 y 2

## Objetivo
Obtener el detalle segundo a segundo de cada carrera descargando y parseando los
archivos FIT, y exponerlo en `activity_laps` y `activity_records`.

## Resultado visible
`etl_running show-run <activity_id>` genera un PNG/HTML con ritmo, FC y cadencia
a lo largo del tiempo y la tabla de laps. Es la primera vez que se **ve** el
entrenamiento de la serie.

## Alcance
**Dentro:** descarga FIT por actividad running (solo con GPS/FC, no manuales ni cinta sin sensores), bronze de FIT,
parser, tablas silver, vista de verificación.
**Fuera:** métricas derivadas (etapa 4).

## Entregables
- `ingest/fit_download.py`: descarga ZIP vía API (automatiza `gc-personal activity-download`), lista de pendientes = actividades en silver sin FIT en bronze.
- Bronze: `lake/bronze/garmin/activity_fit/dt=…/<activity_id>.zip` (+ manifiesto).
- `silver/parsers/fit.py` con `fitdecode`: mensajes `record`, `lap`, `session`.
- Tablas `activity_laps` y `activity_records`.
- `tools/show_run.py` (matplotlib o plotly).
- Registro de actividades sin FIT con su motivo (manual, sin descarga, error).

## Tareas
- [x] **Spike D12:** FIT real de intervalos: 34/35 laps con `wkt_step_index`; mensajes `workout` y API `get_activity_workouts` presentes. No aparece un `workoutId` explícito en la lista devuelta: confirmar enlace exacto en etapa 5 (ver MEMORY.md).
- [x] Descarga Python con `GarminPersonalApiClient.download_activity(id)` → ZIP de FIT (auth/reintentos compartidos).
- [x] Descarga idempotente: actividades con FIT en el manifiesto no se solicitan de nuevo.
- [x] Parser: semicírculos → grados; `enhanced_speed` (ya escalado por fitdecode) → m/s; timestamp → UTC.
- [x] Laps tipados con métricas, `lap_trigger`, `intensity`, `wkt_step_index`.
- [x] Reconciliación de distancia de laps con actividad (umbral 1 % por defecto; divergencias registradas).
- [x] Distinguir trabajo/recuperación con `intensity` y pasos workout.
- [x] Guardar `timer_running` y huecos sin interpolación; HTML separa trazos en pausas y saltos > 5 s.
- [x] Fixture FIT **sintético**, en lugar de transformar uno real: coordenadas ficticias, CRC correcto, 5 minutos, series y FIT corrupto (más seguro para repo público).
- [x] Tests del parser, descarga, idempotencia, tablas silver y HTML con FIT sintético.

## Criterios de aceptación
```bash
make test
etl_running fit download --pending
etl_running silver build --only activity_laps activity_records
etl_running show-run <activity_id> --out /tmp/run.html
duckdb -c "select activity_id, count(*) from 'lake/silver/activity_laps.parquet' group by 1 order by 1 limit 5"
```
- Para cada actividad con FIT: `abs(sum(lap.distance) − activity.distance_m) / distance_m < 1 %` (o queda registrada la excepción).
- Re-ejecutar la descarga no baja nada nuevo.
- `activity_records` no tiene timestamps duplicados por actividad.
- Las actividades manuales aparecen en el registro de "sin FIT: manual", no como error.
- Una gráfica y la tabla de laps de una carrera de series muestran visiblemente los bloques de trabajo y recuperación.

## Datos de prueba
Un FIT anonimizado corto (~5 min) y uno de series; uno corrupto para probar el manejo de errores.

## Riesgos
- El API puede no exponer descarga FIT en todos los casos → plan B: `garminconnect` o export manual desde Garmin Connect.
- Volumen: 1 FIT ≈ cientos de KB; con cientos de actividades sigue siendo manejable. Parquet con compresión zstd.
- Dispositivos con campos distintos (running dynamics) → columnas opcionales.

## Evidencia
Ejecución real 2026-10-26, exclusivamente en `lake/` (ignorado por git):

- 38 FIT ZIP descargados (38 actividades running); segunda ejecución: **0 pendientes**.
- 587 laps, 20 610 records, 0 discrepancias de distancia mayores o iguales a 1 %;
  587 claves de lap y 20 610 timestamps por actividad únicos.
- Gráfica HTML con ritmo, FC, cadencia y tabla de laps generada en `lake/_views/run.html`.
- Spike: primera carrera comprobada tenía campo `wkt_step_index` pero **todos sus valores nulos**;
  una carrera de intervalos tenía **34/35 valores no nulos**, mensajes `workout` y
  `get_activity_workouts` devolvió una lista asociada. Sus campos no incluyen
  `workoutId`; no afirmar correspondencia directa de IDs en la etapa 5 sin verificación.
- 83 tests (incluido FIT sintético, pausas y series) y lint en verde; ninguno de los ZIP reales se versiona ni se usa como fixture.

## Preguntas abiertas
- `wkt_step_index` viene poblado en FIT con workout, no necesariamente en todas las carreras.
  Pendiente de etapa 5: cómo enlazar ID de workout del plan con `get_activity_workouts`,
  que devuelve pasos/nombre pero no `workoutId` explícito.
