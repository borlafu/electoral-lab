"""Importador de los ficheros oficiales del Ministerio del Interior (infoelectoral).

Descarga manual (el servidor bloquea accesos automatizados desde centros de datos, pero funciona
en un navegador normal):  https://infoelectoral.interior.gob.es/es/elecciones-celebradas/area-de-descargas/
ZIP «Congreso, total circunscripción», p. ej. 02202307_TOTA.zip. Ficheros de ancho fijo ISO-8859-1:

  03xxaamm.DAT  candidaturas      (código, siglas, denominación)
  07xxaamm.DAT  datos de circunscripción (censo, votantes, blancos, nulos, votos a candidaturas)
  08xxaamm.DAT  votos y diputados por candidatura y circunscripción

Posiciones (1-indexadas) tomadas del paquete rOpenSpain/infoelectoral y de la documentación oficial.
Las siglas oficiales se traducen a las etiquetas del registro con configs/parties/interior_labels.yaml.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import yaml

from electoral_lab.storage import paths, raw


def _f(line: str, a: int, b: int) -> str:
    return line[a - 1: b].strip()


def parse_03(text: str) -> pd.DataFrame:
    rows = []
    for ln in text.splitlines():
        if len(ln) < 214:
            continue
        rows.append(dict(party_code=_f(ln, 9, 14), siglas=_f(ln, 15, 64), denominacion=_f(ln, 65, 214)))
    return pd.DataFrame(rows)


def parse_07(text: str) -> pd.DataFrame:
    rows = []
    for ln in text.splitlines():
        if len(ln) < 155:
            continue
        prov = _f(ln, 12, 13)
        if prov in ("99", "00"):
            continue
        rows.append(dict(
            province=prov, electors=int(_f(ln, 86, 93) or 0),  # censo de escrutinio (incluye CERA)
            blank=int(_f(ln, 126, 133) or 0), null=int(_f(ln, 134, 141) or 0),
            candidacy_votes=int(_f(ln, 142, 149) or 0), seats=int(_f(ln, 150, 155) or 0),
        ))
    df = pd.DataFrame(rows)
    if not df.empty:
        df["valid"] = df.blank + df.candidacy_votes
        df["votes_cast"] = df.valid + df.null
        df = df.drop_duplicates("province")
    return df


def parse_08(text: str) -> pd.DataFrame:
    rows = []
    for ln in text.splitlines():
        if len(ln) < 33:
            continue
        prov = _f(ln, 12, 13)
        if prov in ("99", "00"):
            continue
        rows.append(dict(province=prov, party_code=_f(ln, 15, 20), votes=int(_f(ln, 21, 28) or 0),
                         seats=int(_f(ln, 29, 33) or 0)))
    return pd.DataFrame(rows).drop_duplicates(["province", "party_code"]) if rows else pd.DataFrame(rows)


def _labels() -> dict[str, str]:
    p = paths.CONFIGS / "parties" / "interior_labels.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else {}


def to_label(siglas: str, mapping: dict[str, str]) -> str:
    if siglas in mapping:
        return mapping[siglas]
    return re.sub(r"\s*-\s*", "–", siglas)


def import_zip(zip_path: Path, election: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    doc = raw.register_local(f"interior_{election}", Path(zip_path))
    with zipfile.ZipFile(io.BytesIO(doc.read_bytes())) as z:
        names = {n[:2]: n for n in z.namelist() if n.upper().endswith(".DAT")}
        read = lambda k: z.read(names[k]).decode("latin-1")  # noqa: E731
        c03, c07, c08 = parse_03(read("03")), parse_07(read("07")), parse_08(read("08"))
    mapping = _labels()
    c03["label"] = [to_label(s, mapping) for s in c03.siglas]
    res = c08.merge(c03[["party_code", "label", "denominacion"]], on="party_code", how="left")
    res = res.rename(columns={"denominacion": "name"})
    res["election"] = election
    res["source_url"] = f"interior:{Path(zip_path).name}"
    tot = c07.assign(election=election, source_url=f"interior:{Path(zip_path).name}")
    tot = tot[["election", "province", "source_url", "blank", "valid", "null", "votes_cast", "electors"]]
    res = res[["election", "province", "source_url", "label", "name", "votes", "seats"]]
    # sustituye esa elección en las tablas normalizadas
    from electoral_lab.ingestion.refresh import TABLES, load_table

    for key, new in (("results", res), ("totals", tot)):
        old = load_table(key)
        merged = pd.concat([old[old.election != election], new], ignore_index=True)
        paths.NORMALIZED.mkdir(parents=True, exist_ok=True)
        merged.to_csv(paths.NORMALIZED / TABLES[key], index=False)
    return res, tot
