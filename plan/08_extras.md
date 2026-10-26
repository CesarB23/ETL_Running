# Etapa 8 — Extras

**Estado:** PENDIENTE · **Depende de:** etapa 7

Etapa opcional. Dado el objetivo de uso personal + portafolio (D11), la **opción D es
la recomendada** y puede hacerse en paralelo desde la etapa 4. El resto se elige
según interés. Cada bloque se planifica en detalle al llegar y se cierra con la
misma disciplina (criterios + evidencia).

## Opciones

### A. Predicción y análisis avanzado
- Estimación de VO2max/forma física a partir de ritmo en zona 2 y FC.
- Predicción de tiempos de 5K/10K (Riegel y modelo con tus datos).
- Riesgo de sobrecarga con un modelo simple (regresión logística sobre carga aguda/crónica y variación de ritmo/eficiencia).
- Verificación: validación temporal (entrenar con el pasado, predecir las siguientes N semanas) y comparación contra una línea base ingenua.

### B. Nube
- Bronze/silver en S3 o GCS; DuckDB/MotherDuck o BigQuery para gold.
- Infraestructura como código (Terraform), secretos en un gestor, ejecución programada en la nube.
- Verificación: `terraform plan/apply` reproducible y pipeline diario corriendo sin tu Mac.

### C. Observabilidad y operación
- Métricas de pipeline (duración, filas, fallos) exportadas y graficadas.
- Alertas de operación, runbook, pruebas de recuperación (borrar silver y regenerar).
- Verificación: ejercicio de desastre documentado (regenerar todo desde bronze en < X min).

### D. Publicación como portafolio (recomendada)
- Generador de **datos sintéticos realistas** (`scripts/make_demo_data.py`) que reproduce la forma de bronze/FIT, con semilla fija, para que cualquiera ejecute el pipeline completo sin cuenta Garmin.
- Demo pública (Streamlit Community Cloud u otra) con warehouse sintético.
- README con diagrama, decisiones de diseño (ADR), capturas y cómo correr; `docs/` pulido; CI con badges.
- Auditoría de privacidad antes de publicar: `git log` y árbol sin `.env`, `lake/`, coordenadas, nombres ni IDs reales (herramienta tipo `gitleaks` + test propio).
- Verificación: un tercero clona el repo y levanta la demo con un solo comando (`make demo`); la auditoría de secretos pasa en CI.

## Criterio común de cierre
- Un comando reproduce el resultado.
- Los resultados se comparan contra una línea base o una referencia externa.
- `MEMORY.md` documenta decisiones y aprendizajes.

## Evidencia
_(rellenar según la opción elegida)_

## Preguntas abiertas
- Resuelta (D11): prioridad = D (portafolio). ¿Cuál de A, B o C se suma después?
