.PHONY: setup test lint fmt clean dbt-build dbt-docs app demo alerts

setup:
	uv sync

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

dbt-docs:
	uv run dbt docs generate --project-dir dbt --profiles-dir dbt
	uv run dbt docs serve --project-dir dbt --profiles-dir dbt

# Dashboard local de solo lectura sobre Gold.
app:
	uv run streamlit run app/main.py

# Warehouse sintético para demo/capturas; nunca usa datos reales.
demo:
	uv run python scripts/make_demo_warehouse.py

# Evalúa reglas y escribe lake/alerts.log.
alerts:
	uv run python -m etl_running alerts run
