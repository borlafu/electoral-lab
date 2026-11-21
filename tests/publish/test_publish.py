import json

import numpy as np
import pytest
from typer.testing import CliRunner

from electoral_lab.cli.main import app
from electoral_lab.geography.catalog import provinces
from electoral_lab.publish import publish
from electoral_lab.storage import paths


@pytest.fixture
def root(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(paths, "PUBLISHED", tmp_path / "published" / "latest")
    return tmp_path


def test_publish_slims_and_packs(root, make_run):
    run = make_run(root, list(provinces()))
    res = publish(run)
    out = paths.PUBLISHED
    assert res.dest == out and res.provinces == 52
    assert (out / "pivotal.csv").exists() and (out / "manifest.json").exists()
    assert not list(out.glob("dist_next_*.npy"))
    with np.load(out / "sims.npz") as z:
        assert set(z.files) == {"seats_total", "entities", "national", "national_cols"}
        assert z["seats_total"].dtype == np.int16
    with np.load(out / "dist_next.npz") as z:
        assert sorted(z.files) == ["01_PP", "02_PP"]
        assert z["02_PP"][0] == 2
    meta = json.loads((out / "PUBLISHED.json").read_text())
    assert meta["run_id"] == run.name and meta["provinces_pivotal"] == 52
    assert not (out.parent / ".latest.tmp").exists()


def test_publish_rejects_partial_run_unless_allowed(root, make_run):
    run = make_run(root, ["29", "28"])
    with pytest.raises(ValueError, match="50 circunscripciones"):
        publish(run)
    assert publish(run, require_all=False).provinces == 2


def test_publish_replaces_previous_snapshot(root, make_run):
    paths.PUBLISHED.mkdir(parents=True)
    (paths.PUBLISHED / "stale.txt").write_text("x")
    publish(make_run(root, list(provinces())))
    assert not (paths.PUBLISHED / "stale.txt").exists()


def test_cli_publish_latest_and_partial_error(root, make_run):
    make_run(root, ["29"])
    r = CliRunner().invoke(app, ["publish"])
    assert r.exit_code == 1 and "51 circunscripciones" in r.output
    r = CliRunner().invoke(app, ["publish", "--partial"])
    assert r.exit_code == 0, r.output
    assert "Publicada 20261121T000000_test" in r.output
