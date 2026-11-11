"""Puntos exactos en los que un voto adicional cambia el reparto.

Para una candidatura p y unos votos fijos del resto (V_-p, blancos), la función
    A_p(n) = escaños esperados de p con n votos
es una escalera no decreciente en n (más votos propios solo pueden ayudar: suben los cocientes
de p y, al crecer el total de votos válidos, otras candidaturas pueden quedar bajo el umbral).

Calculamos exactamente sus escalones n*_k = min{n : A_p(n) >= k} sin barrer n:
  * El conjunto de candidaturas elegibles (umbral del 3 %) es constante a trozos en n.
  * Dentro de cada tramo, p obtiene su k-ésimo escaño si su cociente n/k supera al
    (S-k+1)-ésimo mayor cociente del resto, con el desempate legal por votos totales.
Así, A_p(n+1) - A_p(n) != 0 solo en los puntos n = n*_k - 1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from electoral_lab.legal.allocation import ConstituencyRules, allocate


@dataclass(frozen=True)
class Step:
    n: int  # con n votos, p tiene ya el escaño (o la mitad, si hay sorteo)
    jump: float  # incremento de escaños esperados de A_p(n-1) a A_p(n)
    level: int  # k-ésimo escaño de p
    displaced: int  # índice (en 'others') de la candidatura que pierde el escaño; -1 si ninguno
    cause: str  # 'cociente' | 'umbral_propio' | 'salida_umbral_ajeno' | 'sorteo'


def _eligibility_intervals(others: np.ndarray, R: int, rules: ConstituencyRules, n_lo: int, n_hi: int):
    """Tramos [lo, hi] de n con conjunto elegible constante entre las otras candidaturas."""
    num, den = rules.threshold_num, rules.threshold_den
    if num == 0:
        return [(n_lo, n_hi, others > 0)]
    # q es elegible con n votos de p si den*V_q >= num*(n+R)  <=>  n <= floor((den*V_q - num*R)/num)
    last = np.floor_divide(den * others - num * R, num)  # último n con q elegible
    last = np.where(others > 0, last, -1)
    cuts = sorted({int(x) for x in last if n_lo <= x < n_hi})
    out = []
    lo = n_lo
    for c in cuts + [n_hi]:
        hi = c
        if hi >= lo:
            out.append((lo, hi, (last >= lo) & (others > 0)))
        lo = hi + 1
    return out


def _top_quotients(others: np.ndarray, elig: np.ndarray, S: int):
    idx = np.flatnonzero(elig)
    if len(idx) == 0:
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0, int)
    owner = np.repeat(idx, S)
    div = np.tile(np.arange(1, S + 1), len(idx))
    tot = others[owner]
    q = tot / div
    order = np.lexsort((-tot, -q))[:S]
    return owner[order], div[order], tot[order]


def seat_steps(
    rules: ConstituencyRules,
    others: np.ndarray,
    blank: int,
    n_max: int,
    n_min: int = 0,
) -> list[Step]:
    """Escalones de A_p(n) para n en [n_min, n_max]. 'others' excluye a p."""
    others = np.asarray(others, dtype=np.int64)
    R = int(others.sum() + blank)
    S = rules.seats
    if rules.method == "plurality":
        top = int(others.max()) if len(others) else 0
        steps = []
        if len(others) and top > 0:
            n_tied = int((others == top).sum())
            # con n = top empata (sorteo entre n_tied+1); con top+1 gana
            disp = int(np.argmax(others))
            if n_min <= top <= n_max:
                steps.append(Step(top, 1.0 / (n_tied + 1), 1, disp, "sorteo"))
            if n_min <= top + 1 <= n_max:
                steps.append(Step(top + 1, 1.0 - 1.0 / (n_tied + 1), 1, disp, "cociente"))
        elif n_min <= 1 <= n_max:
            steps.append(Step(1, 1.0, 1, -1, "cociente"))
        return steps

    num, den = rules.threshold_num, rules.threshold_den
    # umbral propio: (den-num)*n >= num*R
    n_thr = -(-num * R // (den - num)) if num else 1
    n_thr = max(n_thr, 1)
    lo0 = max(n_thr, n_min)
    if lo0 > n_max:
        return []
    intervals = _eligibility_intervals(others, R, rules, lo0, n_max)
    tops = [(lo, hi, _top_quotients(others, el, S)) for lo, hi, el in intervals]
    steps: list[Step] = []
    for k in range(1, S + 1):
        found = None
        for j, (lo, hi, (own, dv, tot)) in enumerate(tops):
            pos = S - k  # índice 0-based del cociente ajeno a superar
            if pos >= len(own):
                cand, lot, disp = lo, False, -1  # no hay rival para ese puesto
            else:
                a, d = int(tot[pos]), int(dv[pos])
                m, r = divmod(k * a, d)
                disp = int(own[pos])
                if r != 0 or m < a:
                    cand, lot = m + 1, False
                elif m > a:
                    cand, lot = m, False
                else:  # m == a: mismo cociente y mismos votos totales -> sorteo
                    cand, lot = m, True
            if cand < lo:
                cand, lot = lo, False
            if cand <= hi:
                if cand == lo and j == 0 and lo == n_thr:
                    cause = "umbral_propio"
                elif cand == lo and j > 0:
                    cause = "salida_umbral_ajeno"
                else:
                    cause = "sorteo" if lot else "cociente"
                found = (cand, lot, disp, cause)
                break
        if found is None:
            break  # niveles superiores tampoco caben en el rango
        cand, lot, disp, cause = found
        if lot:
            steps.append(Step(cand, 0.5, k, disp, "sorteo"))
            if cand + 1 <= n_max:
                steps.append(Step(cand + 1, 0.5, k, disp, "sorteo"))
        else:
            steps.append(Step(cand, 1.0, k, disp, cause))
    lottery_pts = {s.n for s in steps if s.cause == "sorteo"}
    if lottery_pts:
        # Con sorteos entre varias candidaturas empatadas el salto no es 1/2: se recalcula
        # exactamente con el motor legal en esos puntos (casos de medida casi nula).
        affected = lottery_pts | {x + 1 for x in lottery_pts}
        kept = [s for s in steps if s.n not in affected]
        for x in sorted(affected):
            if not (n_min <= x <= n_max) or x < 1:
                continue
            jump = seats_bruteforce(rules, others, blank, x) - seats_bruteforce(rules, others, blank, x - 1)
            if abs(jump) > 1e-12:
                ref = next((s for s in steps if s.n == x), None) or next(s for s in steps if s.n in affected)
                kept.append(Step(x, jump, ref.level, ref.displaced, "sorteo"))
        steps = sorted(kept, key=lambda s: (s.n, s.level))
    return [s for s in steps if s.n >= n_min]


def seats_bruteforce(rules: ConstituencyRules, others: np.ndarray, blank: int, n: int, p_pos: int = 0) -> float:
    v = np.insert(np.asarray(others, dtype=np.int64), p_pos, n)
    return float(allocate(rules, v, blank).seats[p_pos])
