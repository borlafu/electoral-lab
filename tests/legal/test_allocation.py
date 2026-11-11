import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from electoral_lab.legal.allocation import ConstituencyRules, allocate, allocate_many, threshold_votes


def test_dhondt_textbook():
    # Ejemplo clásico del art. 163 LOREG (480.000 votos, 8 escaños)
    r = allocate(ConstituencyRules.congreso(8), [168000, 104000, 72000, 64000, 40000, 32000], 0)
    assert r.seats_int.tolist() == [4, 2, 1, 1, 0, 0]


def test_threshold_counts_blank_votes():
    rules = ConstituencyRules.congreso(5)
    # 2,9 % de válidos (incluidos blancos) -> excluida aunque su cociente diera escaño
    votes = [50000, 30000, 2900]
    blank = 100000 - sum(votes)
    r = allocate(rules, votes, blank)
    assert threshold_votes(100000, rules) == 3000
    assert not r.eligible[2]
    r2 = allocate(rules, [50000, 30000, 3000], blank - 100)
    assert r2.eligible[2]


def test_tie_on_quotient_goes_to_more_votes():
    # 'A' 300 (300/2=150) y 'B' 150: empatan en cociente 150 por el 2.º escaño; gana A (más votos)
    r = allocate(ConstituencyRules(seats=2, threshold_num=0), [300, 150], 0)
    assert r.seats_int.tolist() == [2, 0]


def test_full_tie_is_lottery_expected_seats():
    r = allocate(ConstituencyRules(seats=1, method="dhondt", threshold_num=0), [100, 100], 0)
    assert r.lottery and np.allclose(r.seats, [0.5, 0.5])


def test_ceuta_melilla_plurality():
    r = allocate(ConstituencyRules.congreso(1), [10, 30, 20], 5)
    assert r.seats.tolist() == [0, 1, 0]


@settings(max_examples=200, deadline=None)
@given(st.integers(2, 12), st.lists(st.integers(0, 50000), min_size=2, max_size=7), st.integers(0, 3000))
def test_allocate_many_matches_scalar(S, votes, blank):
    rules = ConstituencyRules.congreso(S)
    V = np.array([votes, votes[::-1]], dtype=np.int64)
    B = np.array([blank, blank])
    many = allocate_many(rules, V, B)
    for d in range(2):
        assert np.allclose(many[d], allocate(rules, V[d], int(B[d])).seats)


@settings(max_examples=100, deadline=None)
@given(st.integers(2, 10), st.lists(st.integers(1, 20000), min_size=2, max_size=6))
def test_seats_sum_and_monotonic(S, votes):
    rules = ConstituencyRules.congreso(S)
    r = allocate(rules, votes, 0)
    assert abs(r.seats.sum() - (S if r.eligible.any() else 0)) < 1e-9
    v2 = list(votes)
    v2[0] += 500
    assert allocate(rules, v2, 0).seats[0] >= r.seats[0] - 1e-9
