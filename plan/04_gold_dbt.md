# Etapa 4 — Gold con dbt

**Estado:** HECHA (2026-10-26) · **Depende de:** etapas 2 y 3

## Objetivo
Construir el modelo analítico con dbt-duckdb: dimensiones, hechos y métricas de
rendimiento y carga de las actividades de running, con tests y documentación.

## Resultado visible
`make dbt-build` termina en verde, `dbt docs serve` muestra el linaje y existen
consultas de negocio que responden:
- ¿Cómo evolucionan mi ritmo y mi eficiencia aeróbica por mes?
- ¿Cuál es mi carga aguda/crónica de las últimas 8 semanas?
- ¿Cuántos km por semana llevo?

## Alcance
**Dentro:** proyecto dbt, `sources` sobre Parquet silver, `staging`, marts
(`dim_date`, `fct_runs`, `fct_run_laps`, `fct_training_load`,
`fct_weekly_summary`, `mart_data_quality`), tests y docs.
**Fuera:** `fct_plan_vs_actual` (etapa 5), datos de salud/recuperación (D15).

## Entregables
- `dbt/dbt_project.yml`, `profiles.yml` (DuckDB en `lake/warehouse.duckdb`), `packages.yml` (dbt_utils).
- `dbt/models/staging/stg_*.sql` (una por tabla silver, solo renombrado y casts).
- `dbt/models/marts/*.sql` + `schema.yml` con descripciones y tests.
- Macros: `pace_min_km`, `rolling_avg`.
- Parámetros en `vars`: ventanas aguda/crónica (7/28). Sin FCmax/FC reposo (D13).
- `analyses/` con las consultas de negocio de arriba.

## Tareas
- [x] Configurar dbt-duckdb con `sources` external_location de Parquet silver.
- [x] Staging por tabla silver, sin coordenadas GPS en Gold.
- [x] `dim_date` con `dbt_utils.date_spine`.
- [x] `fct_runs`: ritmo, eficiencia aeróbica, drift (si hay records), flags `is_valid_for_pace`.
- [x] `fct_training_load`: **carga = `moderate_min + 2·vigorous_min`** por actividad → agregado diario → medias móviles 7/28 → ACWR. Días sin entrenamiento = 0; minutos ausentes = NULL. `is_reliable=false` con historial insuficiente o carga crónica nula.
- [x] Tests genéricos (`unique`, `not_null`, `relationships`, `accepted_values`) y singulares (ACWR ≥ 0, ritmo plausible 2:30–12:00 min/km).
- [x] Documentar métricas en `schema.yml` según `docs/DATA_MODEL.md`.
- [x] Verificar métricas **a mano** con 3 actividades reales (usuario confirmó coincidencia exacta con Garmin Connect).

## Criterios de aceptación
```bash
make dbt-build                       # run + test sin fallos
dbt docs generate && dbt docs serve  # linaje visible
duckdb lake/warehouse.duckdb -c ".read dbt/analyses/weekly_km.sql"
```
- 100 % de tests dbt en verde; cada modelo tiene al menos `unique` + `not_null` en su clave.
- El ritmo medio de 3 actividades coincide con Garmin Connect (±2 s/km).
- Los km semanales de `fct_weekly_summary` coinciden con la suma manual de silver.
- ACWR de la última semana calculado a mano = valor del modelo (±0.01).
- `dbt build` es idempotente (segunda ejecución produce las mismas filas).

## Datos de prueba
`dbt seed` con un mini silver sintético de 6 semanas para tests de ventanas móviles; resultados esperados en CSV (`dbt test` los compara).

## Riesgos
- Fórmula de carga depende de los minutos de intensidad de Garmin, que dependen de zonas internas del reloj (que el usuario no configura) → documentarlo como limitación y comparar contra duración×ritmo.
- Con la ventana desde 2026-08-17, ACWR es fiable solo desde ~2026-09-14 (`is_reliable`).

## Evidencia
Ejecución local 2026-10-26:

- `make dbt-build`: 1 seed, 6 tablas, 3 vistas, 34 pruebas dbt; **44/44 PASS**. `make test`: **84 tests** (incluido lake sintético aislado); `make lint` en verde.
- `dbt docs generate`: `dbt/target/catalog.json` generado; `make dbt-docs` sirve el linaje local.
- DuckDB `lake/warehouse.duckdb`: 38 carreras, 587 laps, 71 días, 11 semanas;
  `fct_weekly_summary` total 244.80 km = suma independiente de `silver.activities`.
- ACWR último día verificado manualmente desde 28 cargas diarias: 1.3474, idéntico a Gold.
- Ritmo de 3 actividades recalculado desde la velocidad de Silver: 0 s/km de diferencia.
  El usuario cotejó las actividades de 2026-10-23, 24 y 25 con la UI de Garmin Connect:
  **6:51, 6:03 y 8:46 min/km respectivamente**, coincidencia exacta (±0 s/km).
- Test aislado con Silver sintético de seis semanas: carga NULL vs 0, ACWR tras 28 días,
  km semanales y segunda construcción idempotente. `dbt seed` contiene expectativas
  semanales fijas, sin datos personales.
- `dbt/analyses/` ejecutadas en DuckDB: km semanales (11 filas), ritmo/eficiencia
  mensual (3 meses; octubre: 11 ritmos válidos, media 6.42 min/km) y carga de
  las últimas 8 semanas (57 días). Todos los datos reales están solo en `lake/`.

## Preguntas abiertas
- Resueltas: sin FCmax/FC reposo (D13) y sin datos de salud (D15); no hay TRIMP.
- Pendiente: ¿vale la pena añadir una carga alternativa basada en ritmo respecto al plan (esfuerzo relativo)? Evaluar tras ver los datos reales.
