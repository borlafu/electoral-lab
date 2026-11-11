# electoral-lab

Laboratorio electoral local para las elecciones generales del **29 de noviembre de 2026** (Congreso).
Obtiene datos oficiales y sondeos, modela la incertidumbre, simula resultados, aplica el reparto legal
de la LOREG por circunscripción y estima **E_p,c**: la probabilidad de que **un voto adicional** a la
candidatura *p* en la circunscripción *c* cambie la asignación de escaños.

```
sondeos ─► modelo nacional (Kalman + efectos casa) ─┐
resultados 2019N/2023 + europeas 2024 ──► modelo territorial (σ calibrada) ─► simulación (20 000 mundos)
BOE (escaños, candidaturas) + INE (censo) ──────────┘                              │
                                     reparto legal exacto (3 % + D'Hondt, art. 163) ◄┘
                                                             │
                      E_p,c (estimador condicional Rao-Blackwell) + contraste Monte Carlo directo
```

## Requisitos

- macOS o Linux, [uv](https://docs.astral.sh/uv/) ≥ 0.4. Python 3.12 se instala solo (`.python-version`).

## Instalación

```bash
cd ~/code/electoral-lab
uv sync
export ELECTORAL_LAB_CONTACT="tu@email"   # se envía en el User-Agent al descargar fuentes
```

El repositorio incluye una instantánea de datos en `data/seed/` (sondeos hasta el 9-11-2026), así que
puede ejecutarse sin red.

## Uso

```bash
uv run electoral data validate                 # comprueba datos y reproduce el reparto oficial 2019N y 2023
uv run electoral run Málaga Madrid Bilbao      # ejecución completa (~45 s); acepta provincias o municipios
uv run electoral report                        # vuelve a imprimir el informe de la última ejecución
uv run electoral ui                            # interfaz web local en http://localhost:8501

uv run electoral sources refresh               # vuelve a descargar BOE, INE, sondeos y resultados
uv run electoral sources refresh --only polls  # solo sondeos
uv run electoral sources list                  # registro de descargas (hash, fecha, URL)
uv run electoral data seed                     # promueve los datos normalizados actuales a data/seed

# sensibilidad
uv run electoral run Málaga --set territorial.sigma_scale=0.7 --sims 40000
uv run electoral run Sevilla --set national.election_day_sd=0.12

# resultados oficiales del Ministerio del Interior (si descargas el ZIP a mano)
uv run electoral sources import-interior 02_202307_1.zip --election congreso_2023
```

Cada ejecución crea `data/runs/<fecha>_<hash>_<elección>/` con `manifest.json` (semilla, hashes de datos
y configuración, commit), CSV de resultados y `pivotal.csv` con E_p,c.

## Cómo leer E_p,c

| columna | significado |
|---|---|
| `E` | probabilidad de que tu voto cambie un escaño |
| `E_per_100k` | lo mismo por 100 000 votos (comparable entre partidos) |
| `one_in` | «1 entre N» = 1/E |
| `M1000` | probabilidad de que +1000 votos cambien algo; `direct_M1000` es el contraste por Monte Carlo directo |
| `top_displaced` | partido que con más frecuencia pierde el escaño |

E_p,c mide **eficacia marginal en escaños**, no utilidad del voto: no incorpora preferencias, gobernabilidad
ni efectos sobre financiación electoral. Véase `docs/MODEL_CARD.md`.

## Documentación

- `docs/PRD.md` – requisitos y alcance
- `docs/ARCHITECTURE.md` – módulos y flujo de datos
- `docs/DATA_SOURCES.md` – fuentes, licencias y transformaciones
- `docs/MODEL_CARD.md` – supuestos, parámetros y limitaciones
- `docs/VALIDATION.md` – pruebas y resultados de validación

## Desarrollo

```bash
uv run pytest -q
uv run ruff check src tests
```
