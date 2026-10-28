.PHONY: setup web-setup test lint fmt clean dbt-build dbt-manifest dbt-docs app app-dev demo alerts dev run-daily launchd-install

setup:
	uv sync
	npm --prefix web ci

web-setup:
	npm --prefix web ci

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	rm -rf .pytest_cache .ruff_cache build dist
	find . -type d -name __pycache__ -not -path "./.venv/*" -prune -exec rm -rf {} +

# Gold (necesita los tres Parquet silver locales; nunca se versionan).
dbt-build:
	uv run dbt deps --project-dir dbt --profiles-dir dbt
	uv run dbt build --project-dir dbt --profiles-dir dbt

dbt-manifest:
	uv run dbt deps --project-dir dbt --profiles-dir dbt
	uv run dbt parse --project-dir dbt --profiles-dir dbt

dbt-docs:
	uv run dbt docs generate --project-dir dbt --profiles-dir dbt
	uv run dbt docs serve --project-dir dbt --profiles-dir dbt

# Interfaz React/TypeScript compilada servida localmente sobre Gold.
app:
	npm --prefix web run build
	uv run python -m app.api

# Desarrollo: Vite con recarga rápida y API Python en paralelo.
app-dev:
	./scripts/run_web_dev.sh

# Warehouse sintético para demo/capturas; nunca usa datos reales.
demo:
	uv run python scripts/make_demo_warehouse.py

# Evalúa reglas y escribe lake/alerts.log.
alerts:
	uv run python -m etl_running alerts run

# Dagster UI local: grafo, schedule, sensor, backfills y checks.
dev:
	mkdir -p dagster_home
	DAGSTER_HOME=$(CURDIR)/dagster_home uv run dagster dev -m orchestration.definitions -p 3000

# Ejecución manual completa. El schedule usa la misma job con partición diaria.
run-daily:
	mkdir -p dagster_home
	DAGSTER_HOME=$(CURDIR)/dagster_home uv run dagster job execute -m orchestration.definitions -j daily_pipeline

# Instala el LaunchAgent del Mac (ver docs/ORCHESTRATION.md).
launchd-install:
	./scripts/install_launchd.sh
