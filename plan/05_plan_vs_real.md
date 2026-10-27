# Etapa 5 — Plan vs real

**Estado:** HECHA (2026-10-26) · **Depende de:** etapas 3 y 4

## Objetivo
Cruzar cada sesión prescrita en el plan semanal con la actividad ejecutada y medir
el cumplimiento por bloque. Es el diferenciador del proyecto.

## Resultado visible
El informe real de la semana 2026-10-19:

```text
Plan 2026-10-20 → carrera 2026-10-21 | 10x100 + 3x300 + 5x500 + 3x300 | parcial
| bloques con ritmo: 11/23 | desplazado +1 día · confirmación manual
  jog: obj 7:30–7:30, real 6:13 min/km → no cumplido (media)
  work #1: obj 5:30–5:30, real 5:39 min/km → no cumplido (media)
  ...
Bloques verificables: 44/44
Cumplimiento semanal: 40.9 %
```

## Alcance
**Dentro:** ingesta del plan a bronze/silver, vinculación plan↔actividad, mapeo
bloque↔lap, modelo gold `fct_plan_vs_actual`.
**Fuera:** recomendar cambios al plan (etapa 8).

## Entregables
- `ingest/plan_loader.py`: lee `../Garmin/workouts/semana_*.json` (o copia) → bronze `plan/weekly_plan`.
- `silver/parsers/plan.py`: `planned_workouts` y `planned_steps` (ritmos a m/s, recuperación tipificada).
- `silver/plan_confirmations.py`: confirmaciones manuales locales ligadas a `plan_hash`.
- `dbt/models/marts/fct_plan_vs_actual.sql`, `fct_plan_sessions.sql`, `fct_unplanned_runs.sql` e `int_plan_activity_match`.
- Reglas de matching documentadas en `docs/DATA_MODEL.md`.
- Informe `etl_running plan-report --week YYYY-MM-DD`.

## Tareas
- [x] Cargar las dos semanas JSON disponibles (2026-10-19 y 2026-10-26); sin JSON = `no_plan`, no se inventan sesiones. Fuerza y descanso (`skipped`) no se cargan como running.
- [x] `../Garmin/data/uploads.json` contiene 4 `workoutId` de la semana de 2026-10-26; se consulta localmente y no se copia a git. `plan link-workouts` exige nombre API exacto y ±1 día. **0 asociaciones automáticas**: aún no hay carreras de esas fechas.
- [x] Matching conservador: confirmación manual (`plan confirm`) > nombre API > misma fecha > ±1 día. Una actividad no se asigna a dos sesiones. Sin evidencia directa no se declara un `workoutId`.
- [x] Desplazamiento de día: confirmaciones locales aceptan ±1 día y el informe muestra `desplazado +1 día`; la confirmación se invalida si cambia el `plan_hash`.
- [x] Mapeo bloque↔lap: lap exacto por `wkt_step_index` + repetición; si el reloj agrupa repeticiones en un mismo índice, se mide el tramo contiguo (`workout_step_group`); después segmentación por distancia y, para un continuo único, el total de la actividad.
- [x] Regla de cumplimiento: ritmo en el rango objetivo ±5 s/km configurable; recuperaciones y bloques sin ritmo no cuentan como fallos.
- [x] Estados `done`, `partial`, `missed`, `upcoming`, `unplanned_extra`, `no_plan`; sesiones futuras no se clasifican como perdidas.
- [x] Confianza alta solo con asociación confirmada/API **y** lap comprobado; tramo agrupado = media; segmentación/total = baja; sin evidencia = ninguna.
- [x] Tests con plan sintético de series, asociación API, fallback por distancia, sesión perdida, carrera sin plan, confirmación manual y desplazamiento de día.
- [x] Revisión real: el usuario confirmó las cuatro carreras de la semana 2026-10-19, incluidas las dos corridas un día después.

## Criterios de aceptación
```bash
make test
uv run python -m etl_running plan load ../Garmin/workouts/semana_2026-10-19.json
uv run python -m etl_running silver build && make dbt-build
uv run python -m etl_running plan-report --week 2026-10-19
```
- [x] Cada sesión del plan tiene exactamente un estado y a lo sumo una actividad.
- [x] En el caso sintético, los bloques esperados coinciden con los generados (100 % del test).
- [x] Revisión manual de ≥ 3 sesiones reales: cuatro sesiones confirmadas por el usuario; ritmos por bloque calculados desde laps/tramos del FIT.
- [x] Ningún bloque queda con `confidence` alta sin laps que lo respalden (test `no_unbacked_high_confidence`).
- [x] Los días de fuerza y descanso no generan filas de running perdidas.

## Datos de prueba
Plan sintético con las formas del PDF (progresivo, series con pausa por distancia, continuo) y actividades simuladas con ruido controlado. Los tests no leen datos personales.

## Riesgos
- Laps del reloj no alineados con los bloques del plan → tramo agrupado y segmentación, con confianza explícita.
- Ejecutar un entreno en otro día → ventana ±1 día configurable y confirmación manual local.
- El plan cambia durante la semana → versionado por `plan_hash`; las confirmaciones dejan de aplicar si cambia.

## Evidencia
Ejecución local 2026-10-26 (datos privados solo en `lake/`):

- Bronze: 2 semanas JSON; Silver: 8 sesiones / 160 pasos expandidos / 4 IDs Garmin del `uploads.json` local. Repetir `plan load` no escribe archivos nuevos.
- Gold: `make dbt-build` en verde (**83/83 recursos, 65 tests de dbt**); `make test` en verde con **90 tests** Python, incluido lake sintético aislado y lint limpio.
- Semana 2026-10-19: 4 sesiones, 4 carreras confirmadas manualmente (dos con `+1 día`); **44/44 bloques con ritmo verificables**, **18 cumplidos = 40.9 %**.
  - 19/10 Progresivo: 2/3 (6:20 vs 6:30; 6:13 vs 6:15; 6:01 vs 6:00).
  - 21/10 Series: 11/23; 10×100 a 5:39 vs 5:30, 3×300 y 5×500 dentro de objetivo, trote/calentamiento y enfriamiento a 6:13 vs 7:30.
  - 23/10 Series: 5/17; 5×1000 a 5:14 vs 5:10–5:20, 10×100 a 5:17 vs 5:30 y trote/enfriamiento fuera de objetivo.
  - 24/10 10K: 0/1; 6:03 vs 6:30–6:45 (se corrió más rápido que lo prescrito).
- `fct_unplanned_runs`: 1 carrera extra en la semana; 33 carreras anteriores sin JSON quedan `no_plan`. Semana 2026-10-26: 4 sesiones `upcoming`.
- Informe guardado en `lake/_views/plan-report-2026-10-19.txt` (ignorado por git).

## Deuda derivada
- La API devuelve la definición del workout ejecutado (pasos, repeticiones y objetivos) pero **no un `workoutId`**. Ingerirla permitiría separar repeticiones individuales cuando el FIT las agrupa; hoy el tramo agrupado tiene confianza media.
- El JSON del plan fija un ritmo puntual (p. ej. 5:30) mientras el workout enviado al reloj usa un rango (5:20–5:40). Se mantiene la tolerancia ±5 s/km del plan; conviene decidir si se amplía a ±10 s/km.

## Preguntas abiertas
- Resuelta (D12): se corre con el workout enviado al reloj; el mapeo principal es por paso y el desplazamiento de día se confirma manualmente.
- ¿Existen JSON de plan anteriores al 2026-10-19? Actualmente solo hay dos semanas; sin JSON no se puede medir cumplimiento histórico.
