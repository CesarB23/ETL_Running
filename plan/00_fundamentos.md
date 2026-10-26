# Etapa 0 — Fundamentos

**Estado:** EN CURSO (implementación completa; falta solo verificar CI en GitHub) · **Depende de:** nada

## Objetivo
Dejar un repo reproducible, con estructura, herramientas de calidad y CI, antes de
escribir lógica de datos.

## Resultado visible
En una máquina limpia: `make setup && make test && make lint` termina en verde y
`python -m etl_running --help` muestra la CLI.

## Alcance
**Dentro:** estructura, `pyproject.toml`, entorno 3.12, config, logging, Makefile,
pytest/ruff, `.gitignore`, `.env.example`, CI, fixture sintético base.
**Fuera:** cualquier ingesta o transformación.

## Entregables
- `pyproject.toml` gestionado con **uv** (`uv.lock` versionado, `.python-version` = 3.12) con deps núcleo: `garmin-connect-personal-api-python`, `duckdb`, `polars`, `pyarrow`, `pydantic`, `pandera`, `fitdecode`; dev: `pytest`, `ruff`.
- `.gitignore` (incluye `lake/`, `.env`, `.venv/`, `*.duckdb`).
- `.env.example` con `GARMIN_PERSONAL_API_KEY=`, rutas del lake y `START_DATE=2026-08-17`.
- `README.md` raíz orientado a portafolio (problema, arquitectura, cómo correr la demo); se completa en la etapa 7–8.
- `LICENSE` (**MIT**, D16) y `SECURITY.md` breve sobre datos personales.
- `src/etl_running/{common,ingest,bronze,silver,gold}/__init__.py`.
- `common/config.py` (carga de `.env` y rutas), `common/logging.py` (JSON, sin secretos).
- `Makefile` con `setup`, `test`, `lint`, `fmt`, `clean`.
- `.github/workflows/ci.yml`: ruff + pytest sobre 3.12.
- `tests/fixtures/` con un `actividades` **sintético** que imita la forma real.
- `tests/unit/test_smoke.py` (import del paquete y carga de config).

## Tareas
- [x] Crear el entorno con `uv sync` (Python 3.12) y verificar que instala todas las dependencias (¿resuelve `fitdecode`/`duckdb` sin conflictos?).
- [x] Redactar `pyproject.toml` y fijar versiones mínimas; commitear `uv.lock` (generado y versionado en el índice; el commit lo hace el usuario).
- [x] `common/config.py` expone `START_DATE` (2026-08-17) y valida que ninguna fecha pedida sea anterior.
- [x] Implementar config y logging con redacción de secretos.
- [x] CLI mínima con **argparse** y subcomandos (`--help`, `version`, `config`); la estructura permite añadir `ingest`, `backfill`, etc. sin dependencias nuevas (D17).
- [x] `common/config.py` expone también `RUNNING_TYPE_KEYS` (por defecto `running, trail_running, treadmill_running, track_running`).
- [x] Generar el fixture sintético **desde la forma documentada en MEMORY.md** (los exports reales de `../Garmin/data/` ya no están en disco): sin nombres, sin URLs, GPS ficticio.
- [x] Script de **anonimización** reutilizable (`scripts/anonymize.py`) con test.
- [ ] Configurar CI y comprobar que pasa (workflow escrito; requiere push a GitHub para verlo correr).

## Criterios de aceptación
```bash
uv run python --version                 # 3.12.x
make setup                              # sin errores (uv sync)
make test                               # todos verdes
make lint                               # sin hallazgos
python -m etl_running --help            # muestra la CLI
# Sin valores reales: los nombres de clave (ownerFullName…) aparecen legítimamente en el
# anonimizador y como null en los fixtures, así que se buscan VALORES, no claves.
git grep -nE '"owner(FullName|DisplayName|ProfileImageUrl[A-Za-z]*)": "' -- tests/fixtures      # sin resultados
git grep -nE 'GARMIN_PERSONAL_API_KEY=[^[:space:]`]' -- . ':!*.example' ':!plan' ':!docs' ':!MEMORY.md' ':!CLAUDE.md'   # sin resultados
git check-ignore lake .env              # ambos ignorados
```
- El workflow de CI pasa en una ejecución limpia.
- Ningún fixture contiene nombre real, URL de perfil ni coordenadas reales (test que lo comprueba).

## Datos de prueba
Fixture sintético de 5 actividades: running, running manual, running sin FC, ciclismo y `other`. Las dos últimas existen solo para probar el filtro de alcance (D15).

## Riesgos
- Dependencias sin wheel para 3.12/ARM → documentar workaround.
- `garmin-connect-personal-api-python` solo instalable desde su fuente actual → anotar en MEMORY.md cómo se instala.

## Evidencia
Ejecutado el 2026-10-25 en macOS (arm64):

| Criterio | Resultado |
| --- | --- |
| `uv run python --version` | `Python 3.12.13` |
| `make setup` | OK; 27 paquetes sin conflictos (duckdb 2.0.0, polars 2.1.0, pyarrow 26.0.0, pandera 0.35.0, fitdecode 0.11.0, garmin-connect-personal-api-python 1.0.0) |
| `make test` | `30 passed` (config, logging/redacción, CLI, anonimizador, fixtures) |
| `make lint` | `All checks passed!` + `36 files already formatted` |
| `python -m etl_running --help` / `version` | Muestra subcomandos `version` y `config`; `etl_running 0.1.0` |
| `git check-ignore lake .env` | Ambos ignorados |
| grep de valores reales en fixtures / API key con valor | Sin resultados |
| `uv sync --locked` | OK (el `uv.lock` es consistente; es lo que usa CI) |
| Test de PII en fixtures | Pasa (`test_fixtures_contain_no_personal_data`) |

**Pendiente:** ver el workflow `.github/workflows/ci.yml` correr en verde en GitHub
(no hay remoto configurado todavía).

Problemas encontrados y corregidos durante la etapa: el anonimizador no limpiaba
correos en textos libres y la redacción de `Authorization: Bearer …` se duplicaba;
ambos los detectaron los tests.

## Preguntas abiertas
- Resueltas: licencia MIT (D16) y CLI con argparse (D17). Nada pendiente en esta etapa.
