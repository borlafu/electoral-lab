from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from electoral_lab.cli import main
from electoral_lab.geography.catalog import provinces

runner = CliRunner()


@pytest.fixture
def pipeline(monkeypatch):
    from electoral_lab import pipeline

    run = Mock(return_value=Path("unused"))
    monkeypatch.setattr(pipeline, "run", run)
    monkeypatch.setattr(main, "_print_report", Mock())
    return run


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "Indica al menos una circunscripción"),
        (["--all", "Madrid"], "no ambos"),
        (["Madrid", "--all"], "no ambos"),
        (["Atlantis"], "No reconozco"),
    ],
)
def test_invalid_selection_does_not_run(args, message, pipeline):
    result = runner.invoke(main.app, ["run", *args], color=False)
    assert result.exit_code == 2
    assert message in result.output
    pipeline.assert_not_called()


def test_all_includes_every_constituency(pipeline):
    result = runner.invoke(main.app, ["run", "--all", "--sims", "10", "--pivotal-sims", "2"])
    assert result.exit_code == 0, result.output
    codes = pipeline.call_args.args[0]
    assert codes == list(provinces())
    assert len(codes) == 52
    assert {"51", "52"} <= set(codes)
    assert pipeline.call_args.kwargs["n_sims"] == 10
    assert pipeline.call_args.kwargs["pivotal_sims"] == 2


def test_explicit_names_codes_and_aliases_preserve_order_without_duplicates(pipeline):
    result = runner.invoke(main.app, [
        "run", "A Coruña", "Ciudad Real", "Santa Cruz de Tenerife", "Bilbao", "Bizkaia", "15", "Madrid",
        "--set", "territorial.sigma_scale=0.7", "--seed", "123",
    ])
    assert result.exit_code == 0, result.output
    assert pipeline.call_args.args[0] == ["15", "13", "38", "48", "28"]
    assert pipeline.call_args.args[1]["territorial"]["sigma_scale"] == 0.7
    assert pipeline.call_args.kwargs["seed"] == 123


def test_help_documents_both_modes():
    result = runner.invoke(main.app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--all" in result.output
    assert "52" in result.output
    assert "circunscripciones" in result.output
