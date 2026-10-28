# CLAUDE.md — ETL_Running

Guía para agentes que trabajen en este repo. Léela entera antes de tocar nada,
y lee también `MEMORY.md` (estado vivo del proyecto) y el plan de la etapa activa
en `plan/`.

## Qué es este proyecto

Plataforma de datos personal (E2E) sobre mis **actividades de running** de Garmin
Connect. Cruza dos cosas: **plan** (lo prescrito) y **ejecución** (lo corrido), y de
ahí deriva progreso y carga. Todo lo que no sea running (otros deportes, datos de
salud como sueño/HRV/body battery) está **fuera de alcance**.

Arquitectura medallion, local-first:

```
Garmin API + PDF plan → ingesta (Python) → bronze (crudo) → silver (tipado)
                                         → gold (marts, dbt) → dashboard / alertas
```

Detalle en `docs/ARCHITECTURE.md` y `docs/DATA_MODEL.md`.

## Relación con `../Garmin/`

- `../Garmin/` es el proyecto previo: exporta JSON, planifica workouts, los sube y
  envía al reloj, y parsea el PDF del plan (`pdfs/`). **No se modifica desde aquí**
  salvo petición explícita.
- Flujo real: el entreno se crea con el script de `../Garmin/`, se envía al reloj y
  se corre con el workout activo. Eso deja laps por paso del plan en el FIT.
- `ETL_Running` es el lado **solo lectura / analítico**. Reutiliza ideas y
  código de `../Garmin/` **copiándolo** (no con imports cruzados entre carpetas).
- Escribir en Garmin (crear workouts/actividades) sigue viviendo en `../Garmin/`.

## Stack (decisiones cerradas, ver MEMORY.md para el porqué)

| Capa | Herramienta |
| --- | --- |
| Lenguaje | Python **3.12** (no 3.14: compatibilidad dbt/Dagster) |
| Entorno | **uv** (`pyproject.toml` + `uv.lock`), como `../Garmin/` |
| Almacenamiento | Parquet + JSON/FIT crudos en `lake/` |
| Motor analítico | DuckDB |
| Transformaciones | dbt-duckdb |
| Orquestación | Dagster (desde etapa 6) |
| Calidad | Pandera (silver) + dbt tests (gold) |
| Dashboard | React + TypeScript, API Python local (etapa 7) |
| Tests / lint | pytest, ruff |
| CLI | argparse (stdlib) |
| FIT | `fitdecode` |
| Licencia | MIT |

No añadas dependencias nuevas sin anotarlo en `MEMORY.md` (sección Decisiones).

## Estructura

```
ETL_Running/
├── CLAUDE.md  MEMORY.md  README.md
├── docs/            arquitectura y modelo de datos
├── plan/            un archivo por etapa (00..08) + roadmap
├── src/etl_running/
│   ├── ingest/      clientes y extractores (Garmin API, FIT, PDF plan)
│   ├── bronze/      escritura inmutable + manifiesto
│   ├── silver/      parsers, tipado, contratos Pandera
│   ├── gold/        utilidades de métricas en Python (si dbt no basta)
│   └── common/      config, logging, fechas/zonas horarias
├── dbt/             proyecto dbt (staging, marts, tests)
├── orchestration/   assets, schedules y sensores de Dagster
├── app/             API local de solo lectura sobre Gold
├── web/             interfaz React + TypeScript
├── tests/           unit/ integration/ fixtures/ (solo datos sintéticos)
├── lake/            (gitignored) bronze/ silver/ gold/ + warehouse.duckdb
└── Makefile         atajos: setup, ingest, test, dbt, run
```

Las carpetas se crean cuando su etapa las necesita, no antes.

## Reglas de trabajo

1. **Una etapa a la vez.** Trabaja solo en la etapa marcada `EN CURSO` en
   `MEMORY.md`. No adelantes tareas de etapas posteriores.
2. **Etapa cerrada = criterios de aceptación cumplidos con evidencia.** Cada plan
   en `plan/` lista comandos verificables. Ejecútalos y pega el resultado resumido
   en la sección "Evidencia" del plan antes de marcarla `HECHA`.
3. **Actualiza `MEMORY.md` al cerrar cada tarea relevante**: estado, decisiones,
   hallazgos sobre los datos, deuda técnica.
4. **Bronze es inmutable.** Nunca se edita ni se borra un archivo de bronze; todo lo
   derivable se reconstruye desde ahí. Silver y gold deben poder regenerarse con un
   solo comando.
5. **Idempotencia.** Re-ejecutar cualquier paso con los mismos inputs no cambia el
   resultado ni duplica filas (upsert por clave natural).
6. **No inventar datos.** Un valor ausente es `NULL`, nunca `0`. Un parseo dudoso se
   registra como warning o va a cuarentena; no se adivina.
7. **Tiempo y unidades.** Guardar timestamps en UTC más la zona local; velocidades
   en m/s y distancias en metros en silver; convertir a min/km y km solo en gold o UI.
8. **Tests primero cuando sea razonable**, y siempre antes de cerrar una etapa.
   Los fixtures contienen solo datos **sintéticos o anonimizados**.
9. **Ventana histórica fija: desde 2026-08-17** (`START_DATE` en config). Ningún
   extractor pide ni procesa fechas anteriores.
10. **Alcance: solo running (D15).** No ingestar ni modelar datos de salud ni otros
    deportes. Bronze guarda la lista de actividades cruda (todos los tipos); desde
    silver solo hay running (`RUNNING_TYPE_KEYS` en config).
11. **Sin parámetros fisiológicos (D13).** El usuario no fija FCmax ni FC de reposo.
    La carga usa los minutos de intensidad de Garmin; no se calcula TRIMP.
12. **El repo es presentable como portafolio** (MIT, D16). Cada etapa deja documentación y
    resultados reproducibles con datos sintéticos; el código y los docs no deben
    asumir que el lector tiene acceso a mi cuenta de Garmin.

## Seguridad y privacidad (no negociable)

- Nunca leer, imprimir, copiar ni commitear `.env`, tokens, API keys ni
  `~/.config/garmin/*`.
- `lake/`, `.env` y cualquier export real van en `.gitignore`.
- Los datos contienen GPS, salud y nombre real: no se pegan en issues, logs ni
  fixtures. Anonimizar (coordenadas desplazadas, `ownerFullName` y URLs de perfil
  eliminados) antes de crear fixtures.
- La API key de Garmin caduca; no hardcodear fechas de expiración en código.
- Los logs no deben incluir payloads completos ni credenciales.

## Convenciones de código

- Python 3.12, tipado con anotaciones, `from __future__ import annotations`.
- Formato y lint con `ruff` (`make lint`). Tests con `pytest` (`make test`).
- Nombres de tablas en inglés `snake_case`; prefijos `stg_`, `fct_`, `dim_`.
- Textos de usuario, docs y mensajes de CLI en español; identificadores en inglés.
- Comentarios solo donde el porqué no sea obvio.
- CLI con **`argparse`** y subcomandos (`add_subparsers`), sin dependencias extra (D17).
- Los módulos de ingesta no tocan disco directamente: usan `bronze/` para escribir.

## Comandos habituales (se completan conforme avanzan las etapas)

```bash
make setup      # uv sync (crea .venv con Python 3.12)
make test       # pytest
make lint       # ruff
make ingest     # ingesta incremental (desde etapa 1)
make dbt-build  # dbt run + test (desde etapa 4)
make dev        # dagster dev (desde etapa 6)
make app        # dashboard React/TypeScript (API Python local sobre Gold)
```

## Definición de "hecho" para cualquier tarea

- [ ] El código corre desde cero con `make setup` y el comando documentado.
- [ ] Tests nuevos pasan y los existentes siguen pasando.
- [ ] `ruff` sin errores.
- [ ] Re-ejecución idempotente comprobada.
- [ ] `MEMORY.md` y el plan de la etapa actualizados.
- [ ] Ningún dato real ni secreto en git.
