{% macro pace_min_km(speed_mps) -%}
    case when {{ speed_mps }} > 0 then 1000.0 / {{ speed_mps }} / 60.0 end
{%- endmacro %}
