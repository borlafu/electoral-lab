"""Modelo territorial: de cuotas nacionales a votos por candidatura y circunscripción.

Perfil base b_{e,c}: cuota de la entidad e en la provincia c en la elección base (2023), con
herencias documentadas (Sumar 2023 -> FA / Podemos / Compromís según la proporción Podemos/Sumar de
las europeas de 2024; SALF con su perfil de 2024; Adelante uniforme en Andalucía).

Para cada simulación s:

  1. Participación  T_c = expit(logit(t23_c) + d_nat + d_c);  válidos_c = censo26_c * T_c * (1 - nulos23_c)
  2. Factor regional  eta_{e,R} ~ N(0, rho * sigma_{e,c}^2)                       (correlación dentro de la CCAA)
  3. Cuotas esperadas  pi_{e,c} ∝ b_{e,c} * r_g * exp(eta_{e,R(c)}),   normalizadas a (1 - blanco_c)
     con r_g calibrado para que la suma nacional ponderada coincida con la cuota nacional simulada s_g.
  4. Votos  V_{e,c} = válidos_c * pi_{e,c} * exp(eps_{e,c} - sigma_eps^2/2),  eps ~ N(0, (1-rho) sigma_{e,c}^2)
     independiente entre candidaturas. Es esta última capa la que el estimador condicional integra
     analíticamente: dado el resto, V_{p,c} es lognormal con parámetros conocidos.

sigma_{e,c} depende del tamaño de la candidatura en la provincia y se calibra con los residuos del
swing proporcional 2019N -> 2023 (véase calibrate_sigma).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from electoral_lab.geography.catalog import provinces
from electoral_lab.party_registry.registry import OTHERS, Registry

BLANK = "BLANCO"


@dataclass
class SigmaModel:
    a: float  # varianza mínima (log)
    b: float  # término ~ 1/cuota
    floor: float
    cap: float
    n_points: int = 0
    notes: str = ""

    def sd(self, share: np.ndarray) -> np.ndarray:
        s = np.sqrt(self.a + self.b / np.maximum(share, 1e-3))
        return np.clip(s, self.floor, self.cap)


@dataclass
class Territory:
    prov: list[str]  # códigos INE
    names: list[str]
    ccaa: np.ndarray  # índice de CCAA por provincia
    seats: np.ndarray
    electors: np.ndarray
    turnout_base: np.ndarray
    null_rate: np.ndarray
    blank_rate: np.ndarray
    entities: list[str]  # entidades de papeleta (incluye OTROS)
    groups: list[str]  # entidad nacional por entidad (OTROS -> OTROS_BLANCO; locales -> su id)
    contest: np.ndarray  # [E, C] bool
    base: np.ndarray  # [E, C] cuotas base sobre voto válido
    sigma: np.ndarray  # [E, C] sd total (log)
    seat_eligible: np.ndarray  # [E] False para OTROS
    phi_podemos: np.ndarray  # [C]
    sigma_model: SigmaModel | None = None
    notes: list[str] = field(default_factory=list)

    def index(self, code: str) -> int:
        return self.prov.index(code)

    def weights(self) -> np.ndarray:
        v = self.electors * self.turnout_base * (1 - self.null_rate)
        return v / v.sum()


# ---------------------------------------------------------------- perfiles base
def _shares(results: pd.DataFrame, totals: pd.DataFrame, election: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = results[results.election == election]
    t = totals[totals.election == election].set_index("province")
    sh = r.pivot_table(index="label", columns="province", values="votes", aggfunc="sum").fillna(0.0)
    sh = sh / t["valid"].reindex(sh.columns).to_numpy()[None, :]
    return sh, t


def calibrate_sigma(results: pd.DataFrame, totals: pd.DataFrame, reg: Registry, cfg: dict) -> SigmaModel:
    """Ajusta Var(log swing residual) = a + b/cuota con los cambios 2019N -> 2023."""
    e0, e1 = cfg["calib_election_pair"]
    s0, t0 = _shares(results, totals, e0)
    s1, t1 = _shares(results, totals, e1)
    w1 = t1["valid"] / t1["valid"].sum()
    xs, ys = [], []
    fams = {pid: (reg.base_labels(pid, e0), reg.base_labels(pid, e1)) for pid in reg.national_ids}
    fams["SUMAR_FAMILY"] = (reg.sumar_family.get(e0, []), reg.sumar_family.get(e1, []))
    for _pid, (l0, l1) in fams.items():
        if not l0 or not l1:
            continue
        a = s0.reindex(l0).fillna(0).sum()
        b = s1.reindex(l1).fillna(0).sum()
        both = (a > 0.005) & (b > 0.005)
        if both.sum() < 3:
            continue
        nat0 = (a[both] * w1[both.index[both]]).sum()
        nat1 = (b[both] * w1[both.index[both]]).sum()
        d = np.log(b[both] / a[both]) - np.log(nat1 / nat0)
        xs.extend(b[both].to_numpy())
        ys.extend((d**2).to_numpy())
    x, y = np.array(xs), np.array(ys)
    # mínimos cuadrados robustos (recorte del 2 % superior) de y ~ a + b/x
    keep = y <= np.quantile(y, 0.98)
    A = np.c_[np.ones(keep.sum()), 1 / x[keep]]
    coef, *_ = np.linalg.lstsq(A, y[keep], rcond=None)
    a_, b_ = max(coef[0], 0.0), max(coef[1], 0.0)
    return SigmaModel(a_, b_, cfg["sd_floor"], cfg["sd_cap"], int(keep.sum()),
                      f"ajuste {e0}->{e1}: var = {a_:.4f} + {b_:.5f}/cuota, n={int(keep.sum())}")


def build(tables: dict[str, pd.DataFrame], reg: Registry, cfg: dict) -> Territory:
    tcfg = cfg["territorial"]
    base_el = tcfg["base_election"]
    provs = provinces()
    codes = sorted(provs)
    seats = tables["seats"].set_index("province").seats.reindex(codes).to_numpy()
    electors = tables["censo"].set_index("province").electors.reindex(codes).to_numpy(float)
    tot = tables["totals"][tables["totals"].election == base_el].set_index("province").reindex(codes)
    turnout = (tot.votes_cast / tot.electors).to_numpy(float)
    null_rate = (tot["null"] / tot.votes_cast).to_numpy(float)
    blank_rate = (tot.blank / tot.valid).to_numpy(float)
    shares, _ = _shares(tables["results"], tables["totals"], base_el)
    shares = shares.reindex(columns=codes).fillna(0.0)

    cand = tables["candidacies"]
    cand = cand[cand.proclaimed.astype(str).str.lower().isin(["true", "1"])]
    contest_sets = cand.groupby("province").party_id.apply(set).to_dict()

    ep = tables["ep2024"].pivot_table(index="province", columns="party", values="pct").reindex(codes)
    phi = (ep["PODEMOS"] / (ep["PODEMOS"] + ep["SUMAR"])).fillna(0.35).to_numpy()

    ent = [p for p in reg.parties if any(p in contest_sets.get(c, set()) for c in codes)] + [OTHERS]
    E, C = len(ent), len(codes)
    contest = np.zeros((E, C), bool)
    base = np.zeros((E, C))
    used_labels: set[str] = set()
    sumar_labels = reg.sumar_family.get(base_el, [])
    used_labels.update(sumar_labels)
    sumar = shares.reindex(sumar_labels).fillna(0).sum().to_numpy()
    for i, pid in enumerate(ent):
        for j, c in enumerate(codes):
            contest[i, j] = pid in contest_sets.get(c, set())
        if pid == OTHERS:
            continue
        spec = reg.parties[pid].base
        if base_el in spec and isinstance(spec[base_el], list):
            labs = spec[base_el]
            used_labels.update(labs)
            base[i] = shares.reindex(labs).fillna(0).sum().to_numpy()
        elif base_el in spec and isinstance(spec[base_el], dict) and "sumar_split" in spec[base_el]:
            kind = spec[base_el]["sumar_split"]
            pod_runs = np.array([("PODEMOS" in contest_sets.get(c, set())) for c in codes])
            heir_runs = np.array([bool({"FA", "FV"} & contest_sets.get(c, set())) for c in codes])
            if kind == "podemos":
                base[i] = sumar * np.where(heir_runs, phi, 1.0)
            else:  # FA / FV: lo que no es Podemos (o todo si Podemos no concurre)
                base[i] = sumar * np.where(pod_runs, 1 - phi, 1.0)
        elif "ep_2024" in spec:
            base[i] = ep[spec["ep_2024"]].fillna(0).to_numpy() / 100.0
        elif "uniform_in_ccaa" in spec:
            base[i] = np.array([0.05 if provs[c].ccaa_code == spec["uniform_in_ccaa"] else 0.0 for c in codes])
        base[i] *= contest[i]
    # OTROS: residuo de 2023 (todas las etiquetas no heredadas), con un mínimo del 0,5 %
    oi = ent.index(OTHERS)
    other_labels = [lab for lab in shares.index if lab not in used_labels]
    base[oi] = np.maximum(shares.reindex(other_labels).fillna(0).sum().to_numpy(), 0.005)
    contest[oi] = True
    # entidades sin perfil (p. ej. una lista nueva) -> 0,5 % donde concurren
    for i in range(E):
        miss = contest[i] & (base[i] <= 0)
        base[i, miss] = 0.005

    smodel = calibrate_sigma(tables["results"], tables["totals"], reg, tcfg)
    sigma = smodel.sd(np.maximum(base, 1e-3))
    for i, pid in enumerate(ent):
        if pid in reg.parties and reg.parties[pid].is_local:
            sigma[i] = np.maximum(sigma[i], tcfg["local_party_sd"])
        if pid in ("SALF", "ADELANTE", "FA", "FV", "PODEMOS"):  # perfiles heredados: más incertidumbre
            sigma[i] = np.sqrt(sigma[i] ** 2 + 0.1**2)
    sigma = sigma * float(tcfg.get("sigma_scale", 1.0))
    ccaa_codes = sorted({provs[c].ccaa_code for c in codes})
    ccaa = np.array([ccaa_codes.index(provs[c].ccaa_code) for c in codes])
    groups = [reg.group(p) if p != OTHERS else "OTROS_BLANCO" for p in ent]
    return Territory(
        prov=codes, names=[provs[c].name for c in codes], ccaa=ccaa, seats=seats, electors=electors,
        turnout_base=turnout, null_rate=null_rate, blank_rate=blank_rate, entities=ent, groups=groups,
        contest=contest, base=base, sigma=sigma, seat_eligible=np.array([p != OTHERS for p in ent]),
        phi_podemos=phi, sigma_model=smodel,
    )
