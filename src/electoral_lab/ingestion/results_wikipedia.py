"""Resultados provinciales históricos del Congreso desde las páginas de circunscripción de Wikipedia.

Fuente SECUNDARIA usada como semilla porque la descarga oficial de Interior está protegida contra
accesos automatizados desde centros de datos. Si importas los ficheros oficiales (ingestion.interior),
estos sustituyen a la semilla. Los repartos se validan reproduciendo los escaños oficiales.
"""

from __future__ import annotations

import json
import re
import time

import pandas as pd

from electoral_lab.geography.catalog import provinces
from electoral_lab.ingestion import wikitable as wt
from electoral_lab.storage import raw

API = "https://en.wikipedia.org/w/api.php"

SECTIONS = {"congreso_2023": "2023", "congreso_2019n": "November 2019"}
TOTAL_ROWS = {
    "blank ballots": "blank",
    "valid votes": "valid",
    "invalid votes": "null",
    "votes cast / turnout": "votes_cast",
    "registered voters": "electors",
}


def fetch_page(code: str, wiki_name: str) -> raw.RawDoc:
    page = f"{wiki_name} (Congress of Deputies constituency)"
    return raw.fetch(
        f"wikipedia_constituencies/{code}",
        API,
        "json",
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": "2",
                "redirects": "1"},
    )


def _last_paren(s: str) -> str | None:
    """Contenido del último grupo entre paréntesis equilibrados al final: 'X (PSE–EE (PSOE))' -> 'PSE–EE (PSOE)'."""
    s = s.rstrip()
    if not s.endswith(")"):
        return None
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                return s[i + 1 : -1].strip()
    return None


def parse_section(text: str, section_title: str) -> tuple[list[dict], dict]:
    m = re.search(rf"^===\s*{re.escape(section_title)}\s*===\s*$", text, re.M)
    if not m:
        return [], {}
    body = text[m.end():]
    nxt = re.search(r"^==", body, re.M)
    body = body[: nxt.start()] if nxt else body
    spans = wt.find_tables(body)
    if not spans:
        return [], {}
    tab = wt.parse_table(body[spans[0][0]: spans[0][1]])
    parties, totals = [], {}
    for r in tab.rows:
        texts = [wt.clean(c.raw) for c in r]
        if not texts:
            continue
        key = texts[0].lower()
        if key in TOTAL_ROWS and len(texts) > 1:
            nums = [wt.first_number(x.replace(",", "")) for x in texts[1:] if re.match(r"^[\d,]+", x)]
            if nums:
                totals[TOTAL_ROWS[key]] = int(nums[0])
            continue
        acr = _last_paren(re.sub(r"\s*\d+$", "", texts[1])) if len(texts) >= 4 and texts[0] == "" else None
        if acr:
            name = re.sub(r"\s*\d+$", "", texts[1]).strip()  # quita superíndices de notas
            votes = wt.first_number(texts[2].replace(",", ""))
            if votes is None or texts[2].lower().startswith("n/a"):
                continue
            seats = None
            for t in texts[5:7]:
                if re.fullmatch(r"\d+", t):
                    seats = int(t)
                    break
            parties.append(dict(label=acr, name=name, votes=int(votes), seats=seats or 0))
    return parties, totals


def collect(
    elections=("congreso_2023", "congreso_2019n"), pause: float = 1.0, offline: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarga (o reutiliza con offline=True) las 52 páginas y devuelve (resultados, totales)."""
    res_rows, tot_rows = [], []
    for code, p in provinces().items():
        doc = raw.latest(f"wikipedia_constituencies/{code}", "json") if offline else None
        if doc is None:
            doc = fetch_page(code, p.wiki_en)
            time.sleep(pause)
        doc.url = doc.url or f"https://en.wikipedia.org/wiki/{p.wiki_en.replace(' ', '_')}_(Congress_of_Deputies_constituency)"
        text = json.loads(doc.read_text())["parse"]["wikitext"]
        for el in elections:
            parties, totals = parse_section(text, SECTIONS[el])
            for x in parties:
                res_rows.append(dict(election=el, province=code, source_url=doc.url, **x))
            if totals:
                tot_rows.append(dict(election=el, province=code, source_url=doc.url, **totals))
    res, tot = pd.DataFrame(res_rows), pd.DataFrame(tot_rows)
    return res, reconcile(res, tot)


def reconcile(res: pd.DataFrame, tot: pd.DataFrame) -> pd.DataFrame:
    """Corrige totales incoherentes con la suma de candidaturas (erratas de la fuente secundaria).

    Si |sum(votos) + blancos - válidos| supera el 0,2 %, se recalculan válidos y emitidos y se anota.
    Ejemplo real: Cáceres 2023 figura con 40.000 válidos de más.
    """
    tot = tot.copy()
    tot["note"] = ""
    s = res.groupby(["election", "province"]).votes.sum()
    for i, r in tot.iterrows():
        cand = s.get((r.election, r.province))
        if cand is None or pd.isna(r.blank) or pd.isna(r.valid):
            continue
        diff = cand + r.blank - r.valid
        if abs(diff) > 0.002 * r.valid:
            tot.at[i, "note"] = f"válidos corregidos {int(r.valid)} -> {int(cand + r.blank)}"
            tot.at[i, "valid"] = cand + r.blank
            tot.at[i, "votes_cast"] = cand + r.blank + (r["null"] or 0)
    return tot
