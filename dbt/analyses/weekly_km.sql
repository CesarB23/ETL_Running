-- Para DuckDB fuera de dbt: consulta sobre tablas materializadas en lake/warehouse.duckdb.
select week_start, run_count, distance_km
from gold.fct_weekly_summary
order by week_start;
