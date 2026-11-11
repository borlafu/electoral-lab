"""El estimador condicional coincide con la enumeración exacta en un caso pequeño."""
import numpy as np
from scipy.special import ndtr

from electoral_lab.legal.allocation import ConstituencyRules
from electoral_lab.models.territorial import Territory
from electoral_lab.pivotal.breakpoints import seats_bruteforce
from electoral_lab.pivotal.estimator import estimate
from electoral_lab.simulation.engine import SimResult


def _toy(S_sims=3):
    E, C = 3, 1
    terr = Territory(prov=["29"], names=["Toy"], ccaa=np.array([0]), seats=np.array([3]),
                     electors=np.array([1000.0]), turnout_base=np.array([0.7]), null_rate=np.array([0.0]),
                     blank_rate=np.array([0.0]), entities=["A", "B", "OTROS"], groups=["A", "B", "OTROS_BLANCO"],
                     contest=np.ones((E, C), bool), base=np.ones((E, C)) / 3, sigma=np.full((E, C), 0.2),
                     seat_eligible=np.array([True, True, False]), phi_podemos=np.zeros(1))
    rng = np.random.default_rng(1)
    votes = np.zeros((S_sims, E, C), np.int64)
    votes[:, 0, 0] = [240, 255, 230]
    votes[:, 1, 0] = rng.integers(110, 140, S_sims)
    votes[:, 2, 0] = 9
    blank = np.full((S_sims, C), 3, np.int64)
    log_mu = np.log(np.maximum(votes, 1)).astype(np.float32)
    sig = np.full((E, C), 0.05)
    seats = np.zeros((S_sims, E, C), np.float32)
    for s in range(S_sims):
        seats[s, 0, 0] = seats_bruteforce(ConstituencyRules.congreso(3), votes[s, [1], 0], 12, int(votes[s, 0, 0]))
    return SimResult(terr, votes, blank, log_mu, sig, seats, None, 0.0)


def test_rb_equals_enumeration():
    sim = _toy()
    r = estimate(sim, 0, "A", increments=(1, 10), direct_k=10)
    rules = ConstituencyRules.congreso(3)
    exact = []
    for s in range(sim.n):
        mu, sd = float(sim.log_mu[s, 0, 0]), 0.05
        others = sim.votes[s, [1], 0]
        blank = int(sim.blank[s, 0] + sim.votes[s, 2, 0])
        tot = 0.0
        for m in range(1, 1000):
            pm = ndtr((np.log(m + 0.5) - mu) / sd) - ndtr((np.log(m - 0.5) - mu) / sd)
            if pm < 1e-15:
                continue
            tot += pm * (seats_bruteforce(rules, others, blank, m + 1) - seats_bruteforce(rules, others, blank, m))
        exact.append(tot)
    assert abs(r.E - np.mean(exact)) < 1e-6
