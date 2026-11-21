"""Exporta una ejecución a una instantánea ligera que la app publicada carga sin calcular nada.

La carpeta de una ejecución completa (`data/runs/<run_id>/`) ocupa ~35 MB, casi todo en `sims.npz`
(votos y escaños provinciales por escenario, que la interfaz no usa). La instantánea publicada conserva
solo lo que muestra la app:

  * todos los CSV y JSON de la ejecución (sin cambios);
  * `sims.npz` reducido: escaños nacionales por escenario (int16) y cuotas nacionales simuladas;
  * `dist_next.npz`: los `dist_next_<prov>_<partido>.npy` empaquetados en un solo fichero comprimido;
  * `PUBLISHED.json`: metadatos de la publicación (ejecución de origen, fecha, commit, tamaño).

La escritura es atómica: se genera en una carpeta temporal y se sustituye la anterior al final.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from electoral_lab.storage import paths

TABLES = [
    "manifest.json", "national_summary.csv", "national_trend.csv", "house_effects.csv", "seats_national.csv",
    "seats_province.csv", "votes_province.csv", "pivotal.csv", "pivotal_detail.json", "polls_used.csv",
]
REQUIRED = ["manifest.json", "seats_national.csv", "seats_province.csv", "votes_province.csv"]


@dataclass
class PublishResult:
    dest: Path
    run_id: str
    provinces: int
    size_bytes: int


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=paths.ROOT,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _dir_size(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def publish(run_dir: Path, dest: Path | None = None, require_all: bool = True) -> PublishResult:
    """Copia la ejecución `run_dir` a `dest` (por defecto data/published/latest) en formato ligero."""
    run_dir = Path(run_dir)
    dest = Path(dest) if dest else paths.PUBLISHED
    missing = [n for n in REQUIRED if not (run_dir / n).exists()]
    if missing:
        raise FileNotFoundError(f"La ejecución {run_dir} no tiene: {', '.join(missing)}")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    provs = list(manifest.get("provinces_pivotal") or [])
    if require_all:
        from electoral_lab.geography.catalog import provinces

        faltan = sorted(set(provinces()) - set(provs))
        if faltan:
            raise ValueError(
                f"La ejecución no calcula E_p,c en {len(faltan)} circunscripciones ({', '.join(faltan[:5])}…). "
                "Genera una con `electoral run --all` o usa --partial."
            )

    tmp = dest.parent / f".{dest.name}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    for name in TABLES:
        if (run_dir / name).exists():
            shutil.copy2(run_dir / name, tmp / name)

    if (run_dir / "sims.npz").exists():
        with np.load(run_dir / "sims.npz", allow_pickle=True) as z:
            keep = {
                "seats_total": np.rint(z["seats_total"]).astype(np.int16),
                "entities": np.array([str(e) for e in z["entities"]]),
            }
            if "national" in z.files:
                keep["national"] = z["national"].astype(np.float32)
                keep["national_cols"] = np.array([str(c) for c in z["national_cols"]])
        np.savez_compressed(tmp / "sims.npz", **keep)

    dist = {f.stem.removeprefix("dist_next_"): np.load(f).astype(np.float32)
            for f in sorted(run_dir.glob("dist_next_*.npy"))}
    if dist:
        np.savez_compressed(tmp / "dist_next.npz", **dist)

    meta = {
        "run_id": manifest.get("run_id", run_dir.name),
        "source_run": str(run_dir.relative_to(paths.ROOT)) if run_dir.is_relative_to(paths.ROOT) else str(run_dir),
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "last_poll": manifest.get("last_poll"),
        "n_polls": manifest.get("n_polls"),
        "n_sims": manifest.get("n_sims"),
        "provinces_pivotal": len(provs),
    }
    meta["size_bytes"] = _dir_size(tmp)
    (tmp / "PUBLISHED.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    return PublishResult(dest=dest, run_id=meta["run_id"], provinces=len(provs), size_bytes=meta["size_bytes"])
