"""Perfil territorial de las europeas de 2024 (porcentaje por provincia) desde Wikipedia.

Se usa para dos cosas que 2023 no permite: el perfil de SALF (no se presentó en 2023) y la
proporción Podemos / (Podemos + Sumar) con la que se reparte el voto de Sumar 2023.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from electoral_lab.geography.catalog import resolve
from electoral_lab.ingestion import wikitable as wt
from electoral_lab.storage import raw

PAGE = "Results_of_the_2024_European_Parliament_election_in_Spain"
PAGE_URL = f"https://en.wikipedia.org/wiki/{PAGE}"
API = "https://en.wikipedia.org/w/api.php"

LABELS = {"PP": "PP", "PSOE": "PSOE", "Vox": "VOX", "Sumar": "SUMAR", "SALF": "SALF", "Podemos": "PODEMOS",
          "Junts": "JUNTS", "ERC": "ERC", "EH Bildu": "BILDU", "PNV": "PNV", "BNG": "BNG", "CCa": "CCA"}


def fetch() -> raw.RawDoc:
    return raw.fetch("wikipedia_ep2024", API, "json", params={
        "action": "parse", "page": PAGE, "prop": "wikitext", "format": "json", "formatversion": "2"})


def parse(text: str) -> pd.DataFrame:
    i = text.find("===Constituencies===")
    body = text[i:]
    spans = [s for s in wt.find_tables(body) if "Summary of constituency results" in body[s[0]: s[0] + 300]]
    if not spans:
        raise ValueError("no se encuentra la tabla de circunscripciones de las europeas 2024")
    tab = wt.parse_table(body[spans[0][0]: spans[0][1]])
    head = tab.rows[0]
    cols = {}
    for j, c in enumerate(head):
        lab = wt.clean(c.raw)
        if lab in LABELS and not c.spanned:
            cols[j] = LABELS[lab]
    rows = []
    for r in tab.rows[3:]:
        if not r or r[0].header:
            continue
        name = wt.clean(r[0].raw)
        try:
            code = resolve(name) if name else None
        except KeyError:
            continue
        if not code:
            continue
        for j, pid in cols.items():
            if j < len(r) and not r[j].spanned and "AAAAAA" not in r[j].attrs:
                v = wt.first_number(wt.clean(r[j].raw))
                if v is not None:
                    rows.append(dict(province=code, party=pid, pct=v, source_url=PAGE_URL))
    df = pd.DataFrame(rows)
    if df.province.nunique() != 52:
        raise ValueError(f"europeas 2024: {df.province.nunique()} provincias")
    return df


def load(doc: raw.RawDoc) -> pd.DataFrame:
    return parse(json.loads(doc.read_text())["parse"]["wikitext"])


__all__ = ["fetch", "parse", "load", "re"]
