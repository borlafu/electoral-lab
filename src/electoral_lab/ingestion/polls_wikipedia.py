"""Adaptador de sondeos: recopilación de Wikipedia («Opinion polling for the 2026 Spanish general election»).

Es una fuente SECUNDARIA: cada fila conserva la URL de la referencia original (encuestadora o
medio) para poder auditarla. Las observaciones entran con review_status='auto' y pasan por
validation.polls antes de usarse.

Semántica registrada para cada valor:
  measure_type = 'vote_estimate' (estimación de voto publicada, no intención directa)
  denominator  = 'valid_votes'   (supuesto documentado; la tabla excluye abstención y NS/NC)
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

import pandas as pd

from electoral_lab.ingestion import wikitable as wt
from electoral_lab.party_registry.registry import Registry
from electoral_lab.storage import raw

PAGE = "Opinion_polling_for_the_2026_Spanish_general_election"
API = "https://en.wikipedia.org/w/api.php"
SOURCE_ID = "wikipedia_polls_2026"

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def fetch_wikitext(page: str = PAGE, source_id: str = SOURCE_ID) -> raw.RawDoc:
    return raw.fetch(
        source_id,
        API,
        "json",
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": "2",
                "redirects": "1"},
    )


def _sections(text: str) -> list[tuple[str, int, int]]:
    heads = [(m.group(2).strip(), m.start(), len(m.group(1))) for m in re.finditer(r"^(=+)([^=\n]+)\1\s*$", text, re.M)]
    out = []
    for i, (title, start, lvl) in enumerate(heads):
        end = len(text)
        for _t2, s2, l2 in heads[i + 1:]:
            if l2 <= lvl:
                end = s2
                break
        out.append((title, start, end))
    return out


def parse_fieldwork(s: str, year: int) -> tuple[date | None, date | None]:
    s = wt.clean(s).replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    # forma general: "d1 [m1] [y1] - d2 m2 [y2]"
    m = re.match(r"^(\d{1,2})(?:\s+([A-Za-z]{3})[a-z]*)?(?:\s+(\d{4}))?\s*(?:-\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*(?:\s+(\d{4}))?)?$", s)
    if not m:
        return None, None
    d1, m1, y1, d2, m2, y2 = m.groups()
    try:
        if d2 is None:  # un solo día "9 Nov"
            mm = MONTHS[m1.lower()]
            d = date(int(y1) if y1 else year, mm, int(d1))
            return d, d
        mo2 = MONTHS[m2.lower()]
        ye2 = int(y2) if y2 else year
        mo1 = MONTHS[m1.lower()] if m1 else mo2
        ye1 = int(y1) if y1 else (ye2 - 1 if mo1 > mo2 else ye2)
        return date(ye1, mo1, int(d1)), date(ye2, mo2, int(d2))
    except (KeyError, ValueError):
        return None, None


def _header_label(raw_cell: str) -> str:
    m = re.findall(r"link=([^|\]]+)(?:\|([^\]]+))?\]\]", raw_cell)
    if m:
        target, label = m[-1]
        return (label or target).strip()
    return wt.clean(raw_cell)


def parse_tables(text: str, registry: Registry, sections: tuple[str, ...] | None = None) -> pd.DataFrame:
    rows = []
    for title, start, end in _sections(text):
        ym = re.match(r"^(\d{4})", title)
        if not ym:
            continue
        if sections and title not in sections:
            continue
        year = int(ym.group(1))
        body = text[start:end]
        spans = wt.find_tables(body)
        if not spans:
            continue
        a, b = spans[0]
        tab = wt.parse_table(body[a:b])
        if len(tab.rows) < 3:
            continue
        head = tab.rows[0]
        colmap: dict[int, str | None] = {}
        fixed: dict[str, int] = {}
        for j, c in enumerate(head):
            lab = wt.clean(c.raw).lower()
            if "polling firm" in lab:
                fixed["firm"] = j
            elif "fieldwork" in lab:
                fixed["date"] = j
            elif "sample" in lab:
                fixed["n"] = j
            elif "turnout" in lab:
                fixed["turnout"] = j
            elif lab == "lead":
                fixed["lead"] = j
            else:
                colmap[j] = registry.poll_party(_header_label(c.raw))
        for r in tab.rows[1:]:
            if not r or all(c.header for c in r) or len(r) < len(head) - 1:
                continue
            firm_raw = r[fixed["firm"]].raw if "firm" in fixed else ""
            firm = wt.clean(firm_raw)
            if not firm or re.search(r"election|results?$", firm, re.I) and "/" not in firm:
                continue
            d0, d1 = parse_fieldwork(r[fixed["date"]].raw, year) if "date" in fixed else (None, None)
            n = wt.first_number(wt.clean(r[fixed["n"]].raw).replace(",", "")) if "n" in fixed else None
            urls = wt.refs(firm_raw)
            pollster, _, sponsor = firm.partition("/")
            pid = hashlib.sha1(f"{firm}|{d0}|{d1}|{n}".encode()).hexdigest()[:12]
            for j, party in colmap.items():
                if j >= len(r):
                    continue
                c = r[j]
                if c.spanned and c.origin[1] != j:
                    continue  # copia de colspan: el valor se asigna a la primera columna
                val = wt.first_number(wt.clean(c.raw.split("<br")[0]))
                if val is None or party is None:
                    continue
                merged = []
                if c.colspan > 1:
                    merged = [colmap.get(j + k) for k in range(1, c.colspan)]
                rows.append(dict(
                    poll_id=pid, source_id=SOURCE_ID, source_url=urls[0] if urls else None,
                    publisher="Wikipedia (recopilación)", pollster=pollster.strip(), sponsor=sponsor.strip() or None,
                    fieldwork_start=d0, fieldwork_end=d1, sample_size=n,
                    geographic_scope="ES", measure_type="vote_estimate", denominator="valid_votes",
                    party_id=party, merged_with="+".join(m for m in merged if m) or None,
                    reported_value=val, table=title, review_status="auto",
                ))
    df = pd.DataFrame(rows)
    if not df.empty:
        df["fieldwork_start"] = pd.to_datetime(df["fieldwork_start"])
        df["fieldwork_end"] = pd.to_datetime(df["fieldwork_end"])
    return df
