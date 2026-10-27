# ETL_Running

Plataforma de datos personal sobre mis **actividades de running** de Garmin Connect,
con arquitectura medallion local: **bronze → silver → gold → dashboard**.

Responde a tres preguntas: ¿cumplo el plan?, ¿cómo evolucionan mi ritmo y mi
eficiencia?, ¿cómo va mi carga de entrenamiento? Solo running; otros deportes y datos
de salud están fuera de alcance. Licencia MIT.

## Navegación

| Documento | Para qué |
| --- | --- |
| `CLAUDE.md` | Reglas y convenciones para agentes y colaboradores |
| `MEMORY.md` | Estado vivo, decisiones y hechos sobre los datos |
| `docs/ARCHITECTURE.md` | Capas, flujo y decisiones técnicas |
| `docs/DATA_MODEL.md` | Tablas bronze/silver/gold, claves y reglas |
| `plan/README.md` | Roadmap y cómo se verifica cada etapa |
| `plan/00..08_*.md` | Plan detallado por etapa con criterios de aceptación |

## Inicio rápido

```bash
make setup                       # uv sync (Python 3.12)
cp .env.example .env             # y pega tu GARMIN_PERSONAL_API_KEY
make test && make lint
uv run python -m etl_running --help
uv run python -m etl_running config
```

## Estado

Etapa 0 (fundamentos) implementada; la ingesta empieza en `plan/01_bronze_ingesta.md`.

Con bronze cargado, construye la tabla de actividades de running en silver:

```bash
uv run python -m etl_running silver build --full-refresh
uv run python -m etl_running silver report
```

La tabla queda en `lake/silver/activities.parquet` (datos personales: ignorados por git).
El comando `silver build` sin `--full-refresh` no reescribe si bronze no cambió.

Para el detalle de laps y registros por segundo (etapa 3):

```bash
uv run python -m etl_running fit download --pending
uv run python -m etl_running silver build --only activity_laps activity_records
uv run python -m etl_running show-run <activity_id> --out lake/_views/run.html
```

Abre `lake/_views/run.html` en tu navegador. El gráfico y los ZIP originales
son privados, permanecen dentro de `lake/` y no se versionan.

## Gold (dbt + DuckDB)

Tras construir las tres tablas Silver, genera el almacén analítico:

```bash
make dbt-build   # instala dbt_utils, construye vistas/tablas y ejecuta tests
make dbt-docs    # genera y sirve el linaje local (detener con Ctrl+C)
```

Los marts viven en `lake/warehouse.duckdb`, esquema `gold` (ignorado por git).
Ejemplo sin instalar el CLI de DuckDB:

```bash
uv run python -c "import duckdb; print(duckdb.connect('lake/warehouse.duckdb', read_only=True).execute('select week_start, distance_km from gold.fct_weekly_summary order by 1').fetchall())"
```

El código y las pruebas de CI utilizan **únicamente datos sintéticos**; tu lake
real nunca se sube al repositorio.

## Plan vs real

Desde la raíz del repo, con tus JSON de semana (no se versionan):

```bash
uv run python -m etl_running plan load ../Garmin/workouts/semana_2026-10-19.json
uv run python -m etl_running silver build
uv run python -m etl_running plan link-workouts   # opcional: requiere API key
uv run python -m etl_running plan confirm --date 2026-10-20 --activity-id 123456789
make dbt-build
uv run python -m etl_running plan-report --week 2026-10-19
```

`../Garmin/data/uploads.json` se usa solo si existe para contrastar el nombre
del workout con la API; no se versiona. `plan confirm` registra en local que un
entreno se corrió otro día (±1) sin modificar el plan original. Semanas sin JSON
son `no_plan` y los ritmos sin lap, tramo o segmento verificable quedan **sin
dato**, no como fallo.
