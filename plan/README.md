# Roadmap

Cada etapa produce un **resultado visible** y se cierra con **criterios de
aceptación verificables por comando**. No se empieza la siguiente sin cerrar la anterior.

| # | Etapa | Resultado visible | Depende de |
| --- | --- | --- | --- |
| 0 | [Fundamentos](00_fundamentos.md) | `make setup && make test` verde en máquina limpia | — |
| 1 | [Bronze incremental + backfill](01_bronze_ingesta.md) | Historial completo en `lake/bronze/` + informe de ingesta | 0 |
| 2 | [Silver](02_silver.md) | Tabla Parquet de actividades running consultable con DuckDB + reporte de calidad | 1 |
| 3 | [FIT → laps y records](03_fit.md) | Gráfica de una carrera segundo a segundo | 1, 2 |
| 4 | [Gold con dbt](04_gold_dbt.md) | `dbt build` verde + docs de linaje + primeras consultas de negocio | 2, 3 |
| 5 | [Plan vs real](05_plan_vs_real.md) | Tabla semanal de cumplimiento del plan | 3, 4 |
| 6 | [Orquestación](06_orquestacion.md) | Pipeline diario automático visible en Dagster | 1–5 |
| 7 | [Dashboard y alertas](07_dashboard_alertas.md) | Interfaz React/TypeScript con actividades, mapas y análisis | 4, 5 |
| 8 | [Extras](08_extras.md) | Predicción, nube u observabilidad (a elegir) | 7 |

> **Orden de ejecución:** 0–5 → 7 (dashboard, D21) → 6 (Dagster) → 8. La etapa 7
> no depende de la orquestación; se adelantó para obtener valor visible antes de
> decidir dónde corre Dagster.

## Plantilla de cada plan

Cada archivo contiene: Objetivo · Resultado visible · Alcance (dentro/fuera) ·
Entregables · Tareas · Criterios de aceptación (comandos) · Datos de prueba ·
Riesgos · Evidencia (se rellena al cerrar) · Preguntas abiertas.

## Cómo se cierra una etapa

1. Todas las tareas marcadas.
2. Se ejecutan los comandos de "Criterios de aceptación" y se pega el resultado
   resumido en "Evidencia".
3. `MEMORY.md`: estado `HECHA`, decisiones y hallazgos nuevos, fecha en el registro.
4. Commit/tag `etapa-N`.

## Principio guía: datos reales sin exponerlos

Alcance transversal: **solo running** (D15), ventana desde **2026-08-17** (D10).

Cada etapa se verifica con dos conjuntos:
- **Sintético/anonimizado** en `tests/fixtures/` → corre en CI y en cualquier máquina.
- **Real** en `lake/` → verificación local manual; nunca se versiona.
