# Dashboard y alertas

Aplicación local de **solo lectura** sobre `lake/warehouse.duckdb`. La UI no
recalcula entrenamientos: muestra los marts de Gold ya construidos por dbt. Si un
KPI no está en Gold, no se inventa en la app.

## Arranque

```bash
make dbt-build          # genera/actualiza Gold
make app                # abre Streamlit en http://localhost:8501
make alerts             # evalúa reglas y escribe lake/alerts.log
```

Para el modo demo, sin datos personales:

```bash
make demo                       # crea lake_demo/warehouse.duckdb sintético
DEMO_MODE=1 make app            # Streamlit con banner de datos sintéticos
```

`lake_demo/` y `lake/alerts.log` están ignorados por git. El modo demo es el único
origen admitido para capturas públicas.

## Páginas

| Página | Contenido | Fuente Gold |
| --- | --- | --- |
| **Resumen** | Km y carreras de los últimos 7 días, tiempo, ACWR, cumplimiento y volumen semanal | `fct_runs`, `fct_training_load`, `fct_weekly_summary` |
| **Progreso** | Ritmo, eficiencia aeróbica y drift cardíaco en el tiempo | `fct_runs` |
| **Carga** | Carga aguda/crónica y ACWR con zonas | `fct_training_load` |
| **Plan vs real** | Cumplimiento semanal, sesiones y detalle por bloque | `fct_weekly_summary`, `fct_plan_sessions`, `fct_plan_vs_actual` |
| **Salud del pipeline** | Frescura, volumen, claves únicas, rechazos y últimas alertas | `mart_data_quality`, `lake/alerts.log` |

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

Si no hay avisos, el log deja una línea `INFO | no_alerts`. Hasta la etapa 6 no hay
schedule: las alertas solo se ejecutan cuando lanzas `make alerts` (o un cron
externo). La notificación es local; no se envían datos a Telegram ni e-mail.

## Tests

```bash
make test
uv run pytest tests/unit/test_alerts.py tests/unit/test_dashboard.py -q
```

- Reglas: casos que disparan y no disparan, límites y orden estable.
- Runner: warehouse temporal, escritura del log y ausencia de warehouse.
- Consultas: warehouse demo sintético; se comprueba que todos los marts
  necesarios existen y devuelven datos.
- Las páginas se validaron con `streamlit.testing.v1.AppTest` en modo demo.

## Privacidad

- La app no lee Silver ni Bronze, y no muestra coordenadas ni datos de salud.
- El modo demo solo usa datos ficticios generados por
  `scripts/make_demo_warehouse.py` (semilla determinista).
- No se versionan `lake/`, `lake_demo/`, `*.duckdb`, FIT ni logs.

## Limitaciones actuales

- Sin orquestación, los datos no se actualizan solos; el dashboard refleja el
  último `make dbt-build`.
- La frescura puede marcar `data_stale` si no se reconstruye Gold en 36 h. Es
  información real, no un fallo de la app.
- No hay autenticación: está pensado para `localhost`.
- Los modelos predictivos quedan para la etapa 8.
