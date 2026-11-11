"""Comprobaciones de datos y del motor legal."""

from __future__ import annotations

import numpy as np
import pandas as pd

from electoral_lab.ingestion.refresh import load_table
from electoral_lab.legal.allocation import ConstituencyRules, allocate


def reproduce_official(election: str) -> tuple[int, int, list[str]]:
    """Recalcula el reparto de cada provincia con el motor legal y lo compara con los escaños oficiales."""
    res = load_table("results")
    tot = load_table("totals").set_index(["election", "province"])
    r = res[res.election == election]
    bad = []
    n = 0
    for code, g in r.groupby("province"):
        S = int(g.seats.sum())
        blank = int(tot.loc[(election, code), "blank"])
        out = allocate(ConstituencyRules.congreso(S), g.votes.to_numpy(np.int64), blank)
        n += 1
        if not np.array_equal(out.seats_int, g.seats.to_numpy()):
            bad.append(code)
    return n, n - len(bad), bad


def run_all() -> list[tuple[str, bool, str]]:
    out = []
    seats = load_table("seats")
    out.append(("escaños 2026", len(seats) == 52 and seats.seats.sum() == 350,
                f"{len(seats)} circunscripciones, {seats.seats.sum()} escaños (RD 806/2026)"))
    censo = load_table("censo")
    out.append(("censo INE", len(censo) == 52, f"{censo.electors.sum():,} electores (CER + CERA)"))
    cand = load_table("candidacies")
    pc = cand[cand.proclaimed.astype(str).str.lower() == "true"].groupby("province").size()
    out.append(("candidaturas", len(pc) == 52 and pc.min() >= 3,
                f"{int(pc.sum())} candidaturas proclamadas en {len(pc)} circunscripciones"))
    polls = load_table("polls")
    last = pd.to_datetime(polls.fieldwork_end).max()
    out.append(("sondeos", len(polls) > 0, f"{polls.poll_id.nunique()} sondeos; último fin de campo {last.date()}"))
    tot = load_table("totals")
    res = load_table("results")
    for el in sorted(res.election.unique()):
        g = res[res.election == el].groupby("province").votes.sum()
        t = tot[tot.election == el].set_index("province")
        diff = (g + t.blank.reindex(g.index) - t.valid.reindex(g.index)).abs()
        out.append((f"cuadre de votos {el}", bool((diff <= 0.002 * t.valid.reindex(g.index)).all()),
                    f"máx. descuadre {int(diff.max())} votos"))
        n, ok, bad = reproduce_official(el)
        out.append((f"reparto oficial {el}", ok == n, f"{ok}/{n} provincias reproducidas" + (f"; fallan {bad}" if bad else "")))
    return out
