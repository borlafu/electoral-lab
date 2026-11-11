"""Catálogo de circunscripciones (provincias INE) y resolución de nombres y municipios."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from electoral_lab.storage import paths


@dataclass(frozen=True)
class Province:
    code: str  # código INE, 2 dígitos
    name: str
    ccaa_code: str
    ccaa: str
    wiki_en: str
    aliases: tuple[str, ...]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


@lru_cache
def provinces() -> dict[str, Province]:
    out = {}
    with open(paths.CONFIGS / "geography" / "provincias.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["ine_code"]] = Province(
                r["ine_code"], r["name"], r["ccaa_code"], r["ccaa"], r["wiki_en"], tuple(r["aliases"].split("|"))
            )
    return out


@lru_cache
def _alias_index() -> dict[str, str]:
    idx = {}
    for code, p in provinces().items():
        for a in (p.name, p.wiki_en, *p.aliases):
            idx[norm(a)] = code
    return idx


# Municipios relevantes para el usuario que no coinciden con el nombre de su provincia.
MUNICIPALITIES = {
    "bilbao": "48",
    "getxo": "48",
    "barakaldo": "48",
    "marbella": "29",
    "torremolinos": "29",
    "alcala de henares": "28",
    "mostoles": "28",
    "villanueva del ariscal": "41",
    "donostia": "20",
    "san sebastian": "20",
    "vitoria": "01",
    "vitoria gasteiz": "01",
    "pamplona": "31",
    "iruna": "31",
    "gijon": "33",
    "oviedo": "33",
    "vigo": "36",
    "santiago de compostela": "15",
    "jerez de la frontera": "11",
    "elche": "03",
    "cartagena": "30",
    "palma": "07",
}


def resolve(name: str) -> str:
    """Devuelve el código INE de la circunscripción para un nombre de provincia o municipio."""
    n = norm(name)
    if n in _alias_index():
        return _alias_index()[n]
    if n in MUNICIPALITIES:
        return MUNICIPALITIES[n]
    if n.isdigit() and n.zfill(2) in provinces():
        return n.zfill(2)
    raise KeyError(f"No reconozco la circunscripción o municipio: {name!r}")


def by_ccaa() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c, p in provinces().items():
        out.setdefault(p.ccaa_code, []).append(c)
    return out
