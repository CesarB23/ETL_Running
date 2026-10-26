# Etapa 2 — Silver (actividades running)

**Estado:** HECHA (2026-10-26; pruebas y decisiones verificadas) · **Depende de:** etapa 1

## Objetivo
Convertir bronze en una tabla Parquet de actividades **solo de running**, tipada,
validada y deduplicada, con cuarentena para lo inválido.

## Resultado visible
Se puede abrir DuckDB y ejecutar:
```sql
select date_trunc('week', start_utc) as semana, count(*) runs, round(sum(distance_m)/1000,1) km
from read_parquet('lake/silver/activities.parquet')
where not is_manual
group by 1 order by 1;
```
más `etl_running silver report` con filas procesadas, rechazadas, `out_of_scope` y cobertura.

## Alcance
**Dentro:** tabla `activities` (solo running), contrato Pandera, cuarentena, filtro por
`RUNNING_TYPE_KEYS`, reconstrucción completa desde bronze.
**Fuera:** laps/records (etapa 3), `planned_*` (etapa 5), métricas (etapa 4) y todo dato de salud (D15).

## Entregables
- `silver/parsers/activities.py`: payload → DataFrame con columnas del modelo.
- `silver/schemas.py`: contrato Pandera.
- `silver/build.py`: lee la última versión por `dt` de bronze, filtra a running, hace upsert y escribe Parquet.
- `lake/silver/_quarantine/activities.parquet` con `reason`, `source_path`.
- CLI (`argparse`): `silver build [--full-refresh]`, `silver report`.
- Diccionario de campos Garmin → silver en `docs/DATA_MODEL.md`.

## Tareas
- [x] Mapear campos de `activities` (nombres Garmin → silver), conversión UTC/local con `tz_local`.
- [x] Filtro de alcance: conservar solo `activityType.typeKey ∈ RUNNING_TYPE_KEYS`; contar el resto como `out_of_scope` (no a cuarentena: no es error).
- [x] `is_manual` desde `manualActivity`; `has_gps` (falso en cinta o sin coordenadas).
- [x] Extraer `moderate_intensity_min` y `vigorous_intensity_min` (insumo de la carga).
- [x] Contrato: tipos, rangos (FC 30–230 o `NULL`, `distance_m >= 0`, `duration_s > 0`), unicidad de `activity_id`.
- [x] Estrategia de versiones: la última por `ingested_at` gana.
- [x] `--full-refresh` regenera todo desde bronze con resultado idéntico.
- [x] Tests con fixtures sintéticos: running normal, manual, sin FC, cinta, ciclismo y `other` (estos dos deben salir como `out_of_scope`).

## Criterios de aceptación
```bash
make test
etl_running silver build --full-refresh
etl_running silver build                    # 2.ª vez: sin cambios
etl_running silver report
duckdb -c "select count(*), count(distinct activity_id), count(distinct activity_type) from 'lake/silver/activities.parquet'"
```
- `count(*) = count(distinct activity_id)`.
- Todo `activity_type` en silver pertenece a `RUNNING_TYPE_KEYS` (test).
- Reconciliación: `activities en bronze = silver + cuarentena + out_of_scope`.
- Re-ejecutar no cambia el contenido: mismo hash lógico de la tabla (test).
- `full-refresh` ≡ incremental (test de equivalencia sobre fixtures).
- Cero valores `0` donde el origen es nulo (test sobre actividades sin FC).

## Datos de prueba
Fixture sintético con: running manual, sin FC, cinta, duplicado en dos ventanas de ingesta, ciclismo y `other`, y una con cambio de hora (DST).

## Riesgos
- Cambios de esquema entre fechas antiguas y recientes → parsers tolerantes + warnings, no fallos silenciosos.
- Zona horaria: `startTimeLocal` sin offset → derivar `tz_local` de GMT vs local y validar con DST.
- Un tipo de carrera no previsto (p. ej. `virtual_run`) queda fuera sin avisar → el reporte lista los `typeKey` descartados.

## Evidencia
Ejecución local 2026-10-26 (datos reales solo en `lake/`, ignorado por git):

- Bronze: 43 actividades únicas → silver: **38 running**, cuarentena: **0**, fuera de alcance: **5** (`cycling=2`, `other=2`, `walking=1`). Reconciliación OK.
- `silver build` por segunda vez: **sin cambios**. `--full-refresh` construye 38 filas.
- DuckDB: `count(*) = count(distinct activity_id) = 38`, un solo `activity_type`.
- Consulta semanal (ver resultado visible): 10 semanas entre 2026-08-17 y 2026-10-19; por ejemplo la semana de 2026-10-19: 5 carreras, 45.3 km.
- Los tests sintéticos verifican manual, sin FC, cinta, DST, duplicados/versiones, cuarentena, idempotencia y CLI.
- `pytz` es requerido por DuckDB para truncar fechas de Parquet con zona UTC; fijado en `pyproject.toml`/`uv.lock`.
- Con volumen personal pequeño, cambios en bronze provocan reconstrucción completa de silver; sin cambios se omite la escritura. El resultado es equivalente a un upsert por `activity_id`, pero **no hay upsert físico incremental**.
- Parquet sin compresión para compatibilidad con visores de VS Code: 38 filas, 19 KB; 77 tests y lint en verde. Segunda ejecución: sin reescritura.

## Preguntas abiertas
- Resueltas por el usuario: **conservar** lat/lon de inicio en Silver (datos locales ignorados por git, no mostrar en gold/UI por defecto); **incluir** `treadmill_running` como running con `has_gps = false`.
