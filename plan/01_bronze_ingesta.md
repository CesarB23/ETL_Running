# Etapa 1 — Bronze incremental + backfill

**Estado:** EN CURSO · **Depende de:** etapa 0

## Objetivo
Ingestar la lista de actividades de Garmin (todos los tipos, crudo) a bronze de forma
incremental, idempotente y trazable, y recuperar el historial desde 2026-08-17.

## Resultado visible
`etl_running backfill` carga todo desde **2026-08-17** hasta hoy, `etl_running ingest --since last` descarga solo lo nuevo, y
`etl_running bronze report` imprime una tabla con filas, rango de fechas, frescura y
errores por dataset. Al terminar se conoce el **número exacto de actividades** en la ventana, el desglose por `typeKey` y que la primera cae el 17/08 o después.

## Alcance
**Dentro:** extractor de la lista de actividades (`garmin/activities_list`) y carga del plan semanal (`plan/weekly_plan`), escritura
bronze con manifiesto, modo incremental con lookback, backfill reanudable,
reintentos y manejo de token, informe. CLI con `argparse` (D17).
**Fuera:** FIT (etapa 3), tipado/limpieza/filtro de running (etapa 2) y **cualquier dato de salud** (D15).

## Entregables
- `ingest/garmin_client.py`: autenticación, reintentos con backoff, límite de ritmo.
- `ingest/extractors.py`: extractor paginado de actividades con firma `(client, since, until) -> payload`.
- `bronze/writer.py`: escribe `lake/bronze/<fuente>/<dataset>/dt=…/<run_id>.json` y
  registra en `_manifest.parquet`; **nunca sobrescribe**.
- `ingest/cursor.py`: estado por dataset (último `dt` completo) en `lake/_state/cursor.json`.
- CLI (`argparse`): `ingest [--since last|YYYY-MM-DD] [--until] [--lookback N]`,
  `backfill [--from] [--to]`, `bronze report`.
- Documentación de la política de reintentos y de errores parciales.

## Tareas
- [x] Portar la lógica de `../Garmin/garmin_export.py` (copiar, no importar), quedándonos solo con `search_activities`.
- [x] Diseñar `run_id` (timestamp + corto aleatorio) y `sha256` del payload.
- [x] Escritura atómica (archivo temporal + rename) y comprobación de duplicado por hash (no reescribe si el hash no cambió).
- [x] Paginación de `search_activities` desde la más reciente hacia atrás hasta cruzar `START_DATE`; descartar las anteriores.
- [x] Particionar cada actividad por la fecha local de inicio (`dt`).
- [x] Manejo de 401 (refrescar token una vez) y 429/5xx (backoff exponencial); ventana sin actividades se registra como payload vacío (es un hecho).
- [x] Cursor reanudable: si el backfill se interrumpe, continúa donde quedó.
- [x] Comando `bronze report` con conteo por `typeKey` (para decidir `RUNNING_TYPE_KEYS`).
- [x] Tests con cliente simulado (sin red): reintentos, idempotencia, cursor, hash repetido.

## Criterios de aceptación
```bash
make test                                              # incluye tests de ingesta con cliente falso
etl_running backfill                                   # por defecto: START_DATE=2026-08-17 hasta hoy; reanudable con Ctrl+C
etl_running backfill --from 2026-08-01                 # debe RECHAZARSE (anterior a START_DATE)
etl_running ingest --since last                        # 2.ª ejecución: 0 archivos nuevos
etl_running bronze report                              # tabla por dataset
```
- `min(dt)` en bronze es ≥ 2026-08-17 y la lista de actividades se pagina hasta cruzar esa fecha (se descartan las anteriores).
- Dos ejecuciones consecutivas sin cambios en origen no crean archivos nuevos ni modifican el manifiesto (salvo registro de ejecución).
- Ningún archivo bronze se modifica tras escribirse (test: checksum antes/después).
- Interrumpir el backfill a mitad y relanzar produce el mismo conjunto final que una ejecución continua.
- Reconciliación: nº de actividades en bronze = nº devuelto por el API paginado.
- Los logs no contienen token, key ni nombre real (test de redacción).

## Datos de prueba
- Cliente falso que devuelve fixtures sintéticos y simula 401/429/500.
- Real: ejecución manual con tu cuenta; no se versiona.

## Riesgos
- Límites de la API no documentados → empezar con concurrencia 1 y medir.
- La paginación de `search_activities` puede devolver duplicados entre páginas → deduplicar por `activityId` antes de escribir.
- Historial con campos distintos → bronze crudo lo absorbe; silver lo normaliza.

## Evidencia
Implementación y tests con cliente falso: 64 tests y lint en verde (2026-10-26). Incluye `bronze show --last-days N` (solo lectura)
y un cursor que solo avanza con ventanas contiguas (una carga parcial no oculta días).

Ejecución real observada 2026-10-26: `backfill` desde 2026-08-17 hasta 2026-10-26
descargó **43 actividades**; ejecución incremental siguiente: **0 archivos nuevos**.
`bronze report`: 43 actividades, `running=38`, `cycling=2`, `other=2`,
`walking=1`; particiones `dt=2026-08-17` a `dt=2026-10-26` (incluye días
vacíos). Silver confirmó primera actividad el 2026-08-17 y 38 running.

Nota de alcance: la carga de `plan/weekly_plan` no se implementó aquí; vive en la
etapa 5 (`ingest/plan_loader.py`), donde ya estaba entregable.

## Preguntas abiertas
- Resueltas: ventana desde 2026-08-17 (D10), CLI argparse (D17), solo running (D15).
- Pendiente: confirmar con el desglose por `typeKey` qué tipos entran en `RUNNING_TYPE_KEYS`.
