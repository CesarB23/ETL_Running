# ETL_Running

Plataforma de datos personal sobre mis **actividades de running** de Garmin Connect,
con arquitectura medallion local: **bronze → silver → gold → dashboard**.

Responde a tres preguntas: ¿cumplo el plan?, ¿cómo evolucionan mi ritmo y mi
eficiencia?, ¿cómo va mi carga de entrenamiento? Solo running; otros deportes y datos
de salud están fuera de alcance. Licencia MIT.

## Navegación

| Documento | Para qué |
| --- | --- |
| `CLAUDE.md` | Reglas y convenciones para agentes y colaboradores |
| `MEMORY.md` | Estado vivo, decisiones y hechos sobre los datos |
| `docs/ARCHITECTURE.md` | Capas, flujo y decisiones técnicas |
| `docs/DATA_MODEL.md` | Tablas bronze/silver/gold, claves y reglas |
| `plan/README.md` | Roadmap y cómo se verifica cada etapa |
| `plan/00..08_*.md` | Plan detallado por etapa con criterios de aceptación |

## Inicio rápido

```bash
make setup                       # uv sync (Python 3.12)
cp .env.example .env             # y pega tu GARMIN_PERSONAL_API_KEY
make test && make lint
uv run python -m etl_running --help
uv run python -m etl_running config
```

## Estado

Etapa 0 (fundamentos) implementada; la ingesta empieza en `plan/01_bronze_ingesta.md`.
