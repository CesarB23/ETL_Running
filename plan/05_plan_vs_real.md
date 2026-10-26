# Etapa 5 — Plan vs real

**Estado:** PENDIENTE · **Depende de:** etapas 3 y 4

## Objetivo
Cruzar cada sesión prescrita en el plan semanal con la actividad ejecutada y medir
el cumplimiento por bloque. Es el diferenciador del proyecto.

## Resultado visible
Una tabla semanal, por ejemplo:

| Día | Sesión | Bloques cumplidos | Ritmo objetivo | Ritmo real | Desviación |
| --- | --- | --- | --- | --- | --- |
| Jue 22 | 10×100 + 5×1000 | 14/15 | 5:10–5:20 | 5:14 | −2 s/km |

y un `% de cumplimiento` semanal en `fct_weekly_summary`.

## Alcance
**Dentro:** ingesta del plan a bronze/silver, vinculación plan↔actividad, mapeo
bloque↔lap, modelo gold `fct_plan_vs_actual`.
**Fuera:** recomendar cambios al plan (etapa 8).

## Entregables
- `ingest/plan_loader.py`: lee `../Garmin/workouts/semana_*.json` (o copia) → bronze `plan/weekly_plan`.
- `silver/parsers/plan.py`: `planned_workouts` y `planned_steps` (ritmos a m/s, recuperación tipificada).
- `dbt/models/marts/fct_plan_vs_actual.sql` y modelo intermedio `int_plan_activity_match`.
- Reglas de matching documentadas en `docs/DATA_MODEL.md`.
- Informe `etl_running plan-report --week YYYY-MM-DD`.

## Tareas
- [ ] Cargar el plan de la semana 2026-10-19 y validar contra el esquema del PDF parseado. Para semanas anteriores (desde 2026-08-17) solo hay plan si existen sus JSON; las semanas sin plan se marcan `no_plan` y las actividades quedan `unplanned`.
- [ ] Recuperar o regenerar la relación `workoutId ↔ fecha` (el `uploads.json` de `../Garmin/` ya no existe): consultar el calendario de Garmin en la ingesta (dataset adicional `garmin/calendar`) o leer el `workoutId` desde el FIT/actividad según el spike de la etapa 3.
- [ ] **Matching sesión↔actividad (D12):** 1.º por `workoutId`/nombre del workout si el FIT o la actividad lo traen; 2.º misma fecha local, tipo running, no manual; si hay varias, mayor solape duración/distancia; si ninguna, `missed`.
- [ ] **Mapeo bloque↔lap (D12):** por `wkt_step_index` ↔ `planned_steps.step_order` (`match_method = wkt_step`, `confidence = high`). Respaldo si el FIT no trae índices: segmentar `activity_records` por distancia acumulada (`distance_segmentation`, `confidence = low`).
- [ ] Definir regla de cumplimiento: ritmo medio del bloque dentro del rango objetivo ±tolerancia (parámetro, por defecto 5 s/km).
- [ ] Estados por sesión: `done`, `partial`, `missed`, `unplanned_extra`.
- [ ] Marcar `confidence` del mapeo (alta si hay laps nítidos, baja si fue por segmentación).
- [ ] Tests con una sesión sintética de series y su actividad simulada.
- [ ] Revisar manualmente la semana real y corregir reglas.

## Criterios de aceptación
```bash
make test
etl_running plan load ../Garmin/workouts/semana_2026-10-19.json
etl_running silver build && make dbt-build
etl_running plan-report --week 2026-10-19
```
- Cada sesión del plan tiene exactamente un estado y a lo sumo una actividad.
- En el caso sintético, los bloques esperados coinciden con los generados (100 % del test).
- Revisión manual de ≥ 3 sesiones reales: el reporte coincide con lo que Garmin muestra por vuelta.
- Ningún bloque queda con `confidence` alta sin laps que lo respalden.
- Los días de fuerza y descanso no generan filas de running perdidas.

## Datos de prueba
Plan sintético con las formas del PDF (progresivo, series con pausa por distancia, continuo) y actividades simuladas con ruido controlado.

## Riesgos
- Laps del reloj no alineados con los bloques del plan → fallback por distancia; dejar claro el nivel de confianza.
- Ejecutar un entreno en otro día → permitir ventana ±1 día configurable.
- El plan cambia durante la semana → versionar por `plan_hash`.

## Evidencia
_(rellenar: informe de una semana real y la revisión manual)_

## Preguntas abiertas
- Resuelta (D12): se corre con el workout enviado al reloj; el mapeo principal es por paso.
- ¿Tienes los JSON/PDF de semanas anteriores al 2026-10-19 (desde 2026-08-17)? Si no, el historial de cumplimiento empieza en esa semana y crece cada semana.
