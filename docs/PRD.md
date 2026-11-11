# PRD – electoral-lab

## Problema
Un votante quiere saber, para su circunscripción, qué probabilidad tiene su voto de cambiar el reparto
de escaños según la candidatura elegida (E_p,c), con datos actualizados y la incertidumbre explícita.

## Objetivos
1. Obtener y archivar datos oficiales (BOE, INE) y sondeos públicos, con trazabilidad (hash, URL, fecha).
2. Agregar sondeos con efectos de casa y proyectar al 29-N con incertidumbre honesta.
3. Bajar a circunscripción con error calibrado históricamente.
4. Aplicar el reparto legal exacto (LOREG arts. 163 y 170) en cada simulación.
5. Estimar E_p,c con baja varianza y contrastarlo con Monte Carlo directo.
6. Ejecutarse en local (CLI + interfaz Streamlit), reproducible por semilla y hashes.

## No objetivos
- Recomendar a quién votar. E_p,c mide eficacia marginal en escaños, no preferencia ni gobernabilidad.
- Senado (sistema mayoritario distinto), voto CERA específico, predicción de pactos.

## Usuarios y flujos
- `electoral run <lugares>`: informe de E_p,c para provincias o municipios (Bilbao → Bizkaia).
- `electoral ui`: explorar escenarios, sensibilidad y auditoría.
- `electoral sources refresh`: actualizar datos hasta el día de la elección.

## Criterios de aceptación
- 52/52 circunscripciones reproducen el reparto oficial de 2019N y 2023 a partir de votos.
- Suma de escaños = 350; censo y candidaturas proclamadas cuadran con BOE/INE.
- Estimador condicional coincide con Monte Carlo directo (M1000) dentro del error.
- `pytest` y `ruff` en verde.
