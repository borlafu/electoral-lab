# Guía para agentes

- Python 3.12 con uv. Comandos: `uv run pytest -q`, `uv run ruff check src tests`, `uv run electoral …`.
- El motor legal (`legal/allocation.py`) es la pieza crítica: cualquier cambio requiere que
  `tests/legal` y `tests/integration` sigan reproduciendo 52/52 repartos oficiales.
- No modificar `data/raw` a mano: es un archivo inmutable con hash. Las correcciones van en el parser o
  en `data/manual/`, y se documentan en `docs/DATA_SOURCES.md`.
- Los parámetros del modelo viven en `configs/models/default.yaml`; documenta cambios en `docs/MODEL_CARD.md`.
- Textos de usuario en español. Usa `ELECTORAL_LAB_CONTACT` para el User-Agent de descargas.
