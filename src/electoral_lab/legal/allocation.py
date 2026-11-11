"""Motor legal exacto para el Congreso de los Diputados (LOREG, arts. 163 y 170).

Este módulo no sabe nada de encuestas: recibe votos enteros y devuelve escaños.

Reglas implementadas (art. 163.1 LOREG):
  a) No se tienen en cuenta las candidaturas que no obtengan al menos el 3 % de los votos
     válidos emitidos en la circunscripción (candidaturas + blancos).
  b) Se ordenan de mayor a menor los cocientes V_i / j, j = 1..S, de las candidaturas restantes.
  c) Los escaños se atribuyen a los S mayores cocientes.
     Empate de cocientes: gana la candidatura con más votos totales. Si también empatan en
     votos, el primer empate se resuelve por sorteo y los sucesivos de forma alternativa.
Ceuta y Melilla (art. 170): sale elegido el candidato con más votos (sin umbral).

Diseño numérico:
  * Los cocientes se comparan como float64. Para votos < 2**31 y S < 1000, la división IEEE es
    correctamente redondeada: dos racionales iguales producen el mismo float y dos distintos
    difieren en más de 1 ulp, así que la ordenación es exacta (ver tests).
  * El sorteo se representa por defecto como escaños esperados (fracciones), de modo que
    A_p(V + e_p) - A_p(V) no introduce aleatoriedad independiente entre mundos contrafactuales.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

MAX_VOTES = 2**31 - 1


@dataclass(frozen=True)
class ConstituencyRules:
    seats: int
    method: Literal["dhondt", "plurality"] = "dhondt"
    threshold_num: int = 3  # 3 %
    threshold_den: int = 100
    legal_basis: str = "LOREG art. 163"

    @staticmethod
    def congreso(seats: int) -> ConstituencyRules:
        if seats == 1:
            return ConstituencyRules(seats=1, method="plurality", threshold_num=0, legal_basis="LOREG art. 170")
        return ConstituencyRules(seats=seats)


@dataclass
class AllocationResult:
    seats: np.ndarray  # escaños esperados (float; enteros salvo sorteo)
    eligible: np.ndarray  # bool, supera el umbral
    valid_votes: int
    threshold_votes: int  # mínimo de votos para superar el umbral
    last_winner: tuple[int, int] | None = None  # (partido, divisor)
    first_loser: tuple[int, int] | None = None
    lottery: bool = False
    explanation: list[str] = field(default_factory=list)

    @property
    def seats_int(self) -> np.ndarray:
        return np.rint(self.seats).astype(int)


def threshold_votes(valid_votes: int, rules: ConstituencyRules) -> int:
    """Mínimo entero n con n * den >= num * valid (\"al menos el 3 por 100\")."""
    if rules.threshold_num == 0:
        return 0
    return -(-rules.threshold_num * valid_votes // rules.threshold_den)


def _check(votes: np.ndarray, blank: int) -> None:
    if votes.ndim != 1:
        raise ValueError("votes debe ser un vector")
    if (votes < 0).any() or blank < 0:
        raise ValueError("votos negativos")
    if votes.sum() + blank > MAX_VOTES:
        raise ValueError("demasiados votos para la comparación exacta en float64")


def allocate(
    rules: ConstituencyRules,
    votes: Sequence[int] | np.ndarray,
    blank: int = 0,
    explain: bool = False,
) -> AllocationResult:
    v = np.asarray(votes, dtype=np.int64)
    _check(v, int(blank))
    valid = int(v.sum() + blank)
    thr = threshold_votes(valid, rules)
    eligible = v >= thr if rules.threshold_num else np.ones_like(v, dtype=bool)
    eligible &= v > 0
    seats = np.zeros(len(v), dtype=float)
    expl: list[str] = []

    if rules.method == "plurality":
        if not eligible.any():
            return AllocationResult(seats, eligible, valid, thr, explanation=["sin votos"])
        top = v.max()
        winners = np.flatnonzero(v == top)
        seats[winners] = 1.0 / len(winners)
        if explain:
            expl.append(f"Mayoría simple: gana {winners.tolist()} con {top} votos")
        return AllocationResult(seats, eligible, valid, thr, lottery=len(winners) > 1, explanation=expl)

    S = rules.seats
    idx = np.flatnonzero(eligible)
    if len(idx) == 0:
        return AllocationResult(seats, eligible, valid, thr, explanation=["ninguna candidatura supera el umbral"])
    div = np.arange(1, S + 1)
    party = np.repeat(idx, S)
    dv = np.tile(div, len(idx))
    tot = v[party]
    q = tot / dv
    # orden: cociente desc, votos totales desc (desempate legal)
    order = np.lexsort((-tot, -q))
    party, dv, tot, q = party[order], dv[order], tot[order], q[order]
    n = len(q)
    if n <= S:
        np.add.at(seats, party, 1.0)
        return AllocationResult(seats, eligible, valid, thr, explanation=expl)
    # ¿empate exacto (cociente y votos totales) cruzando la frontera S?
    qc, tc = q[S - 1], tot[S - 1]
    tied = np.flatnonzero((q == qc) & (tot == tc))
    lottery = bool(len(tied) > 1 and tied.min() < S <= tied.max())
    if lottery:
        inside = int((tied < S).sum())
        sure = np.arange(S) [~np.isin(np.arange(S), tied)]
        np.add.at(seats, party[sure], 1.0)
        np.add.at(seats, party[tied], inside / len(tied))
        expl.append(
            f"Sorteo legal entre candidaturas {sorted(set(party[tied].tolist()))}: {inside} escaño(s) para {len(tied)} cocientes empatados"
        )
    else:
        np.add.at(seats, party[:S], 1.0)
    res = AllocationResult(
        seats,
        eligible,
        valid,
        thr,
        last_winner=(int(party[S - 1]), int(dv[S - 1])),
        first_loser=(int(party[S]), int(dv[S])),
        lottery=lottery,
        explanation=expl,
    )
    if explain:
        res.explanation.insert(0, f"Votos válidos {valid}; umbral 3 % = {thr} votos")
        for k in range(min(n, S + 3)):
            mark = "ESCAÑO" if k < S else "fuera"
            res.explanation.append(f"{k + 1:>3}. cand {party[k]} / {dv[k]} = {q[k]:.2f}  [{mark}]")
    return res


def allocate_many(rules: ConstituencyRules, votes: np.ndarray, blank: np.ndarray) -> np.ndarray:
    """Reparto vectorizado para una matriz (simulaciones x candidaturas). Devuelve escaños esperados.

    Usa partición numérica y recurre al motor escalar exacto cuando hay un empate en la frontera.
    """
    V = np.asarray(votes, dtype=np.int64)
    B = np.asarray(blank, dtype=np.int64)
    D, P = V.shape
    out = np.zeros((D, P), dtype=float)
    if rules.method == "plurality":
        for d in range(D):
            out[d] = allocate(rules, V[d], int(B[d])).seats
        return out
    S = rules.seats
    valid = V.sum(1) + B
    thr = -(-rules.threshold_num * valid // rules.threshold_den)
    elig = (V >= thr[:, None]) & (V > 0)
    Q = V[:, :, None] / np.arange(1, S + 1)[None, None, :]
    Q = np.where(elig[:, :, None], Q, -1.0).reshape(D, P * S)
    if P * S <= S:
        return np.where(elig, S, 0).astype(float)
    part = -np.partition(-Q, (S - 1, S), axis=1)
    qS, qS1 = part[:, S - 1], part[:, S]
    counts = (Q.reshape(D, P, S) > qS1[:, None, None]).sum(2).astype(float)
    tie = (qS == qS1) & (qS > 0)
    for d in np.flatnonzero(tie):
        counts[d] = allocate(rules, V[d], int(B[d])).seats
    return counts
