import numpy as np
import pandas as pd
from scipy.special import expit

from electoral_lab.models.national import fit_party


def test_kalman_recovers_level_and_house_effects():
    rng = np.random.default_rng(0)
    days = pd.date_range("2026-01-01", periods=300, freq="D")
    truth = expit(-1.0 + np.cumsum(rng.normal(0, 0.004, len(days))))
    house = {"A": 0.08, "B": -0.08, "C": 0.0}
    rows = []
    for i in range(0, 300, 3):
        k = "ABC"[(i // 3) % 3]
        p = expit(np.log(truth[i] / (1 - truth[i])) + house[k])
        rows.append(dict(pollster=k, fieldwork_end=days[i], n_eff=1000, X=100 * rng.binomial(1000, p) / 1000))
    obs = pd.DataFrame(rows)
    cfg = dict(bounds=dict(rw_sd_daily=[0.001, 0.03], tau=[0.0, 0.2], house_sd=[0.01, 0.3]))
    f = fit_party(obs, "X", cfg, days[-1].date())
    assert abs(f.mean_now - truth[-1]) < 0.02
    assert f.house["A"] > f.house["C"] > f.house["B"]
