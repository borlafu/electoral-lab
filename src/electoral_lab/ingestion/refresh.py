"""Orquestación de la actualización de fuentes -> tablas normalizadas (data/normalized/*.csv).

Cada fuente se descarga, se archiva en bruto (data/raw) y se normaliza. Si una fuente falla, se
conserva la última tabla normalizada (o la semilla incluida en data/seed) y se informa del fallo.
"""

from __future__ import annotations

import json
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from electoral_lab.ingestion import ep2024, official, polls_wikipedia, results_wikipedia
from electoral_lab.party_registry.registry import Registry
from electoral_lab.storage import paths

TABLES = {
    "seats": "constituencies_2026.csv",
    "censo": "censo_2026.csv",
    "candidacies": "candidacies_2026.csv",
    "polls": "polls_national.csv",
    "results": "results_congreso.csv",
    "totals": "totals_congreso.csv",
    "ep2024": "ep2024_profile.csv",
}


@dataclass
class SourceStatus:
    name: str
    ok: bool
    rows: int = 0
    message: str = ""


def _write(df: pd.DataFrame, key: str) -> Path:
    paths.NORMALIZED.mkdir(parents=True, exist_ok=True)
    p = paths.NORMALIZED / TABLES[key]
    df.to_csv(p, index=False)
    return p


def refresh(only: list[str] | None = None, offline_results: bool = True) -> list[SourceStatus]:
    reg = Registry.load()
    jobs = {
        "seats": lambda: official.fetch_convocatoria(),
        "censo": lambda: official.fetch_censo(),
        "candidacies": lambda: official.fetch_candidaturas(reg),
        "polls": lambda: polls_wikipedia.parse_tables(
            json.loads(polls_wikipedia.fetch_wikitext().read_text())["parse"]["wikitext"], reg),
        "results": None,  # se hace junto con totals
        "ep2024": lambda: ep2024.load(ep2024.fetch()),
    }
    out = []
    for key, job in jobs.items():
        if only and key not in only and not (key == "results" and "totals" in only):
            continue
        try:
            if key == "results":
                res, tot = results_wikipedia.collect(offline=offline_results)
                _write(res, "results")
                _write(tot, "totals")
                out.append(SourceStatus("results+totals", True, len(res)))
                continue
            df = job()
            _write(df, key)
            out.append(SourceStatus(key, True, len(df)))
        except Exception as e:  # noqa: BLE001 - se informa y se sigue con la última versión
            out.append(SourceStatus(key, False, 0, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
    return out


def promote_to_seed() -> list[Path]:
    """Copia las tablas normalizadas actuales a data/seed (instantánea versionada en git)."""
    paths.SEED.mkdir(parents=True, exist_ok=True)
    done = []
    for name in TABLES.values():
        src = paths.NORMALIZED / name
        if src.exists():
            shutil.copy2(src, paths.SEED / name)
            done.append(paths.SEED / name)
    return done


def load_table(key: str) -> pd.DataFrame:
    p = paths.normalized_or_seed(TABLES[key])
    if not p.exists():
        raise FileNotFoundError(f"No hay datos para '{key}'. Ejecuta: electoral sources refresh")
    return pd.read_csv(p, dtype={"province": str})
