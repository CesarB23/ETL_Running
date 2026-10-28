# Etapa 7 — Dashboard y alertas

**Estado:** HECHA (2026-10-26) · **Depende de:** etapas 4 y 5

> Orden de ejecución: se hizo antes que la etapa 6 porque solo depende de Gold y
> Plan vs real, no de la orquestación (decisión D21).

## Objetivo
Hacer visible el valor del pipeline con un dashboard y alertas basadas en reglas.

## Resultado visible
`make app` abre una interfaz React + TypeScript con pestañas de:
1. **Actividades**: mapa OpenStreetMap, laps FIT y ritmos real/plan por distancia o tiempo.
2. **Progreso**: ritmo y eficiencia aeróbica en el tiempo.
3. **Carga**: aguda/crónica y ACWR.
4. **Salud del pipeline**: frescura y calidad de datos.

Y un archivo `alerts.log` con avisos generados por reglas.

## Alcance
**Dentro:** app de solo lectura sobre `warehouse.duckdb`, filtros por fecha, reglas de
alerta, notificación simple.
**Fuera:** modelos predictivos (etapa 8), autenticación multiusuario.

## Entregables
- `web/` (React/TypeScript), `app/api.py`, `app/queries.py` (consultas a Gold, nunca Silver).
- `src/etl_running/alerts/rules.py` y `etl_running alerts run`.
- Reglas iniciales (umbrales en configuración):
  - ACWR > 1.5 (solo si `is_reliable`) → riesgo de sobrecarga.
  - Más de 10 días sin entrenar o semana con < 50 % del plan.
  - Datos sin actualizar > 36 h.
  - API key próxima a caducar (si se informa la fecha en config).
- `docs/DASHBOARD.md` con capturas y definición de cada KPI.

## Tareas
- [x] Definir KPIs y su fuente en gold (sin lógica de negocio duplicada en la app).
- [x] Página Resumen + Progreso (primero, para tener algo visible pronto).
- [x] Página Carga.
- [x] Vista Actividades con mapa, ritmo por registro, promedios de vuelta y plan superpuesto.
- [x] Página de salud del pipeline desde `mart_data_quality`.
- [x] Motor de alertas con reglas puras (función `datos → lista de avisos`) y tests unitarios.
- [x] OSM con atribución y aviso de que las peticiones de teselas revelan la zona visualizada.
- [x] **Modo demo (D11):** `DEMO_MODE=1` apunta a un warehouse sintético, con banner visible "datos sintéticos", y es el único origen de demos públicas.
- [x] Revisión de cada cifra contra la fuente (Garmin Connect).

## Criterios de aceptación
```bash
make app                    # carga sin errores
make test                   # tests de reglas de alerta
etl_running alerts run      # genera avisos (o confirma que no hay)
```
- Cada KPI del dashboard coincide con una consulta SQL directa a gold (test de humo).
- Las reglas de alerta tienen tests con casos que disparan y no disparan.
- La app funciona con un `warehouse.duckdb` sintético (`DEMO_MODE=1`) y es el único origen de capturas y demos públicas.
- Tiempo de carga de cada página < 3 s con tu volumen de datos.
- Sin coordenadas ni datos personales en la demo pública.

## Datos de prueba
Warehouse sintético generado por script (`scripts/make_demo_warehouse.py`).

## Riesgos
- Métricas mal interpretadas (ACWR no es diagnóstico médico) → incluir descripción y descargo en la UI.
- Lógica de negocio filtrándose a la app → todo en dbt.

## Evidencia
- `make test`: tests Python en verde, con consultas/API de actividades contra
  warehouse sintético.
- `make lint`: ruff check + format en verde.
- `npm --prefix web run build`: TypeScript y bundle Vite compilan.
- `make dbt-build`: el Gold incluye `fct_run_track` y `fct_run_laps` para el mapa y las series.
- `DEMO_MODE=1`: API y consultas usan exclusivamente un warehouse sintético.
- `make demo` genera 37 carreras, 12 semanas, 18 sesiones de plan y 72 bloques
  sintéticos en `lake_demo/warehouse.duckdb`.
- `etl_running alerts run` con el warehouse demo escribe dos avisos esperados:
  cumplimiento bajo y API key próxima a caducar.
- El modo demo es el único origen de capturas y demos públicas; no se versionan datos personales.
- Commit React `336662c` creado localmente (pendiente de push).

## Preguntas abiertas
- **Interfaz:** React + TypeScript, con API Python local de solo lectura.
- ~~¿Canal de notificación preferido?~~ **`lake/alerts.log`** en la primera versión;
  notificación macOS/Telegram/e-mail se pospone a la etapa 6/8.
