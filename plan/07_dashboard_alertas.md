# Etapa 7 — Dashboard y alertas

**Estado:** PENDIENTE · **Depende de:** etapas 4 y 5

## Objetivo
Hacer visible el valor del pipeline con un dashboard y alertas basadas en reglas.

## Resultado visible
`make app` abre Streamlit con páginas de:
1. **Resumen**: km semanales, tiempo, número de sesiones, última actividad.
2. **Progreso**: ritmo y eficiencia aeróbica en el tiempo.
3. **Carga**: aguda/crónica y ACWR con zonas.
4. **Plan vs real**: cumplimiento semanal y detalle por sesión.
5. **Salud del pipeline**: frescura y calidad de datos.

Y un archivo `alerts.log` con avisos generados por reglas.

## Alcance
**Dentro:** app de solo lectura sobre `warehouse.duckdb`, filtros por fecha, reglas de
alerta, notificación simple.
**Fuera:** modelos predictivos (etapa 8), autenticación multiusuario.

## Entregables
- `app/main.py` y `app/pages/*.py`, `app/queries.py` (SQL contra marts, nunca contra silver).
- `src/etl_running/alerts/rules.py` y `etl_running alerts run`.
- Reglas iniciales (umbrales en configuración):
  - ACWR > 1.5 (solo si `is_reliable`) → riesgo de sobrecarga.
  - Más de 10 días sin entrenar o semana con < 50 % del plan.
  - Datos sin actualizar > 36 h.
  - API key próxima a caducar (si se informa la fecha en config).
- `docs/DASHBOARD.md` con capturas y definición de cada KPI.

## Tareas
- [ ] Definir KPIs y su fuente en gold (sin lógica de negocio duplicada en la app).
- [ ] Página Resumen + Progreso (primero, para tener algo visible pronto).
- [ ] Página Carga.
- [ ] Página Plan vs real con detalle por bloque.
- [ ] Página de salud del pipeline desde `mart_data_quality`.
- [ ] Motor de alertas con reglas puras (función `datos → lista de avisos`) y tests unitarios.
- [ ] Opción de privacidad: ocultar mapas/coordenadas por defecto.
- [ ] **Modo demo (D11):** `DEMO_MODE=1` apunta a un warehouse sintético, con banner visible "datos sintéticos", y es lo que usan las capturas del README.
- [ ] Revisión de cada cifra contra la fuente (Garmin Connect).

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
_(rellenar: capturas de cada página, ejecución de alertas)_

## Preguntas abiertas
- ¿Streamlit, Evidence o Metabase? (propuesta: Streamlit por flexibilidad y Python).
- ¿Canal de notificación preferido (Telegram, e-mail, notificación macOS)?
