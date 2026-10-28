# Dashboard y alertas

Aplicación local de **solo lectura** sobre `lake/warehouse.duckdb`. La interfaz
React/TypeScript obtiene exclusivamente datos Gold mediante la API local Python;
no recalcula entrenamientos. El recorrido se dibuja en el navegador sobre teselas
públicas de OpenStreetMap. El proveedor puede inferir la zona visible a partir de
las solicitudes de mapa; no recibe el archivo FIT ni los datos Gold.

## Arranque

```bash
make setup              # uv + dependencias npm
make dbt-build          # genera/actualiza Gold
make app                # interfaz en http://localhost:8000
make alerts             # evalúa reglas y escribe lake/alerts.log
```

Para desarrollo con HMR de Vite: `make app-dev` (http://localhost:5173). La API
queda en `127.0.0.1:8000`; en modo producción, Python sirve el bundle compilado.

Para el modo demo, sin datos personales:

```bash
make demo                       # crea lake_demo/warehouse.duckdb sintético
DEMO_MODE=1 make app            # React con datos deportivos sintéticos
```

`lake_demo/` y `lake/alerts.log` están ignorados por git. El modo demo es el único
origen admitido para capturas públicas.

## Páginas

| Página | Contenido | Fuente Gold |
| --- | --- | --- |
| **Actividades** | Recorrido GPS local, laps FIT, ritmos y comparación con el plan vinculado | `fct_runs`, `fct_run_track`, `fct_run_laps`, `fct_plan_sessions`, `fct_plan_vs_actual` |
| **Progreso** | Ritmo, eficiencia aeróbica y deriva cardíaca a lo largo del tiempo | `fct_runs` |
| **Carga** | Carga aguda/crónica, ACWR y fiabilidad del historial | `fct_training_load` |
| **Salud** | Frescura, volúmenes, claves, rechazos y alertas locales | `mart_data_quality`, `lake/alerts.log` |

La interfaz no usa analítica externa. El mapa sí solicita teselas públicas de
OpenStreetMap y muestra su atribución; cada solicitud revela la zona consultada.
La comparación del plan requiere el vínculo explícito entre sesión y actividad;
nunca se infiere solo por fecha.

### KPIs y lectura

- **ACWR** = carga aguda (7 días) / crónica (28 días). Solo se muestra cuando
  `is_reliable` es verdadero; las primeras 4 semanas de historial no lo son.
  Zona habitual 0,8–1,3; precaución 1,3–1,5; riesgo elevado > 1,5. **No es un
  diagnóstico médico.**
- **Cumplimiento** = bloques de ritmo cumplidos / bloques objetivo, contando solo
  sesiones cerradas con evidencia verificable. Los bloques `unverifiable` no se
  convierten en fallo.
- **Eficiencia aeróbica** = velocidad media (m/s) / FC media. Más alto es mejor,
  pero depende de condiciones y tipo de sesión.
- **Frescura** = antigüedad de `warehouse.duckdb`, no de la última carrera.

La tolerancia de plan es ±5 s/km (`pace_tolerance_s_km` en dbt). Un entrenamiento
desplazado ±1 día cuenta solo si se confirma con
`etl_running plan confirm --date ... --activity-id ...`; no se infiere por fecha.

## Alertas

`etl_running alerts run` evalúa reglas puras en `src/etl_running/alerts/rules.py`
y añade una línea por aviso a `lake/alerts.log`:

```text
2026-10-26T12:00:00Z | WARNING | acwr_high | ACWR 1.62 supera 1.5; ...
```

| Código | Regla | Umbral |
| --- | --- | --- |
| `acwr_high` | ACWR alto con ventana fiable | > 1,5 |
| `inactivity` | Días desde la última carrera | > 10 |
| `plan_compliance_low` | Cumplimiento de la última semana cerrada | < 50 % |
| `data_stale` | Antigüedad del warehouse | > 36 h |
| `api_key_expiring` | API key próxima a caducar | ≤ 14 días |
| `api_key_expired` | API key caducada | < 0 días |

Los umbrales viven como constantes en `rules.py`; cambiarlos exige test. Para la
caducidad de la API key hay que informar la fecha:

```bash
GARMIN_API_KEY_EXPIRES=2026-12-01
```

Si no hay avisos, el log deja una línea `INFO | no_alerts`. El schedule Dagster
diario también evalúa las alertas al final del pipeline; `make alerts` permite
ejecutarlas manualmente. La notificación es local; no se envían datos a Telegram
ni e-mail.

## Tests

```bash
make test
uv run pytest tests/unit/test_alerts.py tests/unit/test_dashboard.py -q
```

- Reglas: casos que disparan y no disparan, límites y orden estable.
- Runner: warehouse temporal, escritura del log y ausencia de warehouse.
- Consultas: warehouse demo sintético; se comprueba que todos los marts
  necesarios existen y devuelven datos.
- La UI React se compila con `npm --prefix web run build`; las consultas y API
  Python se prueban con warehouse sintético.

## Privacidad

- La API lee Gold y solo escucha en localhost.
- Las teselas OSM son externas; el proveedor puede inferir la zona que se visualiza.
- El resto del warehouse y los FIT no se envían a OpenStreetMap.
- El modo demo solo usa datos ficticios generados por
  `scripts/make_demo_warehouse.py` (semilla determinista).
- No se versionan `lake/`, `lake_demo/`, `*.duckdb`, FIT ni logs.

## Limitaciones actuales

- Dagster actualiza Gold según schedule cuando `make dev`/daemon está activo; sin
  orquestador, el dashboard refleja el último `make dbt-build` manual.
- La frescura puede marcar `data_stale` si no se reconstruye Gold en 36 h. Es
  información real, no un fallo de la app.
- No hay autenticación: está pensado para `localhost`.
- Los modelos predictivos quedan para la etapa 8.
