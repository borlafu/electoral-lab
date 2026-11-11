"""Rutas del proyecto. La raíz se toma de ELECTORAL_LAB_HOME o se busca hacia arriba desde el cwd."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    env = os.environ.get("ELECTORAL_LAB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = Path.cwd().resolve()
    for p in [here, *here.parents]:
        if (p / "pyproject.toml").exists() and (p / "configs").is_dir():
            return p
    # instalación editable: subir desde el paquete
    pkg = Path(__file__).resolve()
    for p in pkg.parents:
        if (p / "pyproject.toml").exists() and (p / "configs").is_dir():
            return p
    return here


ROOT = project_root()
CONFIGS = ROOT / "configs"
DATA = ROOT / "data"
RAW = DATA / "raw"
NORMALIZED = DATA / "normalized"
SEED = DATA / "seed"
MANUAL = DATA / "manual"
RUNS = DATA / "runs"
CATALOG_DB = DATA / "catalog.sqlite"


def ensure_dirs() -> None:
    for d in (RAW, NORMALIZED, RUNS, MANUAL):
        d.mkdir(parents=True, exist_ok=True)


def normalized_or_seed(name: str) -> Path:
    """Prefiere data/normalized/<name>; si no existe, la instantánea incluida en data/seed/."""
    p = NORMALIZED / name
    return p if p.exists() else SEED / name
