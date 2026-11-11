"""El motor legal debe reproducir los escaños oficiales de cada provincia (datos semilla)."""
import pytest

from electoral_lab.validation.checks import reproduce_official


@pytest.mark.parametrize("election", ["congreso_2023", "congreso_2019n"])
def test_reproduces_official_seats(election):
    n, ok, bad = reproduce_official(election)
    assert n == 52 and ok == 52, bad
