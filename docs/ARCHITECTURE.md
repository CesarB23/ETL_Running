# Arquitectura

## Flujo

```
┌────────────────────┐
│ Garmin Personal API│──┐
└────────────────────┘  │   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────────────┐
┌────────────────────┐  ├──►│  INGESTA │──►│  BRONZE  │──►│  SILVER  │──►│     GOLD      │──► Streamlit
│ FIT por actividad  │──┤   │ (Python) │   │ crudo,   │   │ tipado,  │   │ marts dbt     │──► Alertas
└────────────────────┘  │   └──────────┘   │ inmutable│   │ validado │   │ DuckDB        │
┌────────────────────┐  │                  └──────────┘   └──────────┘   └───────────────┘
│ Plan semanal (JSON │──┘                        ▲                                ▲
│ parseado del PDF)  │                           └───── Dagster (etapa 6) ────────┘
└────────────────────┘
```

## Capas

### Ingesta (`src/etl_running/ingest/`)
- Extractores por fuente. Devuelven payloads; **no escriben a disco**.
- Incrementales con *lookback* configurable (por defecto 7 días) y modo `backfill`.
- Reintentos con backoff, respeto de límites de la API, renovación de token.
- Cada ejecución produce un registro en el manifiesto de bronze.

### Bronze (`lake/bronze/`)
- Ruta: `lake/bronze/<fuente>/<dataset>/dt=YYYY-MM-DD/<nombre>.json|fit`
  (`dt` = fecha lógica del dato, no de la descarga).
- Cada archivo lleva sidecar o entrada de manifiesto con: `ingested_at`,
  `source`, `request_params`, `sha256`, `parser_version`.
- Inmutable. Si cambia el dato en origen, se añade una nueva versión (`run_id`) y
  silver toma la última.

- **Alcance:** solo running (D15). El filtro por tipo se aplica al pasar de bronze a
  silver, no en la ingesta, para conservar el crudo completo.
- Silver (más abajo) hereda ese filtro.

### Silver (`lake/silver/*.parquet`)
- Una tabla por entidad, tipada y validada con Pandera.
- Claves naturales y upsert; deduplicación por `activity_id` o `(date, metric)`.
- Unidades SI (m, s, m/s), timestamps UTC + `tz_local`.
- Registros inválidos van a `lake/silver/_quarantine/` con el motivo.

### Gold (`dbt/models/marts/` → `lake/warehouse.duckdb`)
- Modelos dimensionales y de hechos, con tests dbt (`unique`, `not_null`,
  `relationships`, `accepted_values` y tests singulares de negocio).
- Métricas derivadas: eficiencia aeróbica, drift cardíaco, carga (minutos de intensidad, ACWR),
  cumplimiento del plan.

### Consumo
- Streamlit lee de DuckDB en modo solo lectura.
- Alertas por reglas sobre gold (consola/archivo primero; notificación después).

## Orquestación (etapa 6)
- Dagster: un *asset* por tabla; los de bronze con partición diaria.
- Schedule diario + sensor que detecta nuevas actividades.
- Antes de eso, `Makefile` + CLI cubren la ejecución manual.

## Calidad y observabilidad
- **Contratos:** Pandera en silver; dbt tests en gold.
- **Frescura:** `max(ingested_at)` por dataset; alerta si supera umbral.
- **Volumen:** conteo por carga; avisa de caídas bruscas.
- **Reconciliación:** `count(*)` bronze vs silver por dataset en cada ejecución.
- **Logs:** estructurados (JSON), sin payloads ni credenciales.

## Seguridad
- Secretos solo en `.env` (permisos 600) y/o variables de entorno.
- `lake/`, `.env` y exports reales fuera de git.
- Fixtures sintéticos. Anonimizar GPS y nombres antes de compartir nada.

## Decisiones y riesgos

| Riesgo | Mitigación |
| --- | --- |
| Garmin cambia el esquema JSON | Bronze crudo + `parser_version` + contratos que fallan ruidosamente |
| API key caduca a mitad de proyecto | Chequeo de auth al inicio de cada ingesta con mensaje claro |
| Python 3.14 sin soporte en dbt/Dagster | Fijar 3.12 en `pyproject.toml` y `.python-version` |
| Historial real desconocido | Backfill paginado con checkpoint reanudable |
| Actividades manuales o sin FC/GPS (cinta) | `NULL` + flags `is_manual`/`has_gps`; métricas las excluyen |
| Zonas horarias / DST | Guardar UTC y `tz_local`; test con cambio de hora |
