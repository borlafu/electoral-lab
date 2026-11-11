"""Simulación conjunta: cuotas nacionales -> votos por provincia -> escaños (motor legal exacto)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from electoral_lab.legal.allocation import ConstituencyRules, allocate_many
from electoral_lab.models.territorial import Territory


@dataclass
class SimResult:
    terr: Territory
    votes: np.ndarray  # [S, E, C] int64, candidaturas (OTROS incluido)
    blank: np.ndarray  # [S, C] int64 votos en blanco
    log_mu: np.ndarray  # [S, E, C] float32 log de la media condicional de V (antes del ruido final)
    sigma_eps: np.ndarray  # [E, C] sd del ruido final
    seats: np.ndarray  # [S, E, C] float32 escaños esperados (fracciones solo en sorteos)
    national: pd.DataFrame  # cuotas nacionales simuladas
    calib_error: float  # máx. |agregado - objetivo| tras calibrar

    @property
    def n(self) -> int:
        return self.votes.shape[0]

    def seats_total(self) -> pd.DataFrame:
        tot = self.seats.sum(axis=2)
        return pd.DataFrame(tot, columns=self.terr.entities)

    def province_votes(self, c: int) -> pd.DataFrame:
        return pd.DataFrame(self.votes[:, :, c], columns=self.terr.entities)

    def province_seats(self, c: int) -> pd.DataFrame:
        return pd.DataFrame(self.seats[:, :, c], columns=self.terr.entities)


def rules_for(terr: Territory, c: int) -> ConstituencyRules:
    return ConstituencyRules.congreso(int(terr.seats[c]))


def simulate(terr: Territory, nat: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> SimResult:
    tc = cfg["territorial"]
    S = len(nat)
    E, C = terr.base.shape
    R = terr.ccaa.max() + 1
    rho = tc["ccaa_share_of_variance"]
    sig_eta = terr.sigma * np.sqrt(rho)
    sig_eps = terr.sigma * np.sqrt(1 - rho)

    # 1. participación, nulos y blancos
    d_nat = rng.normal(0, tc["turnout"]["national_shift_sd"], size=(S, 1))
    d_c = rng.normal(0, tc["turnout"]["province_sd"], size=(S, C))
    T = expit(logit(terr.turnout_base)[None, :] + d_nat + d_c)
    valid = terr.electors[None, :] * T * (1 - terr.null_rate[None, :])
    blank_rate = terr.blank_rate[None, :] * np.exp(rng.normal(0, tc["turnout"]["blank_sd"], size=(S, 1))
                                                    + rng.normal(0, 0.05, size=(S, C)))

    # 2. factor regional por entidad y CCAA (se aplica con la sd de cada provincia)
    z_reg = rng.standard_normal(size=(S, E, R))
    eta = z_reg[:, :, terr.ccaa] * sig_eta[None, :, :]

    # 3. calibración de r_g
    groups = terr.groups
    calib = [g for g in dict.fromkeys(groups) if g in nat.columns]
    gidx = {g: np.array([i for i, x in enumerate(groups) if x == g]) for g in calib}
    w = valid / valid.sum(axis=1, keepdims=True)
    blank_nat = (w * blank_rate).sum(axis=1)
    target = {g: nat[g].to_numpy() for g in calib}
    if "OTROS_BLANCO" in target:
        target["OTROS_BLANCO"] = np.maximum(target["OTROS_BLANCO"] - blank_nat, 0.004)
    W0 = terr.weights()
    r = np.ones((S, E))
    for g in calib:
        B = (terr.base[gidx[g]] * W0[None, :]).sum()
        r[:, gidx[g]] = (target[g] / max(B, 1e-9))[:, None]
    core = terr.base[None, :, :] * np.exp(eta) * terr.contest[None, :, :]
    err = 0.0
    for _ in range(tc["calibration_iters"] + 1):
        raw = core * r[:, :, None]
        pi = raw / raw.sum(axis=1, keepdims=True) * (1 - blank_rate)[:, None, :]
        err = 0.0
        for g in calib:
            agg = (pi[:, gidx[g], :] * w[:, None, :]).sum(axis=(1, 2))
            ratio = target[g] / np.maximum(agg, 1e-12)
            err = max(err, float(np.max(np.abs(agg - target[g]))))
            r[:, gidx[g]] *= ratio[:, None]
    # pi corresponde a la última r aplicada antes de la última corrección; recalculamos con la r final
    raw = core * r[:, :, None]
    pi = raw / raw.sum(axis=1, keepdims=True) * (1 - blank_rate)[:, None, :]

    # 4. votos con ruido final independiente (media 1)
    mu = valid[:, None, :] * pi
    log_mu = np.log(np.maximum(mu, 1e-9)) - 0.5 * sig_eps[None] ** 2
    eps = rng.standard_normal(size=(S, E, C)) * sig_eps[None]
    votes = np.rint(np.exp(log_mu + eps) * terr.contest[None]).astype(np.int64)
    blank = np.rint(valid * blank_rate).astype(np.int64)

    # 5. reparto legal por provincia
    seats = np.zeros((S, E, C), dtype=np.float32)
    elig_e = terr.seat_eligible
    for c in range(C):
        ents = np.flatnonzero(terr.contest[:, c] & elig_e)
        others_blank = blank[:, c] + votes[:, ~elig_e, c].sum(axis=1)
        seats[:, ents, c] = allocate_many(rules_for(terr, c), votes[:, ents, c], others_blank)
    return SimResult(terr, votes, blank, log_mu.astype(np.float32), sig_eps, seats, nat, err)
