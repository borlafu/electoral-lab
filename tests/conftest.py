"""Utilidades compartidas por los tests."""

import json

import numpy as np
import pandas as pd
import pytest


def _make_run(root, codes):
    d = root / "runs" / "20261121T000000_test"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "run_id": d.name, "n_sims": 100, "seed": 1, "last_poll": "2026-11-20", "n_polls": 3,
        "provinces_pivotal": codes,
    }))
    from electoral_lab.geography.catalog import provinces

    names = {c: provinces()[c].name for c in codes}
    pd.DataFrame([dict(province=c, province_name=names[c], party="PP", seats_mean=2.0, E=1e-5, se=1e-7,
                       one_in=1e5, E_per_100k=1.0, M10=1e-4, M100=1e-3, M1000=1e-2, direct_M1000=1e-2,
                       median_votes_to_next=1000.0, top_displaced="PSOE") for c in codes]
                 ).to_csv(d / "pivotal.csv", index=False)
    pd.DataFrame([dict(province=c, province_name=names[c], seats_total=5, party="PP", mean=2.0, p05=1, p95=3,
                       p_at_least_1=1.0) for c in codes]).to_csv(d / "seats_province.csv", index=False)
    pd.DataFrame([dict(province=c, party="PP", share_mean=0.4, share_p05=0.3, share_p95=0.5, p_over_3pct=1.0)
                  for c in codes]).to_csv(d / "votes_province.csv", index=False)
    pd.DataFrame([dict(party="PP", mean=2.0, p05=2, p50=2, p95=2, p_largest=1.0)]
                 ).to_csv(d / "seats_national.csv", index=False)
    pd.DataFrame(columns=["fieldwork_end"]).to_csv(d / "polls_used.csv", index=False)
    (d / "pivotal_detail.json").write_text("{}")
    np.savez_compressed(
        d / "sims.npz", seats_total=np.full((100, 3), 2.0, np.float32), entities=np.array(["PP", "PSOE", "VOX"]),
        seats_sel=np.zeros((100, 3, len(codes)), np.float32), votes_sel=np.zeros((100, 3, len(codes)), np.int32),
        national=np.full((100, 2), 0.3, np.float32), national_cols=np.array(["PP", "PSOE"]),
    )
    for c in codes[:2]:
        np.save(d / f"dist_next_{c}_PP.npy", np.arange(10, dtype=np.float32) + int(c))
    return d


@pytest.fixture
def make_run():
    """Crea una ejecución mínima en <root>/runs con E_p,c para los códigos indicados."""
    return _make_run
