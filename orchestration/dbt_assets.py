"""Integración del proyecto dbt como assets de Dagster."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dagster import AssetExecutionContext, RetryPolicy
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    dbt_assets,
)

from .resources import DBT_PROJECT, dbt_manifest_path


class _ProjectTranslator(DagsterDbtTranslator):
    """Agrupa modelos por carpeta para que el grafo sea legible en la UI."""

    def __init__(self) -> None:
        super().__init__(
            settings=DagsterDbtTranslatorSettings(
                enable_asset_checks=True,
                enable_source_tests_as_checks=True,
            )
        )

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        path = str(dbt_resource_props.get("original_file_path") or "")
        if path.startswith("models/staging"):
            return "staging"
        if path.startswith("models/intermediate"):
            return "intermediate"
        if path.startswith("models/marts"):
            return "marts"
        if dbt_resource_props.get("resource_type") == "source":
            return "sources"
        return "dbt"


# En `dagster dev` se regenera el manifest para recoger cambios en los modelos.
# Fuera de dev, el manifest se genera si falta (checkout limpio o `job execute`).
DBT_PROJECT.prepare_if_dev()
_MANIFEST: Path = dbt_manifest_path()


@dbt_assets(
    manifest=_MANIFEST,
    project=DBT_PROJECT,
    name="dbt_gold",
    dagster_dbt_translator=_ProjectTranslator(),
    retry_policy=RetryPolicy(max_retries=1, delay=30),
    op_tags={"dagster/max_runtime": "1800"},
)
def dbt_gold(context: AssetExecutionContext, dbt: DbtCliResource):
    """`dbt build` materializa staging/intermediate/marts y ejecuta sus tests.

    dagster-dbt convierte los tests dbt en asset checks; así aparecen en la UI
    junto a frescura, volumen y reconciliación.
    """
    yield from dbt.cli(["build"], context=context).stream()
