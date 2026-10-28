# Orquestación local con Dagster

El pipeline de running está definido en `orchestration/` y reutiliza las funciones
de ingesta, Silver, FIT, plan y alertas existentes. Dagster coordina; no duplica la
lógica de transformación. Gold sigue construyéndose con dbt.

## Requisitos y arranque

- Python 3.12 y dependencias instaladas con `uv sync`.
- `.env` local con acceso Garmin válido (`GARMIN_API_KEY`) para ejecuciones reales.
- `lake/` y `dbt/target/manifest.json` se generan localmente y no se versionan.

```bash
make dbt-manifest         # deps + manifest dbt si hace falta
make dev                  # Dagster UI en http://localhost:3000
make run-daily            # ejecuta daily_pipeline sin partición
```

El schedule diario es a las **20:00 America/Mexico_City**. `make dev` debe seguir activo
para que el daemon evalúe schedules y sensores; cerrar la UI apaga ese proceso.
El job ejecutado directamente sin partición usa la fecha local actual, limitada por
`START_DATE`. Schedule y backfills usan la partición diaria de Bronze.

## Assets y calidad

El grafo cubre actividades y FIT de Bronze, actividades/plan/FIT/vínculos de Silver,
modelos y tests dbt en Gold y alertas locales. Los checks de frescura (36 h), volumen
y reconciliación Bronze↔Silver son no bloqueantes. Los tests dbt se muestran como
asset checks cuando dbt puede asociarlos a un modelo; tests singulares con varias
dependencias pueden aparecer como observaciones dbt.

Garmin tiene hasta 2 reintentos exponenciales, Silver 1 reintento y dbt 1 reintento.
Los límites por asset se declaran con `dagster/max_runtime` (60 min para Garmin,
30 min para transformación local). Las reejecuciones usan las mismas funciones
idempotentes del ETL.

## Backfills y reejecución

En Dagster UI, abre **Backfills**, elige `daily_pipeline`, selecciona el rango de
particiones que quieres reconstruir y lanza el backfill. Para materializar un asset
aislado, usa **Assets → Materialize** y elige la partición. Un `make run-daily`
manual no requiere seleccionar una partición.

Una caída de Garmin agota la política de reintento y deja el run fallido en Dagster.
El sensor `pipeline_failure_log` añade el detalle a
`lake/_state/orchestration_failures.log`; no manda mensajes externos. El sensor
`new_activity_sensor` se evalúa cada 15 minutos y lanza el job si detecta FIT
pendiente o Bronze más reciente que Silver.

## Runtime Mac con launchd

La plantilla `orchestration/launchd/com.etl-running.daily.plist` programa un
LaunchAgent a las 20:00 según la zona horaria configurada en macOS. Para que
coincida con Dagster, configura el Mac en `America/Mexico_City`. Instálalo con:

```bash
make launchd-install
```

El wrapper ejecuta `make run-daily` bajo `caffeinate` y escribe stdout/stderr en
`lake/_state/launchd.*.log`. Para desinstalarlo, usa el dominio de tu usuario:

```bash
launchctl bootout "gui/$(id -u)/com.etl-running.daily"
rm "$HOME/Library/LaunchAgents/com.etl-running.daily.plist"
```

El Mac debe estar encendido y con la sesión de usuario disponible a la hora
programada. `caffeinate` evita la suspensión mientras corre el job, pero no puede
iniciar una máquina apagada ni garantiza una ejecución cuando el usuario no ha
iniciado sesión. La instalación del LaunchAgent es local; no forma parte del
checkout y no se activa automáticamente.

## Validación sintética

```bash
uv run pytest tests/unit/test_orchestration.py -q
plutil -lint orchestration/launchd/com.etl-running.daily.plist
```

Los tests usan Garmin falso y Parquet sintético. No se incluyen credenciales,
coordenadas ni datos del lake en las pruebas versionadas.
