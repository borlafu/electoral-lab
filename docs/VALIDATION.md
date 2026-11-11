# Validación

Ejecuta `uv run electoral data validate` y `uv run pytest -q`.

| Comprobación | Resultado |
|---|---|
| Escaños 2026 (RD 806/2026) | 52 circunscripciones, 350 escaños |
| Censo INE | 38 728 356 electores |
| Candidaturas proclamadas | 534 en 52 circunscripciones |
| Cuadre de votos 2019N y 2023 | descuadre máximo 0 votos (tras corregir Cáceres 2023) |
| Reparto oficial 2019N | 52/52 provincias reproducidas |
| Reparto oficial 2023 | 52/52 provincias reproducidas |
| Estimador condicional vs Monte Carlo directo (M1000) | coinciden dentro de 1–2 errores estándar (ver `pivotal.csv`) |

## Tests
- `tests/legal`: D'Hondt, umbral, empates, Ceuta/Melilla, propiedades (hypothesis): monotonía, suma de escaños.
- `tests/pivotal`: umbrales exactos frente a búsqueda por fuerza bruta; estimador frente a enumeración exacta.
- `tests/ingestion`: parsers de wikitext, fechas de campo, anexo del RD, candidaturas, ZIP del Interior.
- `tests/models`: el filtro de Kalman recupera nivel y efectos de casa sintéticos.
- `tests/integration`: reproducción de los repartos oficiales.
