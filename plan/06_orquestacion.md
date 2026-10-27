# Etapa 6 — Orquestación

**Estado:** PENDIENTE · **Depende de:** etapas 1–5

> Se ejecutará **después de la etapa 7** (D21). Falta decidir el runtime: Mac con
> `launchd`/`caffeinate` o una máquina siempre encendida.

## Objetivo
Automatizar el pipeline de extremo a extremo con Dagster: dependencias explícitas,
programación diaria, reintentos y visibilidad.

## Resultado visible
Dagster UI (`make dev`) muestra el grafo de assets bronze → silver → gold, y un
schedule diario que corre sin intervención. Un fallo deliberado muestra el error y
se reintenta.

## Alcance
**Dentro:** assets Dagster para ingesta, silver, dbt (con `dagster-dbt`), schedule,
sensor de actividades nuevas, checks de calidad como *asset checks*, alertas básicas.
**Fuera:** despliegue en la nube (etapa 8).

## Entregables
- `orchestration/definitions.py`, `assets/{bronze,silver,fit,plan}.py`, `dbt_assets.py`.
- Particiones diarias en assets de ingesta; backfill desde la UI.
- `schedules.py`: diario (p. ej. 06:30 hora local) y `sensors.py` para nuevas actividades.
- Asset checks: frescura, volumen, reconciliación bronze↔silver, tests dbt.
- `launchd` plist o servicio equivalente para correr Dagster en tu Mac (documentado).
- `make dev` y `make run-daily`.

## Tareas
- [ ] Envolver cada paso de CLI como asset sin duplicar lógica (los assets llaman a las mismas funciones).
- [ ] Integrar el proyecto dbt como assets con linaje.
- [ ] Configurar políticas de reintento y *timeouts* por asset.
- [ ] Checks de frescura (≤ 36 h sin datos → warning) y volumen.
- [ ] Schedule diario y prueba de una ejecución completa.
- [ ] Sensor: detectar actividad nueva y disparar FIT + silver + dbt incremental.
- [ ] Notificación de fallos (log/archivo; luego Telegram/e-mail opcional).
- [ ] Documentar operación: cómo relanzar, backfill, renovar la API key.

## Criterios de aceptación
```bash
make dev                                   # UI accesible, grafo completo
dagster job execute -j daily_pipeline      # corre de punta a punta en verde
```
- Una ejecución completa desde cero (lake vacío) reconstruye todo y los tests dbt pasan.
- Una segunda ejecución inmediata no crea bronze nuevo (idempotencia).
- Simular un 401 o corte de red: el asset falla, reintenta y deja el error visible.
- El schedule se dispara al menos una vez en el entorno real y queda registro.
- Los asset checks aparecen en la UI con su resultado.

## Datos de prueba
Ejecución con cliente simulado en CI; ejecución real manual.

## Riesgos
- Dagster en Python 3.12 + dbt: conflictos de versiones → fijar versiones compatibles en `pyproject.toml`.
- Un Mac que duerme no ejecuta el schedule → documentar `launchd`/`caffeinate` o mover a nube en etapa 8.

## Evidencia
_(rellenar: captura del grafo, run exitoso, run fallido con reintento)_

## Preguntas abiertas
- ¿Ejecutar en tu Mac o en una máquina siempre encendida (Raspberry, VPS, nube)?
