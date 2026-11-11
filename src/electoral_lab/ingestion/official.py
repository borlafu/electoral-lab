"""Importadores de fuentes oficiales.

* BOE — Real Decreto 806/2026 de convocatoria: escaños por circunscripción (anexo).
* BOE — candidaturas proclamadas al Congreso (BOE-A-2026-23103, 3-XI-2026).
* INE — nota de prensa del censo electoral para el 29-N (CER + CERA por provincia).
"""

from __future__ import annotations

import io
import re

import pandas as pd

from electoral_lab.geography.catalog import provinces, resolve
from electoral_lab.party_registry.registry import Registry
from electoral_lab.storage import raw

BOE_CONVOCATORIA_XML = "https://www.boe.es/eli/es/rd/2026/10/05/806/dof/spa/xml"
BOE_CONVOCATORIA_HTML = "https://www.boe.es/eli/es/rd/2026/10/05/806"
BOE_CANDIDATURAS_PDF = "https://www.boe.es/boe/dias/2026/11/03/pdfs/BOE-A-2026-23103.pdf"
INE_CENSO_PDF = "https://www.ine.es/dyngs/Prensa/EG2026.pdf"

_UNITS = {
    "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciséis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiuno": 21, "veintiuna": 21, "veintidós": 22, "veintitrés": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiséis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50}


def spanish_number(word: str) -> int:
    w = word.strip().strip(".").lower()
    if w in _UNITS:
        return _UNITS[w]
    if w in _TENS:
        return _TENS[w]
    m = re.fullmatch(r"(treinta|cuarenta|cincuenta) y (\w+)", w)
    if m:
        return _TENS[m.group(1)] + _UNITS[m.group(2)]
    raise ValueError(f"número no reconocido: {word!r}")


# ---------------------------------------------------------------- escaños (convocatoria)
def parse_convocatoria(xml: str) -> pd.DataFrame:
    cells = re.findall(r'<td class="cuerpo_tabla_izq">([^<]*)</td>', xml)
    rows = []
    for name, num in zip(cells[0::2], cells[1::2], strict=False):
        code = resolve(name.strip().rstrip("."))
        rows.append(dict(province=code, name_boe=name.strip().rstrip("."), seats=spanish_number(num)))
    df = pd.DataFrame(rows)
    if len(df) != 52 or df.seats.sum() != 350:
        raise ValueError(f"anexo del BOE inesperado: {len(df)} circunscripciones, {df.seats.sum()} escaños")
    df["source_url"] = BOE_CONVOCATORIA_HTML
    return df


def fetch_convocatoria() -> pd.DataFrame:
    doc = raw.fetch("boe_convocatoria", BOE_CONVOCATORIA_XML, "xml")
    return parse_convocatoria(doc.read_text())


# ---------------------------------------------------------------- candidaturas proclamadas
_NOISE = re.compile(
    r"BOLETÍN\s+OFICIAL|^\s*Núm\. \d+|cve: BOE|Verificable en|^\s*(:evc|se\.eob\.www//:sptth|ne|elbacifireV)\s*$"
)
# El texto vertical del margen (cve) aparece invertido al final de algunas líneas con layout=True.
_MARGIN = re.compile(r"\s{2,}(\d{5}-\d{4}-A-EOB|BOE-A-\d{4}-\d+)\s*$")
_NUM = re.compile(r"^\s+(\d+)\.\s+(\S.*?)\s*$")


def pdf_layout_text(pdf_bytes: bytes) -> str:
    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text(layout=True) or "")
    return "\n".join(out)


def parse_candidaturas(text: str, registry: Registry) -> pd.DataFrame:
    lines = [_MARGIN.sub("", ln).rstrip() for ln in text.split("\n") if not _NOISE.search(ln)]
    prov = None
    sec = None
    last = 0
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.search(r"Junta Electoral Provincial de ([^,]+?)(?:,| en su)", ln)
        if m:
            prov = m.group(1).strip()
            sec = None
        s = ln.strip()
        if s == "CONGRESO DE LOS DIPUTADOS":
            sec, last = "C", 0
        elif s.startswith("SENADO"):
            sec = "S"
        mm = _NUM.match(ln)
        if sec == "C" and mm and not mm.group(2).endswith(".") and last < int(mm.group(1)) <= last + 3:
            name = mm.group(2)
            j = i
            while (j + 1 < len(lines) and lines[j + 1].strip() and not _NUM.match(lines[j + 1])
                   and not lines[j + 1].strip().lower().startswith("no proclamada")):
                j += 1
                name += " " + lines[j].strip()
            name = re.sub(r"-\s+", "-", name)
            nxt = next((x.strip() for x in lines[j + 1: j + 4] if x.strip()), "")
            proclaimed = not nxt.lower().startswith("no proclamada") and "no proclamada" not in name.lower()
            name = re.sub(r"\s*No proclamada\.?\s*$", "", name, flags=re.I)
            out.append(dict(province_raw=prov, order=int(mm.group(1)), name=name, proclaimed=proclaimed))
            last = int(mm.group(1))
            i = j
        i += 1
    df = pd.DataFrame(out)
    df["province"] = [resolve(p) for p in df.province_raw]
    df["party_id"] = [registry.candidacy_party(n, p) for n, p in zip(df.name, df.province, strict=False)]
    df["source_url"] = BOE_CANDIDATURAS_PDF
    return df


def fetch_candidaturas(registry: Registry) -> pd.DataFrame:
    doc = raw.fetch("boe_candidaturas", BOE_CANDIDATURAS_PDF, "pdf")
    return parse_candidaturas(pdf_layout_text(doc.read_bytes()), registry)


# ---------------------------------------------------------------- censo INE
def parse_censo(text: str) -> pd.DataFrame:
    rows = {}
    pat = re.compile(r"^(\d{2}) (.+?) ([\d.]+) ([\d.]+) ([\d.]+)\s*$")
    for ln in text.split("\n"):
        m = pat.match(ln.strip())
        if not m:
            continue
        code = m.group(1)
        if code not in provinces():
            continue
        tot, res, ext = (int(x.replace(".", "")) for x in m.group(3, 4, 5))
        if res + ext != tot:
            continue
        rows[code] = dict(province=code, electors=tot, electors_cer=res, electors_cera=ext)
    df = pd.DataFrame(rows.values()).sort_values("province")
    if len(df) != 52:
        raise ValueError(f"censo INE: se esperaban 52 provincias, hay {len(df)}")
    df["source_url"] = INE_CENSO_PDF
    return df


def fetch_censo() -> pd.DataFrame:
    import pdfplumber

    doc = raw.fetch("ine_censo", INE_CENSO_PDF, "pdf")
    with pdfplumber.open(doc.path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    return parse_censo(text)
