import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from electoral_lab.legal.allocation import ConstituencyRules
from electoral_lab.pivotal.breakpoints import seat_steps, seats_bruteforce


@settings(max_examples=150, deadline=None)
@given(st.integers(1, 7), st.lists(st.integers(0, 400), min_size=1, max_size=5), st.integers(0, 60))
def test_steps_match_bruteforce(S, others, blank):
    rules = ConstituencyRules.congreso(S)
    others = np.array(others, dtype=np.int64)
    n_max = int(others.sum()) + 50
    steps = seat_steps(rules, others, blank, n_max)
    jumps = {s.n: 0.0 for s in steps}
    for s in steps:
        jumps[s.n] += s.jump
    prev = seats_bruteforce(rules, others, blank, 0)
    for n in range(1, n_max + 1):
        cur = seats_bruteforce(rules, others, blank, n)
        assert abs((cur - prev) - jumps.get(n, 0.0)) < 1e-9, (n, cur, prev, steps)
        prev = cur
