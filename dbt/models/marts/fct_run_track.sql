-- Coordenadas GPS para mapas del dashboard; se descartan puntos sin posición.
select activity_id, ts_utc, distance_m, lat, lon, speed_mps, altitude_m, heart_rate, timer_running
from {{ ref('stg_activity_records') }}
where lat is not null and lon is not null
  and lat between -90 and 90 and lon between -180 and 180
