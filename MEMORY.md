# MEMORY.md — estado vivo de ETL_Running

Este archivo es la memoria del proyecto. Se actualiza al cerrar cada tarea.
Un agente nuevo debe leer esto después de `CLAUDE.md` y antes de empezar.

_Última actualización: 2026-10-26 (etapas 0–5 y 7 cerradas; siguiente: 6 orquestación)._

## Estado de las etapas

| # | Etapa | Estado | Plan |
| --- | --- | --- | --- |
| 0 | Fundamentos | HECHA | `plan/00_fundamentos.md` |
| 1 | Bronze incremental + backfill | HECHA | `plan/01_bronze_ingesta.md` |
| 2 | Silver (actividades running) | HECHA | `plan/02_silver.md` |
| 3 | FIT → laps y records | HECHA | `plan/03_fit.md` |
| 4 | Gold con dbt | HECHA | `plan/04_gold_dbt.md` |
| 5 | Plan vs real | HECHA | `plan/05_plan_vs_real.md` |
| 6 | Orquestación | PENDIENTE | `plan/06_orquestacion.md` |
| 7 | Dashboard y alertas | HECHA | `plan/07_dashboard_alertas.md` |
| 8 | Extras (ML, nube, observabilidad) | PENDIENTE | `plan/08_extras.md` |

Estados: `PENDIENTE` · `EN CURSO` · `BLOQUEADA` · `HECHA`.
**Etapa activa:** ninguna; la siguiente es la 6 (Orquestación). Orden ejecutado:
0–5 → 7 → 6 → 8 (D21).

## Contexto del usuario y objetivo

- Corredor con plan de entrenamiento semanal en PDF (`../Garmin/pdfs/CÉSAR 2026.pdf`),
  que ya se convierte en workouts estructurados, se suben a Garmin Connect, se envían
  al reloj y se corren con el workout activo.
- Historial relevante: **desde 2026-08-17** (D10).
- No hace seguimiento de FCmax ni FC de reposo (D13).
- **Solo le interesan las actividades de running** (D15); todo lo demás está fuera.
- Objetivo: proyecto E2E de ingeniería de datos de **uso personal real y a la vez
  pieza de portafolio** (D11). Preguntas clave a responder:
  1. ¿Cumplo los ritmos y series prescritos? (plan vs real)
  2. ¿Cómo evolucionan mi ritmo, volumen y eficiencia aeróbica?
  3. ¿Cuál es mi carga de entrenamiento y hay riesgo de sobrecarga?
- Idioma de trabajo: español.

## Decisiones (ADR resumidas)

| ID | Decisión | Porqué | Alternativa descartada |
| --- | --- | --- | --- |
| D1 | Local-first, costo cero | Volumen personal (MB–pocos GB); iterar rápido | Nube desde el inicio (se deja a etapa 8) |
| D2 | DuckDB + Parquet | Sin servidor, SQL potente, ideal para datos personales | PostgreSQL |
| D3 | dbt-duckdb para gold | Tests, docs y linaje de serie | SQL suelto / Polars |
| D4 | Dagster desde etapa 6 | Modela tablas como assets con dependencias | Airflow (pesado), cron (poca visibilidad) |
| D5 | Python 3.12 para este repo | El venv de `../Garmin/` es 3.14; dbt/Dagster pueden no soportarlo bien | Reutilizar 3.14 |
| D6 | Bronze inmutable particionado por fecha | Reproducibilidad y tolerancia a cambios de esquema de Garmin | Guardar solo datos limpios |
| D7 | Copiar, no importar, código de `../Garmin/` | Mantener repos desacoplados | Imports cruzados / monorepo |
| D8 | Fixtures solo sintéticos/anonimizados | Datos de salud y GPS | Fixtures reales |
| D9 | Tabla de plan en silver viene del JSON ya parseado (`workouts/semana_*.json`) | Ya está validado en `../Garmin/` | Re-parsear el PDF |

Decisiones tomadas con las respuestas del usuario (2026-10-25):

| ID | Decisión | Porqué |
| --- | --- | --- |
| D10 | **Ventana histórica fija: desde 2026-08-17.** Backfill y todo el pipeline parten de esa fecha (`START_DATE` en config). Nada anterior se ingesta. | Respuesta del usuario; acota volumen y tiempo de backfill |
| D11 | **Doble propósito: uso personal real + portafolio de Data Eng.** El repo es público-izable: CI, README, docs, demo con warehouse sintético y cero datos reales versionados. La etapa 8 pasa a incluir la opción D (publicación) como recomendada. | Respuesta del usuario |
| D12 | **Los entrenos se crean con `../Garmin/plan_run.py`/`week_import.py`, se envían al reloj y se corren con el workout.** Por tanto los laps del FIT siguen los pasos del plan y se pueden mapear por `wkt_step_index` (no por segmentación por distancia, que queda de respaldo). | Respuesta del usuario |
| D13 | **No hay FCmax ni FC de reposo fijadas por el usuario y no las trackea.** No se usan parámetros fisiológicos. La carga es `load = moderate_min + 2·vigorous_min` (minutos de intensidad de Garmin de la propia actividad). **TRIMP descartado** (necesitaría FC reposo, que viene de datos de salud fuera de alcance, ver D15). | Respuesta del usuario |
| D14 | Gestor de entorno: **uv** (como `../Garmin/`), con `pyproject.toml` + `uv.lock` y `.python-version` = 3.12. | `../Garmin/` ya usa uv |
| D15 | **Alcance: solo actividades de running.** Quedan fuera ciclismo, fuerza, `other` y **todos los datos de salud/bienestar** (sueño, HRV, body battery, estrés, SpO2, pasos, peso, FC reposo, resumen diario, perfil). No se ingestan ni se modelan. Bronze de la lista de actividades conserva todos los tipos (crudo, inmutable), pero **silver y todo lo posterior solo contienen running**; las demás se cuentan en el reporte como `out_of_scope`. | Respuesta del usuario; foco y simplicidad |
| D16 | **Licencia MIT.** | Respuesta del usuario; repo público como portafolio |
| D17 | **CLI con `argparse`** (sin dependencias extra, subcomandos con `add_subparsers`). | Respuesta del usuario |
| D18 | **Conservar lat/lon de inicio en Silver local**, no mostrar en gold/UI por defecto. | Confirmado por el usuario al cerrar la etapa 2; datos personales ignorados por git |
| D19 | **Incluir `treadmill_running`** en Silver como running, con `has_gps = false`. | Confirmado por el usuario al cerrar la etapa 2 |
| D20 | **Un entreno desplazado ±1 día se registra con `plan confirm`** como confirmación manual local ligada al `plan_hash`; no se infiere por fecha ni se sube la confianza de los laps. | Decisión al cerrar la etapa 5; evita falsos positivos |
| D21 | **Etapa 7 antes que etapa 6.** El dashboard solo depende de Gold/Plan vs real; Dagster no aporta contenido y la decisión de runtime sigue abierta. | Valor visible antes, sin tocar la ejecución |
| D22 | **Alertas iniciales a `lake/alerts.log`**, sin Telegram/e-mail ni notificación macOS. | El usuario eligió log local; notificación externa se pospone |

Pendientes de decidir (marcar aquí al resolver):

- [ ] Nube en etapa 8 (AWS/GCP/MotherDuck) o quedarse local; la opción D (portafolio) es la prioritaria.
- [ ] Prioridad analítica si hay que recortar: plan vs real, carga/lesión o predicción de tiempos (propuesta: plan vs real, por ser el diferenciador y por D12).
- [x] FIT real de intervalos: 34 de 35 laps con `wkt_step_index`; incluye mensaje `workout`; API `get_activity_workouts` devuelve pasos/nombre **sin campo `workoutId`**. El vínculo de IDs queda por investigar en etapa 5. Una carrera sin workout tiene el campo pero con todos los valores nulos.
- [x] ¿Qué `activityType.typeKey` cuentan como running? `running`, `trail_running`, `treadmill_running`, `track_running` (configurable en `RUNNING_TYPE_KEYS`); cinta con `has_gps = false` (D19). Backfill real: solo `running` (38); otros tipos previstos quedan configurados para cuando aparezcan.

## Hechos verificados sobre los datos (a 2026-10-21)

Fuente: `../Garmin/data/2026-10-21/*.json`, descargados con la Personal API.

- **Actividades:** 20 registros entre 2026-09-12 y 2026-10-21. Tipos: 16 `running`,
  3 `other`, 1 `cycling`. El límite fue `--activity-limit 20`; la ventana objetivo es
  2026-08-17 en adelante, así que faltan ~4 semanas por recuperar.
- **Estado local de `../Garmin/data/` (2026-10-25):** estaba vacío; ya no estaban los exports de
  ejemplo ni `uploads.json`. Los hechos de esta sección se midieron antes de eso.
  Para ETL_Running el backfill desde la API reconstruye todo; el manifiesto de subidas
  (workoutId ↔ fecha) reapareció después y se usa desde etapa 5; no se versiona.
- **Campos útiles por actividad:** `activityId`, `startTimeLocal/GMT`, `distance` (m),
  `duration`, `movingDuration`, `elapsedDuration`, `averageSpeed`, `maxSpeed` (m/s),
  `averageHR`, `maxHR`, `averageRunningCadenceInStepsPerMinute`, `avgStrideLength`,
  `elevationGain/Loss`, `calories`, `lapCount`, `splitSummaries`, `manualActivity`,
  `startLatitude/Longitude`, `moderateIntensityMinutes`, `vigorousIntensityMinutes`.
- **Datos personales en el payload:** `ownerFullName`, `ownerDisplayName`, URLs de
  imagen de perfil, coordenadas. Eliminar/anonimizar en fixtures.
- **No incluye** series por segundo ni archivo FIT: eso exige descarga por actividad
  (`gc-personal activity-download <id>`), objetivo de la etapa 3.
- **Datos de salud (sueño, HRV, body battery, resumen diario, etc.):** existen en el
  export original pero están **fuera de alcance** (D15). No se ingestan.
- **Actividades manuales** existen (`manualActivity`): sin GPS/FC/FIT; marcar y
  excluir de métricas de ritmo/FC. Regla general: ausencia → `NULL`, nunca 0.
- **Actividades no running** (`cycling`, `other`): fuera de alcance (D15). Sirven como
  casos de prueba del filtro, no como datos del modelo.

## Restricciones técnicas conocidas

- Personal API: solo lectura y solo datos propios. Token de 24 h sin refresh token
  (el SDK lo renueva). La API key caduca (30/90/180 días o 1 año); renovarla en
  `https://connect.garmin.com/app/settings/personalApiToken`.
- Escritura (workouts/actividades) requiere `garminconnect` con usuario/contraseña
  y MFA; vive en `../Garmin/`, no aquí.
- `garmin_personal_api` está instalado como paquete en el venv de `../Garmin/`.
  Aquí se declara como dependencia propia en `pyproject.toml`.

## Plan de entrenamiento (contexto para la etapa 5)

- Semana 2026-10-19 a 2026-10-25. Solo running se convierte en workout; fuerza se ignora.
- Esquema intermedio en `../Garmin/workouts/semana_2026-10-19.json`: sesiones con
  bloques `warmup | jog | reps | continuous`, ritmos en s/km (rango), pausas por
  tiempo o distancia, `warnings`.
- Zonas Garmin son metadato; el objetivo del reloj es el ritmo.
- Subidas registradas en `../Garmin/data/uploads.json` (hash + `workoutId` + fecha);
  volvió a estar disponible en la etapa 5 (4 workouts por fecha); se consulta
  solo localmente y no se versiona. Los uploads existentes son de la semana del
  2026-10-26, para la que aún no hay carreras correspondientes.
- Flujo real del usuario (D12): crear con el script → programar → enviar al reloj →
  correr el workout → la actividad queda con laps por paso. Esto permite enlazar
  plan y ejecución con alta confianza.
- Ruta actual del PDF: `../Garmin/pdfs/CÉSAR 2026.pdf`. `../Garmin/` ahora usa
  `uv` (`pyproject.toml`, `uv.lock`, `.python-version` = 3.14).

## Hallazgos y deuda técnica

- **dbt-duckdb** (etapa 4, D3) añadido a dependencias del proyecto; el paquete
  `dbt_utils` v1.3.3 se fija en `dbt/packages.yml` y `dbt/package-lock.yml`.
  `make dbt-build` instala el paquete y ejecuta `dbt build` con Silver local;
  tests de integración usan un lake temporal sintético en lugar de datos reales.
- **Dependencia `pytz` (etapa 2):** DuckDB la requiere para ejecutar operaciones de
  zona horaria sobre `start_utc` leído de Parquet; se añadió a `pyproject.toml`
  y `uv.lock`. Sin ella falla `date_trunc('week', start_utc)`.
- **Instalación de la librería de Garmin:** `garmin-connect-personal-api-python` está en
  PyPI (v1.0.0), no hace falta instalarla desde otra fuente; entra como dependencia normal.
- **Python 3.12 vía uv:** uv lo descarga solo; `.python-version` = 3.12. El shell del
  usuario tiene `VIRTUAL_ENV` apuntando a otro proyecto, lo que produce un aviso inofensivo
  de uv; se evita con `unset VIRTUAL_ENV` o `uv run --active`.
- **Licencia:** MIT con titular `cbr23` (editar `LICENSE` si se prefiere el nombre real).
- **Comprobación de privacidad:** buscar *valores* (`"ownerFullName": "`), no nombres de
  clave: estos aparecen legítimamente en el anonimizador y como `null` en fixtures.
- **Repo git:** `main`, commit inicial `c23d5ad`, publicado en GitHub con CI en verde.
- **Plan vs real (etapa 5):** 4 confirmaciones manuales locales para la semana
  2026-10-19; dos sesiones se corrieron +1 día y el informe lo muestra. El FIT
  agrupa repeticiones bajo el mismo `wkt_step_index`, por lo que el ritmo se mide
  por tramo contiguo (`workout_step_group`, confianza media): 44/44 bloques
  verificables y 18 cumplidos (40,9 %). La API devuelve la definición del workout
  ejecutado (pasos/objetivos) pero sin `workoutId`; ingerirla permitiría separar
  repeticiones individuales.
- **Deuda de tolerancia:** el JSON del plan usa un ritmo puntual (5:30) y el
  workout del reloj a veces un rango (5:20–5:40). Se mantiene ±5 s/km; decidir si
  se amplía a ±10 s/km para no marcar como fallo un bloque dentro del rango Garmin.

## Registro de cambios

| Fecha | Cambio |
| --- | --- |
| 2026-10-24 | Definición inicial: CLAUDE.md, MEMORY.md, docs y planes por etapa. |
| 2026-10-25 | Respuestas del usuario: historial desde 2026-08-17 (D10), uso personal + portafolio (D11), flujo con workout en el reloj (D12), sin FCmax/FC reposo fijas (D13), uv (D14). Planes y docs ajustados. |
| 2026-10-25 | Alcance reducido a **solo running** (D15): se eliminan datasets de salud, `fct_recovery_daily` y TRIMP. Licencia MIT (D16). CLI con argparse (D17). Planes y docs ajustados. |
| 2026-10-25 | Etapa 0 implementada: estructura, uv + Python 3.12, config/logging/CLI/anonimizador, fixture sintético, Makefile, CI. 30 tests y lint en verde. Pendiente: ejecutar CI en GitHub. |
| 2026-10-26 | Etapa 0 HECHA: publicado en GitHub, CI en verde. Etapa 1 EN CURSO. |
| 2026-10-26 | Etapa 1 implementada con cliente falso: `ingest/{garmin_client,extractors,cursor,pipeline}.py`, `bronze/{writer,report}.py`, CLI `ingest`/`backfill`/`bronze report`/`bronze show`; el cursor solo avanza con ventanas contiguas. 64 tests y lint en verde. Pendiente: backfill real y desglose por `typeKey`. `weekly_plan` queda en etapa 5. |
| 2026-10-26 | Logs rediseñados: formato texto estilo Airflow por defecto (`--log-format json` opcional), mensajes explícitos por paso en cliente/extractor/pipeline. 66 tests. |
| 2026-10-26 | Etapa 2 EN CURSO: parser Garmin, contrato Pandera, deduplicación/versiones, Parquet silver y cuarentena, CLI `silver build/report`. Build local: 43 bronze = 38 running + 0 cuarentena + 5 fuera de alcance; segundo build sin cambios. DuckDB necesita `pytz` para consulta semanal sobre `start_utc`. Datos reales solo en `lake/` ignorado por git. |
| 2026-10-26 | Los Parquet de Silver pasan a escribirse sin compresión por compatibilidad con visores VS Code que no soportan ZSTD; fingerprint de construcción incluye códec para regenerar los archivos antiguos. |
| 2026-10-26 | Etapa 2 HECHA: el usuario confirma conservar coordenadas en Silver local (D18) e incluir cinta sin GPS (D19). PR de Silver validado con CI y 77 tests. |
| 2026-10-26 | Etapa 3: 38 FIT ZIP descargados solo a lake; 587 laps, 20 610 records, 0 excepciones de distancia. FIT con workout: 34/35 laps tienen wkt_step_index, API asocia workout sin exponer workoutId. Parser, descarga, gráfica HTML y fixture FIT sintético implementados. |
| 2026-10-26 | PR #3 FIT integrado; etapa 4 Gold EN CURSO: dbt-duckdb + dbt_utils, 6 marts, 3 vistas staging, 34 pruebas dbt, 44/44 PASS y 84 tests Python incluyendo lake sintético. 38 carreras, 587 laps; ACWR y km cotejados con Silver. Pendiente comparación de 3 ritmos con UI Garmin (±2 s/km). |
| 2026-10-26 | Etapa 4 HECHA: el usuario confirmó en Garmin Connect coincidencia exacta de ritmo medio de 3 carreras (23/10: 6:51, 24/10: 6:03, 25/10: 8:46 min/km). |
| 2026-10-26 | PR #4 Gold integrado (CI verde). Etapa 5 HECHA: 2 JSON semanales a bronze, 8 sesiones/160 pasos silver, 4 uploads con workoutId locales; 4 carreras confirmadas manualmente (dos con +1 día). Respaldo por tramos del FIT: 44/44 bloques verificables y 18 cumplidos (40,9 %); 83/83 recursos dbt y 90 tests Python. Semana 26: cuatro `upcoming`. Etapa 1 HECHA al completar weekly_plan. |
| 2026-10-26 | D21: se adelanta la etapa 7 (dashboard) a la 6 (Dagster). D22: alertas a `lake/alerts.log`. Implementados Streamlit (5 páginas), consultas solo Gold, warehouse demo sintético (`lake_demo/`), reglas puras + `alerts run`, `make app/demo/alerts`, docs `DASHBOARD.md`. 110 tests, lint verde y las 5 páginas cargan con `AppTest` en modo demo. |
