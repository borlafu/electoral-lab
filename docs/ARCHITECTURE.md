# Arquitectura

```
src/electoral_lab/
  storage/        paths, archivo raw con SHA-256 (raw.py), catálogo SQLite de descargas y ejecuciones
  ingestion/      wikitable (parser wikitext con rowspan/colspan), polls_wikipedia, results_wikipedia,
                  official (RD convocatoria, candidaturas BOE con pdfplumber, censo INE), ep2024,
                  interior (importador ZIP de ancho fijo del Ministerio), refresh (orquestación + seed)
  geography/      catálogo de provincias, alias y resolución de municipios (Bilbao → 48)
  party_registry/ registro de candidaturas 2026, etiquetas de sondeos y herencias 2023 → 2026
  legal/          motor de reparto exacto (umbral 3 %, D'Hondt, empates, Ceuta/Melilla)
  models/         national.py (Kalman + efectos casa), territorial.py (perfiles, σ calibrada)
  simulation/     engine.py: n mundos → votos enteros por candidatura y circunscripción → escaños
  pivotal/        breakpoints.py (umbrales exactos de la escalera A_p(n)), estimator.py (Rao-Blackwell)
  validation/     comprobaciones de datos y reproducción de repartos oficiales
  pipeline.py     ejecución completa y artefactos en data/runs/
  cli/main.py     Typer: sources, data, run, report, ui
  ui/app.py       Streamlit
```

## Flujo de datos
1. `data/raw/<fuente>/<sha>.<ext>`: originales inmutables + registro en `data/catalog.sqlite`.
2. `data/normalized/*.csv`: tablas limpias (si no existen se usan las de `data/seed/`).
3. `data/runs/<run_id>/`: `manifest.json`, `national_*.csv`, `seats_*.csv`, `votes_province.csv`,
   `pivotal.csv`, `pivotal_detail.json`, `dist_next_<prov>_<partido>.npy`, `sims.npz`.

## Decisiones
- El motor legal no conoce los modelos; recibe votos enteros. Así se testea aislado.
- Los sorteos se representan como escaños esperados para que A(V+1) − A(V) no tenga ruido propio.
- La configuración (`configs/models/default.yaml`) se sobrescribe con `--set clave=valor` y su hash
  queda en el manifiesto.
