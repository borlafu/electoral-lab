import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from electoral_lab.storage import paths

APP = Path(__file__).resolve().parents[2] / "src/electoral_lab/ui/app.py"


@pytest.fixture
def ui(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    return AppTest.from_file(str(APP), default_timeout=15)


def test_no_implicit_selection_and_all_toggle(ui):
    ui.run()
    assert not ui.exception
    assert ui.multiselect[0].value == []
    assert ui.button[0].disabled
    assert len(ui.multiselect[0].options) == 52
    assert "A Coruña" in ui.multiselect[0].options
    ui.multiselect[0].set_value(["15"]).run()
    assert not ui.button[0].disabled
    ui.checkbox[0].check().run()
    assert ui.multiselect[0].disabled
    assert not ui.button[0].disabled
    ui.checkbox[0].uncheck().run()
    assert not ui.multiselect[0].disabled
    assert ui.multiselect[0].value == ["15"]
    ui.multiselect[0].set_value([]).run()
    assert ui.button[0].disabled


@pytest.mark.parametrize("all_provs", [False, True])
def test_subprocess_receives_atomic_codes_or_all(ui, monkeypatch, all_provs):
    run = Mock(side_effect=lambda args, **kwargs: CompletedProcess(args, 0, "Pipeline completado", ""))
    # app.py se ejecuta como script de Streamlit, no se importa para parchearlo.
    monkeypatch.setattr("subprocess.run", run)
    ui.run()
    ui.multiselect[0].set_value(["15", "13", "38"]).run()
    if all_provs:
        ui.checkbox[0].check().run()
    ui.button[0].click().run()
    assert not ui.exception
    run.assert_called_once()
    args = run.call_args.args[0]
    selection = args[args.index("run") + 1:args.index("--sims")]
    assert selection == (["--all"] if all_provs else ["15", "13", "38"])


def test_subprocess_failure_is_visible(ui, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda args, **kwargs: CompletedProcess(args, 1, "", "Fallo de prueba"))
    ui.run()
    ui.multiselect[0].set_value(["15"]).run()
    ui.button[0].click().run()
    assert not ui.exception
    assert "ha fallado" in ui.error[0].value


def test_results_use_dropdown_and_keep_compound_names(ui):
    # Ficheros de una ejecución anterior: no requiere migración del formato.
    out = paths.RUNS / "20261112_test"
    out.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({
        "run_id": out.name, "n_sims": 10, "seed": 1,
    }))
    pd.DataFrame(columns=["fieldwork_end"]).to_csv(out / "polls_used.csv", index=False)
    codes = ["15", "13", "28", "38"]
    names = ["A Coruña", "Ciudad Real", "Madrid", "Santa Cruz de Tenerife"]
    pd.DataFrame([
        dict(province=code, province_name=name, party="PP", E=0.00001, seats_mean=2.0,
             E_per_100k=1.0, one_in=100000.0, M1000=0.01, direct_M1000=0.01,
             median_votes_to_next=1000, top_displaced="PSOE")
        for code, name in zip(codes, names, strict=True)
    ]).to_csv(out / "pivotal.csv", index=False)
    pd.DataFrame([
        dict(province=code, province_name=name, seats_total=5, party="PP",
             mean=2.0, p05=1, p95=3, p_at_least_1=1.0)
        for code, name in zip(codes, names, strict=True)
    ]).to_csv(out / "seats_province.csv", index=False)
    pd.DataFrame([
        dict(province=code, party="PP", share_mean=0.4, share_p05=0.3, share_p95=0.5, p_over_3pct=1.0)
        for code in codes
    ]).to_csv(out / "votes_province.csv", index=False)
    ui.run()
    assert not ui.exception
    assert len(ui.radio) == 0
    dropdown = next(s for s in ui.selectbox if s.label == "Circunscripción")
    assert dropdown.options == names
    for code in codes:
        dropdown.set_value(code).run()
        assert not ui.exception
        dropdown = next(s for s in ui.selectbox if s.label == "Circunscripción")
        assert dropdown.value == code
    province = next(s for s in ui.selectbox if s.label == "Provincia")
    assert province.value == "15"  # sin valor predeterminado fijo para Málaga
