# Model card

## Cantidad estimada
$$ E_{p,c} = \mathbb{E}\left[A_p(V_{p,c}+1, V_{-p,c}) - A_p(V_{p,c}, V_{-p,c})\right] $$
donde $A_p$ es el reparto legal de la circunscripción $c$ y la esperanza se toma sobre la incertidumbre
del día de la elección. También se publican $M_k$ (efecto de +k votos, k = 10, 100, 1000).

## Modelo nacional (`models/national.py`)
- Paseo aleatorio en logit por grupo + efecto de casa por encuestadora; filtro de Kalman, hiperparámetros
  por máxima verosimilitud.
- n_eff = min(n, 2500) × 0,6; varianza de redondeo añadida (sondeos publicados con un decimal).
- Supuesto de identificación: efecto de casa medio = 0. El riesgo de sesgo conjunto lo cubre el error del día E:
  sd logit 0,09 (0,16 para partidos < 4 %) + factor de bloque izquierda/derecha sd 0,05.
- Excluidos: encuestas internas de partidos; en trackings diarios solo olas no solapadas.
- Sumar y Podemos se modelan por separado; FA (Sumar) y FV (Compromís) forman el grupo nacional FA_FV.

## Modelo territorial (`models/territorial.py`)
- Base 2023 con herencias: voto de Sumar 2023 repartido entre FA/Podemos/Compromís con la proporción de las
  europeas 2024; SALF con su perfil de 2024; Adelante Andalucía uniforme en Andalucía.
- Error provincial lognormal con varianza calibrada en el swing 2019N → 2023:
  var = 0,0093 + 0,00169 / cuota (n = 220 puntos), suelo 0,06, techo 0,6; 40 % de la varianza común por CCAA.
- Participación: desplazamiento nacional (sd logit 0,12) + provincial (0,05); blanco lognormal (0,15).
- Listas locales sin sondeo (Soria ¡Ya!, Teruel Existe, Geroa Bai) con sd 0,30 sobre su resultado previo.
- Resto de candidaturas (OTROS) agregadas: cuentan para la base del 3 % pero no pueden obtener escaño
  (ninguna lo obtuvo en 2019N ni 2023).

## Estimador de E_p,c (`pivotal/estimator.py`)
Rao-Blackwell: condicionado al resto, $V_{p,c}$ es lognormal conocida y la escalera $A_p(n)$ solo salta
en umbrales exactos calculados con aritmética entera; se integra la masa de probabilidad en esos umbrales.
Se contrasta con Monte Carlo directo (+1000 votos).

## Limitaciones
- Las fuentes de sondeos y resultados históricos son secundarias (Wikipedia), aunque validadas.
- Los sondeos españoles han fallado históricamente en más de 2 pp para algún partido; el error del día E es
  un supuesto, no una estimación. Usa `--set national.election_day_sd=…` y `territorial.sigma_scale=…`.
- Las candidaturas nuevas (SALF, Adelante en generales) tienen un perfil territorial muy incierto.
- Un E_p,c muy bajo (p. ej. partido lejos del 3 %) es sensible a las colas de la distribución.
- No es una recomendación de voto.
