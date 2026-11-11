"""Agregador nacional de sondeos: paseo aleatorio en escala logit con efectos de casa (filtro de Kalman).

Para cada entidad nacional g y cada sondeo i (encuestadora k, fin de campo t_i):

    y_i = logit(v_i)                 v_i = estimación publicada (proporción sobre voto válido)
    y_i = x_g(t_i) + h_{g,k} + e_i,  e_i ~ N(0, 1/(n_eff v_i (1-v_i)) + tau_g^2)
    x_g(t+d) = x_g(t) + N(0, q_g d)  (q_g = rw_sd_daily^2)
    h_{g,k} ~ N(0, house_sd_g^2)     (efecto de casa fijo de cada encuestadora)

El estado es [x, h_1..h_K]; el filtro de Kalman da la verosimilitud marginal exacta, que se
maximiza en (rw_sd_daily, tau, house_sd) dentro de los límites de configuración. La predicción
para el día de la elección añade la difusión hasta esa fecha y un error sistemático del día E
(con un factor de bloque izquierda/derecha común) — los sondeos no son insesgados en promedio.

Supuesto de identificación: el efecto de casa medio, ponderado por precisión, es cero; es decir,
el conjunto de encuestadoras no está sesgado en bloque. El error del día E cubre ese riesgo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

from electoral_lab.party_registry.registry import Registry


@dataclass
class PartyFit:
    group: str
    n_obs: int
    rw_sd_daily: float
    tau: float
    house_sd: float
    loglik: float
    last_date: date
    mean_logit_E: float  # predicción en el día E (sin error sistemático)
    var_logit_E: float
    mean_now: float  # estimación en la fecha del último sondeo (proporción)
    house: dict[str, float] = field(default_factory=dict)
    trend: pd.DataFrame | None = None  # serie filtrada (fecha, media, sd) en proporción


@dataclass
class NationalFit:
    parties: dict[str, PartyFit]
    election_date: date
    blocs: dict[str, str]
    cfg: dict
    polls_used: pd.DataFrame

    def summary(self) -> pd.DataFrame:
        rows = []
        for g, f in self.parties.items():
            sd = np.sqrt(f.var_logit_E)
            rows.append(dict(group=g, n_obs=f.n_obs, now=f.mean_now, E_mean=expit(f.mean_logit_E),
                             E_lo=expit(f.mean_logit_E - 1.645 * sd), E_hi=expit(f.mean_logit_E + 1.645 * sd),
                             rw_sd_daily=f.rw_sd_daily, tau=f.tau, house_sd=f.house_sd))
        return pd.DataFrame(rows).sort_values("E_mean", ascending=False)


# ------------------------------------------------------------------ preparación de sondeos
def prepare_polls(polls: pd.DataFrame, reg: Registry, cfg: dict) -> pd.DataFrame:
    """Sondeos en formato ancho por entidad nacional (proporciones), con n_eff."""
    df = polls.copy()
    df["fieldwork_end"] = pd.to_datetime(df["fieldwork_end"])
    df["fieldwork_start"] = pd.to_datetime(df["fieldwork_start"])
    df = df[df["fieldwork_end"] >= pd.Timestamp(cfg["window_start"])]
    df = df[df["measure_type"] == "vote_estimate"]
    df = df[~df["pollster"].isin(cfg.get("exclude_pollsters", []))]
    keys = ["poll_id", "pollster", "fieldwork_start", "fieldwork_end", "sample_size"]
    vals = df.pivot_table(index="poll_id", columns="party_id", values="reported_value", aggfunc="first")
    meta = df.drop_duplicates("poll_id").set_index("poll_id")[keys[1:]]
    wide = meta.join(vals).reset_index()
    merged = df[df.merged_with.notna()].groupby("poll_id").merged_with.apply(lambda s: "+".join(s)).to_dict()
    wide = wide.dropna(subset=["fieldwork_end"])
    wide["merged"] = wide.poll_id.map(merged).fillna("")
    # FA_FV: Sumar (tablas antiguas) o FA + FV; si FV no se publica por separado se imputa su mediana reciente.
    fv_recent = wide.loc[wide.fieldwork_end >= wide.fieldwork_end.max() - pd.Timedelta(days=90), "FV"] if "FV" in wide else []
    fv_imp = float(np.nanmedian(fv_recent)) if len(fv_recent) and np.isfinite(np.nanmedian(fv_recent)) else 1.0
    fa = wide.get("FA", pd.Series(np.nan, index=wide.index))
    fv = wide.get("FV", pd.Series(np.nan, index=wide.index))
    su = wide.get("SUMAR", pd.Series(np.nan, index=wide.index))
    fv_eff = np.where(fv.notna(), fv, np.where(wide.merged.str.contains("FV"), 0.0, fv_imp))
    wide["FA_FV"] = np.where(su.notna(), su, np.where(fa.notna(), fa + fv_eff, np.nan))
    wide["FA_FV_imputed"] = su.isna() & fa.notna() & fv.isna() & ~wide.merged.str.contains("FV")
    groups = reg.national_groups_ids
    for g in groups:
        if g not in wide:
            wide[g] = np.nan
    # tamaño efectivo
    n = wide["sample_size"].astype(float)
    med = n.groupby(wide.pollster).transform("median")
    n = n.fillna(med).fillna(cfg["default_n"])
    wide["n_eff"] = np.minimum(n, cfg["n_cap"]) * cfg["design_effect"]
    if cfg.get("dedupe_tracking", True):
        keep = []
        for _, g in wide.sort_values("fieldwork_end", ascending=False).groupby("pollster", sort=False):
            last_start = None
            for idx, r in g.iterrows():
                if last_start is None or r.fieldwork_end < last_start:
                    keep.append(idx)
                    last_start = r.fieldwork_start if pd.notna(r.fieldwork_start) else r.fieldwork_end
        wide = wide.loc[sorted(keep)]
    wide = wide.sort_values("fieldwork_end").reset_index(drop=True)
    return wide[["poll_id", "pollster", "fieldwork_start", "fieldwork_end", "sample_size", "n_eff", "FA_FV_imputed",
                 *groups]]


# ------------------------------------------------------------------ filtro de Kalman
def _kalman(t: np.ndarray, k: np.ndarray, y: np.ndarray, r0: np.ndarray, K: int, q: float, tau: float,
            hsd: float, x0: float, keep_path: bool = False):
    dim = 1 + K
    m = np.zeros(dim)
    m[0] = x0
    P = np.zeros((dim, dim))
    P[0, 0] = 1.0
    P[np.arange(1, dim), np.arange(1, dim)] = hsd**2
    ll = 0.0
    prev = t[0]
    path = []
    for i in range(len(y)):
        dt = t[i] - prev
        prev = t[i]
        P[0, 0] += q * dt
        j = 1 + k[i]
        # H = e_0 + e_j
        S = P[0, 0] + P[j, j] + 2 * P[0, j] + r0[i] + tau**2
        v = y[i] - (m[0] + m[j])
        PH = P[:, 0] + P[:, j]
        G = PH / S
        m = m + G * v
        P = P - np.outer(G, PH)
        ll += -0.5 * (np.log(2 * np.pi * S) + v * v / S)
        if keep_path:
            path.append((t[i], m[0], P[0, 0]))
    return ll, m, P, path


def fit_party(obs: pd.DataFrame, group: str, cfg: dict, election_date: date) -> PartyFit:
    t0 = obs.fieldwork_end.min()
    t = ((obs.fieldwork_end - t0).dt.days).to_numpy(float)
    pollsters = sorted(obs.pollster.unique())
    kidx = {p: i for i, p in enumerate(pollsters)}
    k = obs.pollster.map(kidx).to_numpy()
    v = np.clip(obs[group].to_numpy(float) / 100.0, 1e-4, 0.999)
    y = logit(v)
    # varianza de muestreo + redondeo de la publicación a 0,1 pp (uniforme: sd = 0,05/sqrt(3) pp)
    r0 = 1.0 / (obs.n_eff.to_numpy(float) * v * (1 - v)) + (0.0005 / np.sqrt(3) / (v * (1 - v))) ** 2
    x0 = float(np.mean(y[: min(5, len(y))]))
    b = cfg["bounds"]

    def unpack(z):
        lo = np.array([b["rw_sd_daily"][0], b["tau"][0], b["house_sd"][0]])
        hi = np.array([b["rw_sd_daily"][1], b["tau"][1], b["house_sd"][1]])
        return lo + (hi - lo) * expit(z)

    def nll(z):
        rw, tau, hsd = unpack(z)
        return -_kalman(t, k, y, r0, len(pollsters), rw**2, tau, hsd, x0)[0]

    best = minimize(nll, np.zeros(3), method="Nelder-Mead", options=dict(maxiter=400, xatol=1e-3, fatol=1e-4,
                                 initial_simplex=np.vstack([np.full(3, -1.0), np.eye(3) * 2.5 - 1.0])))
    rw, tau, hsd = unpack(best.x)
    ll, m, P, path = _kalman(t, k, y, r0, len(pollsters), rw**2, tau, hsd, x0, keep_path=True)
    last = obs.fieldwork_end.max().date()
    days = max((election_date - last).days, 0)
    trend = pd.DataFrame(path, columns=["day", "mean", "var"])
    trend["date"] = t0 + pd.to_timedelta(trend.day, unit="D")
    trend["share"] = expit(trend["mean"])
    trend["lo"] = expit(trend["mean"] - 1.645 * np.sqrt(trend["var"]))
    trend["hi"] = expit(trend["mean"] + 1.645 * np.sqrt(trend["var"]))
    return PartyFit(
        group=group, n_obs=len(y), rw_sd_daily=float(rw), tau=float(tau), house_sd=float(hsd), loglik=float(ll),
        last_date=last, mean_logit_E=float(m[0]), var_logit_E=float(P[0, 0] + rw**2 * days),
        mean_now=float(expit(m[0])), house={p: float(m[1 + i]) for p, i in kidx.items()},
        trend=trend[["date", "share", "lo", "hi"]],
    )


def fit(polls: pd.DataFrame, reg: Registry, cfg_all: dict) -> NationalFit:
    cfg = cfg_all["national"]
    edate = pd.Timestamp(cfg_all["election_date"]).date()
    wide = prepare_polls(polls, reg, cfg)
    out = {}
    for g in reg.national_groups_ids:
        obs = wide[wide[g].notna() & (wide[g] > 0)][["pollster", "fieldwork_end", "n_eff", g]]
        if len(obs) < cfg["min_obs_party"]:
            continue
        out[g] = fit_party(obs, g, cfg, edate)
    blocs = {}
    for pid, p in reg.parties.items():
        blocs[reg.group(pid)] = p.bloc
    return NationalFit(out, edate, blocs, cfg, wide)


# ------------------------------------------------------------------ simulación nacional
def sample(nf: NationalFit, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Muestras de cuotas nacionales sobre voto válido (columnas = entidades + OTROS_BLANCO)."""
    cfg = nf.cfg
    groups = list(nf.parties)
    bloc_f = rng.normal(0, cfg["bloc_sd"], size=n)
    cols = {}
    for g in groups:
        f = nf.parties[g]
        small = expit(f.mean_logit_E) < 0.04
        sd_sys = cfg["election_day_sd_small"] if small else cfg["election_day_sd"]
        x = rng.normal(f.mean_logit_E, np.sqrt(f.var_logit_E + sd_sys**2), size=n)
        sign = {"left": 1.0, "right": -1.0}.get(nf.blocs.get(g, ""), 0.0)
        cols[g] = expit(x + sign * bloc_f)
    df = pd.DataFrame(cols)
    tot = df.sum(axis=1)
    resid = 1.0 - tot
    floor = cfg["others_min"]
    scale = np.where(resid < floor, (1 - floor) / tot, 1.0)
    df = df.mul(scale, axis=0)
    df["OTROS_BLANCO"] = 1.0 - df.sum(axis=1)
    return df
