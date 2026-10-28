"""Job de assets para el pipeline diario."""

from __future__ import annotations

from dagster import AssetSelection, define_asset_job

# Assets + checks dbt/calidad. Las fuentes externas no se materializan.
PIPELINE_SELECTION = AssetSelection.all() | AssetSelection.all_asset_checks()

daily_pipeline = define_asset_job(
    name="daily_pipeline",
    selection=PIPELINE_SELECTION,
    description=(
        "Pipeline completo. El schedule y los backfills pasan la partición diaria; "
        "`dagster job execute -j daily_pipeline` sin partición usa el día actual."
    ),
    tags={"pipeline": "daily", "runtime": "local"},
)
