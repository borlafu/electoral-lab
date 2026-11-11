# Fuentes de datos

Catálogo en `configs/sources/sources.yaml`. Jerarquía: oficial > estadística oficial > secundaria.

| Tabla | Fuente | Tipo | Notas |
|---|---|---|---|
| constituencies_2026 | [RD 806/2026, BOE](https://www.boe.es/eli/es/rd/2026/10/05/806) | oficial | escaños por circunscripción (350) |
| candidacies_2026 | [BOE-A-2026-23103](https://www.boe.es/boe/dias/2026/11/03/pdfs/BOE-A-2026-23103.pdf) | oficial | 534 candidaturas proclamadas; texto de margen invertido corregido |
| censo_2026 | [INE, censo electoral 29-N](https://www.ine.es/dyngs/Prensa/EG2026.pdf) | estadística oficial | 38 728 356 electores (CER + CERA) |
| polls_national | [Wikipedia, sondeos 2026](https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Spanish_general_election) | secundaria | enlaza a cada sondeo; se excluyen encuestas internas de partidos |
| results_congreso / totals_congreso | [Wikipedia, resultados 2023](https://en.wikipedia.org/wiki/Results_of_the_2023_Spanish_Congress_election) y páginas por circunscripción | secundaria | validadas reproduciendo el reparto oficial |
| ep2024_profile | [Wikipedia, europeas 2024](https://en.wikipedia.org/wiki/Results_of_the_2024_European_Parliament_election_in_Spain) | secundaria | proporción Podemos/Sumar por provincia |

## Alternativa oficial para resultados
El área de descargas del [Ministerio del Interior](https://infoelectoral.interior.gob.es/es/elecciones-celebradas/area-de-descargas/)
ofrece ZIP de ancho fijo (formato documentado también por [rOpenSpain/infoelectoral](https://github.com/rOpenSpain/infoelectoral)).
Su web bloquea descargas automatizadas; descarga el ZIP en el navegador y usa
`electoral sources import-interior <zip> --election congreso_2023`.

## Correcciones aplicadas
- Cáceres 2023: el total de votos válidos de la fuente secundaria tenía +40 000; se recalcula desde la suma
  de candidaturas + blanco (queda registrado en la reconciliación).
- Ceuta: «PODEMOS (PAZ, CASA Y TRABAJO)» se mapea a PODEMOS con advertencia.
- Fuerza Valenciana (FV) se imputa dentro de FA_FV cuando el sondeo no la publica.
