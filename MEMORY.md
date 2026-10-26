# MEMORY.md — estado vivo de ETL_Running

Este archivo es la memoria del proyecto. Se actualiza al cerrar cada tarea.
Un agente nuevo debe leer esto después de `CLAUDE.md` y antes de empezar.

_Última actualización: 2026-10-25 (fase de definición; respuestas del usuario incorporadas, sin código aún)._

## Estado de las etapas

| # | Etapa | Estado | Plan |
| --- | --- | --- | --- |
| 0 | Fundamentos | EN CURSO (falta ver CI en GitHub) | `plan/00_fundamentos.md` |
| 1 | Bronze incremental + backfill | PENDIENTE | `plan/01_bronze_ingesta.md` |
| 2 | Silver (actividades running) | PENDIENTE | `plan/02_silver.md` |
| 3 | FIT → laps y records | PENDIENTE | `plan/03_fit.md` |
| 4 | Gold con dbt | PENDIENTE | `plan/04_gold_dbt.md` |
| 5 | Plan vs real | PENDIENTE | `plan/05_plan_vs_real.md` |
| 6 | Orquestación | PENDIENTE | `plan/06_orquestacion.md` |
| 7 | Dashboard y alertas | PENDIENTE | `plan/07_dashboard_alertas.md` |
| 8 | Extras (ML, nube, observabilidad) | PENDIENTE | `plan/08_extras.md` |

Estados: `PENDIENTE` · `EN CURSO` · `BLOQUEADA` · `HECHA`.
**Etapa activa:** 0 (Fundamentos).

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

Pendientes de decidir (marcar aquí al resolver):

- [ ] Nube en etapa 8 (AWS/GCP/MotherDuck) o quedarse local; la opción D (portafolio) es la prioritaria.
- [ ] Prioridad analítica si hay que recortar: plan vs real, carga/lesión o predicción de tiempos (propuesta: plan vs real, por ser el diferenciador y por D12).
- [ ] ¿Verificar con un FIT real que los laps traen `wkt_step_index` y si la actividad enlaza con el `workoutId`? (primera tarea de la etapa 3).
- [ ] ¿Qué `activityType.typeKey` cuentan como running? Propuesta inicial: `running`, `trail_running`, `treadmill_running`, `track_running` (configurable en `RUNNING_TYPE_KEYS`). La cinta no tiene GPS: se mantiene pero se marca `has_gps = false`. Confirmar con los tipos reales tras el backfill.

## Hechos verificados sobre los datos (a 2026-10-21)

Fuente: `../Garmin/data/2026-10-21/*.json`, descargados con la Personal API.

- **Actividades:** 20 registros entre 2026-09-12 y 2026-10-21. Tipos: 16 `running`,
  3 `other`, 1 `cycling`. El límite fue `--activity-limit 20`; la ventana objetivo es
  2026-08-17 en adelante, así que faltan ~4 semanas por recuperar.
- **Estado local de `../Garmin/data/` (2026-10-25):** vacío; ya no están los exports de
  ejemplo ni `uploads.json`. Los hechos de esta sección se midieron antes de eso.
  Para ETL_Running el backfill desde la API reconstruye todo; el manifiesto de subidas
  (workoutId ↔ fecha) hay que recuperarlo o regenerarlo (ver etapa 5).
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
  actualmente ese archivo no existe (ver arriba).
- Flujo real del usuario (D12): crear con el script → programar → enviar al reloj →
  correr el workout → la actividad queda con laps por paso. Esto permite enlazar
  plan y ejecución con alta confianza.
- Ruta actual del PDF: `../Garmin/pdfs/CÉSAR 2026.pdf`. `../Garmin/` ahora usa
  `uv` (`pyproject.toml`, `uv.lock`, `.python-version` = 3.14).

## Hallazgos y deuda técnica

- **Instalación de la librería de Garmin:** `garmin-connect-personal-api-python` está en
  PyPI (v1.0.0), no hace falta instalarla desde otra fuente; entra como dependencia normal.
- **Python 3.12 vía uv:** uv lo descarga solo; `.python-version` = 3.12. El shell del
  usuario tiene `VIRTUAL_ENV` apuntando a otro proyecto, lo que produce un aviso inofensivo
  de uv; se evita con `unset VIRTUAL_ENV` o `uv run --active`.
- **Licencia:** MIT con titular `cbr23` (editar `LICENSE` si se prefiere el nombre real).
- **Comprobación de privacidad:** buscar *valores* (`"ownerFullName": "`), no nombres de
  clave: estos aparecen legítimamente en el anonimizador y como `null` en fixtures.
- **Repo git:** inicializado en `ETL_Running/` con rama `main`; archivos en el índice, sin commits.
- **Deuda:** CI escrito pero sin verificar en GitHub (no hay remoto).

## Registro de cambios

| Fecha | Cambio |
| --- | --- |
| 2026-10-24 | Definición inicial: CLAUDE.md, MEMORY.md, docs y planes por etapa. |
| 2026-10-25 | Respuestas del usuario: historial desde 2026-08-17 (D10), uso personal + portafolio (D11), flujo con workout en el reloj (D12), sin FCmax/FC reposo fijas (D13), uv (D14). Planes y docs ajustados. |
| 2026-10-25 | Alcance reducido a **solo running** (D15): se eliminan datasets de salud, `fct_recovery_daily` y TRIMP. Licencia MIT (D16). CLI con argparse (D17). Planes y docs ajustados. |
| 2026-10-25 | Etapa 0 implementada: estructura, uv + Python 3.12, config/logging/CLI/anonimizador, fixture sintético, Makefile, CI. 30 tests y lint en verde. Pendiente: ejecutar CI en GitHub. |
