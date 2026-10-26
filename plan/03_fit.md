# Etapa 3 — FIT → laps y records

**Estado:** PENDIENTE · **Depende de:** etapas 1 y 2

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
- [ ] **Primera tarea, spike de verificación (D12):** descargar un FIT real de un entreno hecho con workout y comprobar (a) que los `lap` traen `wkt_step_index`, (b) si existe un mensaje `workout`/`workout_step` y su nombre, (c) si la actividad enlaza con el `workoutId` de Garmin (en FIT o en el JSON de la actividad). Anotar el resultado en MEMORY.md; de esto depende la etapa 5.
- [ ] Comprobar cómo se descarga un FIT con la Personal API desde Python (no solo CLI) y documentarlo.
- [ ] Descarga idempotente: si ya hay hash en bronze, no se repite.
- [ ] Parser: convertir semicírculos a grados, `enhanced_speed` a m/s, `timestamp` a UTC.
- [ ] Normalizar `lap` (distancia, tiempo, velocidad media, FC media/max, cadencia, desnivel, `lap_trigger`, `wkt_step_index`).
- [ ] Validar consistencia: suma de laps ≈ `distance_m` de la actividad (tolerancia configurable).
- [ ] Controlar actividades de intervalos: laps de recuperación vs trabajo (preservar `intensity` si existe).
- [ ] Tratar huecos de GPS y pausas (`timer_stop`) sin interpolar a ciegas.
- [ ] Anonimizar un FIT real para convertirlo en fixture (desplazar coordenadas).
- [ ] Tests del parser con FIT sintético/anonimizado.

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
_(rellenar: nº de FIT descargados, gráfica, resultado de reconciliación)_

## Preguntas abiertas
- Resuelta (D12): se corre con el workout del reloj, así que se espera un lap por paso. El spike de arriba confirma si `wkt_step_index` viene en el FIT.
