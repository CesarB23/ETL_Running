"""Asset final de alertas: evalúa Gold y escribe el log local."""

from dagster import AssetExecutionContext, AssetKey, MaterializeResult, asset

from etl_running.alerts.runner import run_alerts


@asset(
    key=AssetKey(["gold", "alerts"]),
    deps=[
        AssetKey(["fct_runs"]),
        AssetKey(["fct_training_load"]),
        AssetKey(["fct_weekly_summary"]),
    ],
    group_name="gold",
    description="Reglas de alerta sobre Gold; escribe lake/alerts.log (sin envíos externos).",
    op_tags={"dagster/max_runtime": "300"},
    required_resource_keys={"settings"},
)
def alerts(context: AssetExecutionContext) -> MaterializeResult:
    """No duplica reglas: llama al mismo motor puro que `etl_running alerts run`."""
    result = run_alerts(context.resources.settings)
    for alert in result.alerts:
        context.log.warning("%s: %s", alert.code, alert.message)
    return MaterializeResult(
        metadata={
            "alerts": len(result.alerts),
            "log_path": str(result.log_path),
        }
    )
