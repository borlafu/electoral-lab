"""Ejecución reproducible de punta a punta: datos -> modelo nacional -> territorial -> simulación -> E_{p,c}.

Cada ejecución crea data/runs/<run_id>/ con:
  manifest.json          configuración, hashes de datos y configuración, commit git, semilla
  national_summary.csv   estimación nacional por entidad (hoy y día E, intervalos 90 %)
  national_trend.csv     series filtradas
  house_effects.csv      efectos de casa estimados
  seats_national.csv     distribución de escaños totales (media, percentiles, P(mayor grupo))
  seats_province.csv     escaños medios y percentiles por provincia y candidatura
  votes_province.csv     cuota media y percentiles por provincia y candidatura
  pivotal.csv            E_{p,c}, M(k), contraste directo, desplazados... para las provincias pedidas
  sims.npz               escaños por simulación (totales y de las provincias pedidas) para la interfaz
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from electoral_lab.ingestion.refresh import TABLES, load_table
from electoral_lab.models import national, territorial
from electoral_lab.party_registry.registry import Registry
from electoral_lab.pivotal.estimator import estimate_province, to_frame
from electoral_lab.simulation.engine import simulate
from electoral_lab.storage import catalog, paths


def load_config(path: Path | None = None, overrides: dict | None = None) -> dict:
    path = path or paths.CONFIGS / "models" / "default.yaml"
    cfg = yaml.safe_load(Path(path).read_text())
    for k, v in (overrides or {}).items():
        d = cfg
        parts = k.split(".")
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = v
    return cfg


def _hash_files(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in sorted(files):
        if f.exists():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(paths.ROOT), "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def load_tables() -> dict[str, pd.DataFrame]:
    return {k: load_table(k) for k in TABLES}


def run(provinces_pivotal: list[str], cfg: dict | None = None, n_sims: int | None = None,
        pivotal_sims: int = 4000, seed: int | None = None, log=print) -> Path:
    cfg = cfg or load_config()
    seed = int(seed if seed is not None else cfg["seed"])
    n_sims = int(n_sims or cfg["n_sims"])
    reg = Registry.load()
    tabs = load_tables()
    data_files = [paths.normalized_or_seed(n) for n in TABLES.values()]
    data_hash = _hash_files(data_files)
    cfg_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + f"_{data_hash[:6]}_{seed}"
    out = paths.RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    log("Ajustando el agregador nacional de sondeos…")
    nf = national.fit(tabs["polls"], reg, cfg)
    nf.summary().to_csv(out / "national_summary.csv", index=False)
    pd.concat([f.trend.assign(group=g) for g, f in nf.parties.items()]).to_csv(out / "national_trend.csv", index=False)
    pd.DataFrame([dict(group=g, pollster=k, house_logit=v) for g, f in nf.parties.items() for k, v in f.house.items()]
                 ).to_csv(out / "house_effects.csv", index=False)
    nf.polls_used.to_csv(out / "polls_used.csv", index=False)

    log("Construyendo el modelo territorial…")
    terr = territorial.build(tabs, reg, cfg)
    log(f"  {terr.sigma_model.notes}")

    log(f"Simulando {n_sims} escenarios…")
    chunks = []
    nat_all = national.sample(nf, n_sims, rng)
    step = 5000
    for i in range(0, n_sims, step):
        chunks.append(simulate(terr, nat_all.iloc[i:i + step].reset_index(drop=True), cfg, rng))
    sim = chunks[0]
    if len(chunks) > 1:
        from electoral_lab.simulation.engine import SimResult

        sim = SimResult(terr, np.concatenate([c.votes for c in chunks]), np.concatenate([c.blank for c in chunks]),
                        np.concatenate([c.log_mu for c in chunks]), chunks[0].sigma_eps,
                        np.concatenate([c.seats for c in chunks]), nat_all, max(c.calib_error for c in chunks))
    log(f"  error máximo de calibración nacional: {sim.calib_error:.5f}")

    st = sim.seats_total()
    q = st.quantile([0.05, 0.5, 0.95]).T
    largest = st.drop(columns=["OTROS"], errors="ignore").idxmax(axis=1).value_counts(normalize=True)
    seats_nat = pd.DataFrame({"mean": st.mean(), "p05": q[0.05], "p50": q[0.5], "p95": q[0.95],
                              "p_largest": largest.reindex(st.columns).fillna(0)})
    seats_nat.index.name = "party"
    seats_nat.reset_index().to_csv(out / "seats_national.csv", index=False)
    blocs = {p: reg.parties[p].bloc if p in reg.parties else "other" for p in st.columns}
    right = st[[p for p in st.columns if blocs[p] == "right"]].sum(axis=1)
    left = st[[p for p in st.columns if blocs[p] == "left"]].sum(axis=1)
    bloc_summary = dict(p_right_majority=float((right >= 176).mean()), p_left_majority=float((left >= 176).mean()),
                        right_mean=float(right.mean()), left_mean=float(left.mean()))

    rows_s, rows_v = [], []
    for c, code in enumerate(terr.prov):
        valid = sim.votes[:, :, c].sum(1) + sim.blank[:, c]
        for e, ent in enumerate(terr.entities):
            if not terr.contest[e, c]:
                continue
            s = sim.seats[:, e, c]
            sh = sim.votes[:, e, c] / valid
            rows_s.append(dict(province=code, province_name=terr.names[c], seats_total=int(terr.seats[c]), party=ent,
                               mean=float(s.mean()), p05=float(np.quantile(s, .05)), p95=float(np.quantile(s, .95)),
                               p_at_least_1=float((s >= 1).mean())))
            rows_v.append(dict(province=code, party=ent, share_mean=float(sh.mean()),
                               share_p05=float(np.quantile(sh, .05)), share_p95=float(np.quantile(sh, .95)),
                               p_over_3pct=float((sh >= 0.03).mean())))
    pd.DataFrame(rows_s).to_csv(out / "seats_province.csv", index=False)
    pd.DataFrame(rows_v).to_csv(out / "votes_province.csv", index=False)

    piv_frames, extra = [], {}
    for code in provinces_pivotal:
        log(f"Estimando E_p,c en {terr.names[terr.index(code)]}…")
        res = estimate_province(sim, code, max_sims=pivotal_sims, increments=cfg["pivotal"]["increments"])
        piv_frames.append(to_frame(res, terr))
        for r in res:
            extra[f"{code}_{r.party}"] = dict(displaced=r.displaced, causes=r.causes,
                                              increments=r.increments, increments_se=r.increments_se)
            np.save(out / f"dist_next_{code}_{r.party}.npy", r.dist_next_seat.astype(np.float32))
    if piv_frames:
        pd.concat(piv_frames).to_csv(out / "pivotal.csv", index=False)
    (out / "pivotal_detail.json").write_text(json.dumps(extra, ensure_ascii=False, indent=1))

    sel = [terr.index(c) for c in provinces_pivotal]
    np.savez_compressed(out / "sims.npz", seats_total=st.to_numpy(np.float32), entities=np.array([str(e) for e in terr.entities]),
                        prov_sel=np.array(provinces_pivotal), seats_sel=sim.seats[:, :, sel],
                        votes_sel=sim.votes[:, :, sel].astype(np.int32), blank_sel=sim.blank[:, sel].astype(np.int32),
                        national=sim.national.to_numpy(np.float32), national_cols=np.array([str(c) for c in sim.national.columns]))

    manifest = dict(
        run_id=run_id, created_at=catalog.now_iso(), seed=seed, n_sims=n_sims, pivotal_sims=pivotal_sims,
        provinces_pivotal=provinces_pivotal, data_hash=data_hash, config_hash=cfg_hash, git_commit=_git_commit(),
        data_files={p.name: str(p.relative_to(paths.ROOT)) for p in data_files if p.exists()},
        sigma_model=asdict(terr.sigma_model), calib_error=sim.calib_error, bloc_summary=bloc_summary,
        last_poll=str(nf.polls_used.fieldwork_end.max().date()), n_polls=int(len(nf.polls_used)), config=cfg,
    )
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str))
    catalog.record_run(run_id, None, "full", "ok", manifest)
    log(f"Ejecución guardada en {out.relative_to(paths.ROOT)}")
    return out


def latest_run() -> Path | None:
    if not paths.RUNS.exists():
        return None
    runs = sorted(p for p in paths.RUNS.iterdir() if (p / "manifest.json").exists())
    return runs[-1] if runs else None
