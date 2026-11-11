"""Estimación de E_{p,c}: escaños esperados que añade un voto más a la candidatura p en c.

    E_{p,c} = E[ A_p(V_p + 1, V_-p) - A_p(V_p, V_-p) ]

Estimador condicional (Rao-Blackwell). En el simulador, dado todo lo demás (participación,
factores nacionales y regionales, votos del resto), V_{p,c} es lognormal con log-media mu y sd
sigma conocidas. Para cada simulación s, con V_-p fijo, la escalera A_p(n) solo salta en los
puntos exactos n*_k (breakpoints.seat_steps). Por tanto

    E[A_p(V+k) - A_p(V) | resto_s] = sum_k jump_k * P(n*_k - k <= V <= n*_k - 1 | mu_s, sigma)

con la masa de la lognormal discretizada: P(V = m) = Phi((log(m+1/2)-mu)/sigma) - Phi((log(m-1/2)-mu)/sigma).
Promediar sobre s da un estimador insesgado (salvo discretización) con varianza muy inferior al
Monte Carlo directo, que casi siempre observa diferencias nulas.

Aproximación declarada: al condicionar se mantiene fijo el voto del resto aunque, en el modelo,
V_p y V_-p comparten participación y factores; esa dependencia ya está en mu_s, así que solo se
ignora la (inexistente) correlación del ruido final eps, que es independiente por construcción.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.special import ndtr

from electoral_lab.pivotal.breakpoints import seat_steps
from electoral_lab.simulation.engine import SimResult, rules_for


@dataclass
class PivotalResult:
    province: str
    party: str
    E: float  # escaños por voto adicional
    se: float  # error estándar Monte Carlo del estimador condicional
    ess: float
    n_sims: int
    increments: dict[int, float]  # M(k) = E[A(V+k) - A(V)]
    increments_se: dict[int, float]
    displaced: dict[str, float]  # reparto de E según la candidatura que pierde el escaño
    causes: dict[str, float]
    direct_k: int = 1000
    direct_mean: float = float("nan")  # MC directo de M(direct_k) para contraste
    direct_se: float = float("nan")
    seats_mean: float = 0.0
    dist_next_seat: np.ndarray = field(default_factory=lambda: np.zeros(0))  # votos que faltan (por sim)
    dist_lose_seat: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def one_in(self) -> float:
        return 1.0 / self.E if self.E > 0 else float("inf")


def _mass(lo: np.ndarray, hi: np.ndarray, mu: float, sd: float) -> np.ndarray:
    """P(lo <= V <= hi) para V lognormal discretizada (enteros)."""
    lo = np.maximum(lo, 0)
    a = np.where(lo <= 0, 0.0, ndtr((np.log(np.maximum(lo - 0.5, 1e-9)) - mu) / sd))
    a = np.where(lo <= 0, 0.0, a)
    b = ndtr((np.log(np.maximum(hi + 0.5, 1e-9)) - mu) / sd)
    return np.where(hi >= lo, b - a, 0.0)


def estimate(sim: SimResult, province_idx: int, entity: str, increments=(1, 10, 100, 1000),
             max_sims: int | None = 4000, direct_k: int = 1000) -> PivotalResult:
    terr = sim.terr
    c = province_idx
    e = terr.entities.index(entity)
    if not terr.contest[e, c]:
        raise ValueError(f"{entity} no concurre en {terr.names[c]}")
    rules = rules_for(terr, c)
    elig = terr.seat_eligible
    ents = [i for i in np.flatnonzero(terr.contest[:, c] & elig) if i != e]
    names = [terr.entities[i] for i in ents]
    S = sim.n if max_sims is None else min(sim.n, max_sims)
    sd = float(sim.sigma_eps[e, c])
    ks = sorted(set(increments) | {1})
    acc = {k: np.zeros(S) for k in ks}
    disp = np.zeros(len(ents) + 1)
    causes: dict[str, float] = {}
    dist_next = np.full(S, np.nan)
    dist_lose = np.full(S, np.nan)
    for s in range(S):
        others = sim.votes[s, ents, c]
        blank = int(sim.blank[s, c] + sim.votes[s, ~elig, c].sum())
        mu = float(sim.log_mu[s, e, c])
        n_hi = int(np.exp(mu + 7 * sd)) + max(ks) + 2
        n_lo = max(int(np.exp(mu - 7 * sd)) - 1, 0)
        steps = seat_steps(rules, others, blank, n_hi, n_lo)
        if not steps:
            continue
        ns = np.array([st.n for st in steps])
        jumps = np.array([st.jump for st in steps])
        for k in ks:
            acc[k][s] = float((jumps * _mass(ns - k, ns - 1, mu, sd)).sum())
        m1 = jumps * _mass(ns - 1, ns - 1, mu, sd)
        for st, w in zip(steps, m1, strict=False):
            disp[st.displaced if st.displaced >= 0 else -1] += w
            causes[st.cause] = causes.get(st.cause, 0.0) + w
        v = int(sim.votes[s, e, c])
        up = ns[ns > v]
        dist_next[s] = up.min() - v if len(up) else np.nan
        down = ns[ns <= v]
        dist_lose[s] = v - down.max() + 1 if len(down) else np.nan
    E1 = acc[1]
    mean = float(E1.mean())
    se = float(E1.std(ddof=1) / np.sqrt(S)) if S > 1 else float("nan")
    ess = float(E1.sum() ** 2 / max((E1**2).sum(), 1e-300)) if E1.any() else 0.0
    # contraste: MC directo con incremento grande (k votos), sobre todas las simulaciones
    from electoral_lab.legal.allocation import allocate_many

    allents = np.flatnonzero(terr.contest[:, c] & elig)
    pos = list(allents).index(e)
    V = sim.votes[:, allents, c].copy()
    B = sim.blank[:, c] + sim.votes[:, ~elig, c].sum(axis=1)
    V[:, pos] += direct_k
    after = allocate_many(rules, V, B)[:, pos]
    diff = after - sim.seats[:, e, c]
    total = disp.sum()
    lab = names + ["(ninguna)"]
    return PivotalResult(
        province=terr.prov[c], party=entity, E=mean, se=se, ess=ess, n_sims=S,
        increments={k: float(acc[k].mean()) for k in ks},
        increments_se={k: float(acc[k].std(ddof=1) / np.sqrt(S)) for k in ks},
        displaced={lab[i]: float(disp[i] / total) for i in range(len(lab)) if total > 0 and disp[i] > 0},
        causes={k: v / total for k, v in causes.items()} if total > 0 else {},
        direct_k=direct_k, direct_mean=float(diff.mean()), direct_se=float(diff.std(ddof=1) / np.sqrt(len(diff))),
        seats_mean=float(sim.seats[:, e, c].mean()), dist_next_seat=dist_next, dist_lose_seat=dist_lose,
    )


def estimate_province(sim: SimResult, code: str, **kw) -> list[PivotalResult]:
    terr = sim.terr
    c = terr.index(code)
    out = []
    for e in np.flatnonzero(terr.contest[:, c] & terr.seat_eligible):
        out.append(estimate(sim, c, terr.entities[e], **kw))
    return sorted(out, key=lambda r: -r.E)


def to_frame(results: list[PivotalResult], terr) -> pd.DataFrame:
    rows = []
    for r in results:
        c = terr.index(r.province)
        rows.append(dict(
            province=r.province, province_name=terr.names[c], party=r.party, seats_mean=r.seats_mean,
            E=r.E, se=r.se, one_in=r.one_in, E_per_100k=r.E * 1e5,
            M10=r.increments.get(10), M100=r.increments.get(100), M1000=r.increments.get(1000),
            direct_M1000=r.direct_mean, direct_M1000_se=r.direct_se, ess=r.ess, n_sims=r.n_sims,
            median_votes_to_next=float(np.nanmedian(r.dist_next_seat)) if np.isfinite(r.dist_next_seat).any() else None,
            top_displaced=max(r.displaced, key=r.displaced.get) if r.displaced else None,
        ))
    return pd.DataFrame(rows)
