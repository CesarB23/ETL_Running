# Etapa 6 — Orquestación

**Estado:** EN CURSO · **Depende de:** etapas 1–5

> Se ejecuta después de la etapa 7 (D21). Runtime decidido: Mac con `launchd` y
> `caffeinate` (D23); el Mac debe estar encendido y con la sesión iniciada.

## Objetivo
Automatizar el pipeline de extremo a extremo con Dagster: dependencias explícitas,
programación diaria, reintentos y visibilidad.

## Resultado visible
Dagster UI (`make dev`) muestra el grafo de assets bronze → silver → gold, y un
schedule diario que corre sin intervención. Un fallo deliberado muestra el error y
se reintenta.

## Alcance
**Dentro:** assets Dagster para ingesta, silver, dbt (con `dagster-dbt`), schedule,
sensor de actividades nuevas, checks de calidad como *asset checks*, alertas básicas.
**Fuera:** despliegue en la nube (etapa 8).

## Entregables
- `orchestration/definitions.py`, `assets/{bronze,silver,fit,plan}.py`, `dbt_assets.py`.
- Particiones diarias en assets de ingesta; backfill desde la UI.
- `schedules.py`: diario a las 20:00 America/Mexico_City y `sensors.py` para nuevas actividades.
- Asset checks: frescura, volumen, reconciliación bronze↔silver, tests dbt.
- `launchd` plist o servicio equivalente para correr Dagster en tu Mac (documentado).
- `make dev` y `make run-daily`.

## Tareas
- [x] Envolver cada paso de CLI como asset sin duplicar lógica (los assets llaman a las mismas funciones).
- [x] Integrar el proyecto dbt como assets con linaje.
- [x] Configurar políticas de reintento y *timeouts* por asset.
- [x] Checks de frescura (≤ 36 h sin datos → warning), volumen y reconciliación.
- [x] Schedule diario a las 20:00 America/Mexico_City; job completo ejecutado manualmente.
- [x] Confirmar un tick automático del schedule a las 20:00 America/Mexico_City.
- [x] Sensor: evalúa FIT pendientes y Bronze más reciente que Silver; pruebas sintéticas cubren `SkipReason` y `RunRequest`.
- [ ] Confirmar en el daemon que una actividad FIT pendiente real lanza `daily_pipeline`.
- [x] Notificación de fallos registrada en `lake/_state/orchestration_failures.log` (sin canales externos).
- [x] Documentar operación, backfill, relanzamiento y LaunchAgent.

## Criterios de aceptación
```bash
make dev                                   # UI accesible, grafo completo
dagster job execute -j daily_pipeline      # corre de punta a punta en verde
```
- [x] Ejecución sintética completa desde lake temporal vacío reconstruye Bronze→Silver→Gold; dbt pasa.
- Una segunda ejecución inmediata no crea bronze nuevo (idempotencia).
- [x] Simular un fallo HTTP 503 sintético en un asset Dagster: agota reintentos y registra el motivo en log temporal.
- [x] El schedule se disparó en el entorno real y su tick/run quedaron registrados.
- [x] Confirmar visualmente en Dagster UI los asset checks y sus resultados: el usuario reporta todos verdes.

## Datos de prueba
Ejecución con cliente simulado en CI; ejecución real manual.

## Riesgos
- Dagster en Python 3.12 + dbt: conflictos de versiones → fijar versiones compatibles en `pyproject.toml`.
- Un Mac que duerme no ejecuta el schedule → documentar `launchd`/`caffeinate` o mover a nube en etapa 8.

## Evidencia
- `make run-daily` sin partición, 2026-10-27: run `3b53c444-d17b-4c10-b855-7955799eb47a`, éxito; dbt **84/84 PASS**.
- Segunda ejecución sin partición: run `8e237183-16ed-41ee-b659-cc8ef4b4b66a`, éxito; ingesta `fetched=0`, `files_written=0`, `files_skipped=1`.
- `test_full_daily_job_builds_gold_from_empty_temporary_lake`: ejecución Dagster completa con Garmin falso, lake temporal nuevo y tablas Gold verificadas; **84/84 tests dbt PASS**.
- `make dev`: UI respondió HTTP 200 en localhost:3000; schedule figura RUNNING (20:00 America/Mexico_City), sensores RUNNING.
- Tick automático real #550 el 2026-10-27 20:00 America/Mexico_City: `SUCCESS`, run `49f2a3b7-5762-4579-9634-8eacb2e64de6`, partición `2026-10-27`; ingesta `fetched=1`, `files_written=1`; Gold contiene 1 carrera, 14 laps y un vínculo de plan.
- Revisión manual de la UI por el usuario: todos los asset checks visibles en verde.
- Preview de `new_activity_sensor`: `SkipReason` esperado porque no había FIT pendiente (`ya_descargado=38`).
- Reintento de Dagster probado con fallo transitorio sintético fuera del lake: 1 `STEP_UP_FOR_RETRY`, intento 2 y éxito.
- `uv run pytest tests/unit/test_orchestration.py -k failure -q`: asset de prueba falla 3 veces, Dagster emite 2 reintentos y el sensor escribe el motivo en `lake/_state/orchestration_failures.log` bajo `tmp_path`; se comprueba también la política de reintento de Bronze.
- `plutil -lint orchestration/launchd/com.etl-running.daily.plist`: OK.
- Pendientes: sensor con FIT pendiente real y relanzamiento del run por el daemon.

## Decisión de runtime
- Resuelto (D23): Mac local con `launchd` + `caffeinate`; no desplegar en nube (etapa 8 fuera de alcance).
