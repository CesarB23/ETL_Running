{% macro rolling_avg(column, days) -%}
    avg({{ column }}) over (
        order by activity_date
        rows between {{ days | int - 1 }} preceding and current row
    )
{%- endmacro %}
