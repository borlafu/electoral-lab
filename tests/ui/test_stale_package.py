"""Regresión: Streamlit Cloud puede tener en site-packages una copia antigua de electoral_lab.

app.py debe importar siempre el paquete del mismo checkout (src/), no la copia instalada.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "src" / "electoral_lab" / "ui" / "app.py"


def test_app_ignores_stale_installed_package(tmp_path):
    stale = tmp_path / "stale" / "electoral_lab"
    (stale / "storage").mkdir(parents=True)
    (stale / "__init__.py").write_text("")
    (stale / "storage" / "__init__.py").write_text("")
    (stale / "storage" / "paths.py").write_text("ROOT = None  # copia antigua sin PUBLISHED\n")
    script = textwrap.dedent(f"""
        import electoral_lab.storage.paths as p
        assert not hasattr(p, "PUBLISHED")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file({str(APP)!r}, default_timeout=60).run()
        errs = [e.message for e in at.exception]
        assert not errs, errs
        print("OK")
    """)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "stale"), "ELECTORAL_LAB_READONLY": "1",
           "ELECTORAL_LAB_BLACKOUT": "off"}
    res = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    assert "OK" in res.stdout
