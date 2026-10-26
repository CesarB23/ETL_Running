# Seguridad y privacidad

Este proyecto procesa datos personales de salud y ubicación (GPS, frecuencia
cardíaca, nombre de usuario). El repositorio es público: **ningún dato real debe
versionarse**.

## Reglas

- `.env`, tokens y API keys nunca se commitean (`.env` está en `.gitignore`).
- `lake/`, los `*.duckdb` y los archivos `.fit` reales están ignorados por git.
- Los fixtures de `tests/fixtures/` son sintéticos o pasan por
  `scripts/anonymize.py` (coordenadas ficticias, sin nombres ni URLs de perfil).
- Los logs redactan tokens, API keys y contraseñas; no incluyen payloads completos.

## Antes de publicar o compartir algo

1. `git grep -nE '"owner(FullName|DisplayName)": "' -- tests/fixtures` no debe devolver nada (valores reales, no nombres de clave).
2. Ejecuta `make test`: incluye un test que falla si un fixture contiene datos personales.
3. Revisa que no haya capturas con mapas, coordenadas o nombres reales.

## Reportar un problema

Si encuentras un dato personal o una credencial expuestos en el repo, abre un issue
sin copiar el dato, o contacta al autor directamente. Si una API key llegó a
publicarse, revócala en <https://connect.garmin.com/app/settings/personalApiToken>.
