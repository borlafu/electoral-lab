"""Lector mínimo de tablas en wikitexto con soporte de colspan/rowspan.

Solo se usa para fuentes secundarias (recopilaciones de Wikipedia). Cada celda conserva su
texto bruto para que los extractores decidan cómo interpretarlo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Cell:
    raw: str
    header: bool = False
    colspan: int = 1
    rowspan: int = 1
    attrs: str = ""
    origin: tuple[int, int] = (0, 0)  # (fila, columna) de la celda original si está expandida
    spanned: bool = False  # True si es copia por colspan/rowspan


@dataclass
class Table:
    caption: str = ""
    rows: list[list[Cell]] = field(default_factory=list)


def find_tables(text: str) -> list[tuple[int, int]]:
    """Posiciones (inicio, fin) de tablas de primer nivel, respetando anidamiento."""
    out, depth, start = [], 0, None
    for m in re.finditer(r"^\s*(\{\||\|\})", text, flags=re.M):
        tok = m.group(1)
        if tok == "{|":
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0 and start is not None:
                out.append((start, m.end()))
                start = None
    return out


def _split_outside(s: str, sep: str) -> list[str]:
    """Divide por 'sep' fuera de {{...}} y [[...]]."""
    parts, buf, depth_t, depth_l, i = [], [], 0, 0, 0
    while i < len(s):
        if s.startswith("{{", i):
            depth_t += 1; buf.append("{{"); i += 2; continue
        if s.startswith("}}", i) and depth_t:
            depth_t -= 1; buf.append("}}"); i += 2; continue
        if s.startswith("[[", i):
            depth_l += 1; buf.append("[["); i += 2; continue
        if s.startswith("]]", i) and depth_l:
            depth_l -= 1; buf.append("]]"); i += 2; continue
        if depth_t == 0 and depth_l == 0 and s.startswith(sep, i):
            parts.append("".join(buf)); buf = []; i += len(sep); continue
        buf.append(s[i]); i += 1
    parts.append("".join(buf))
    return parts


def _parse_cell(chunk: str, header: bool) -> Cell:
    # "attrs | contenido" (el primer '|' fuera de plantillas/enlaces separa atributos)
    pieces = _split_outside(chunk, "|")
    if len(pieces) > 1 and re.search(r"(style|colspan|rowspan|class|align|bgcolor|width|data-sort)\s*=", pieces[0]):
        attrs, content = pieces[0], "|".join(pieces[1:])
    else:
        attrs, content = "", chunk
    cs = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
    rs = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
    return Cell(content.strip(), header, int(cs.group(1)) if cs else 1, int(rs.group(1)) if rs else 1, attrs)


def parse_table(text: str) -> Table:
    lines = text.split("\n")
    t = Table()
    raw_rows: list[list[Cell]] = []
    cur: list[Cell] | None = None
    depth = 0
    buf_cell: list[str] | None = None

    def flush():
        nonlocal buf_cell
        if buf_cell is not None and cur is not None:
            kind, content = buf_cell
            sep = "!!" if kind == "!" else "||"
            for c in _split_outside(content, sep):
                cur.append(_parse_cell(c, kind == "!"))
        buf_cell = None

    for line in lines:
        s = line.strip()
        if s.startswith("{|"):
            depth += 1
            if depth == 1:
                continue
        if s.startswith("|}"):
            depth -= 1
            if depth == 0:
                flush()
                break
        if depth > 1:
            continue
        if s.startswith("|+"):
            flush(); t.caption = s[2:].strip(); continue
        if s.startswith("|-"):
            flush()
            cur = []
            raw_rows.append(cur)
            continue
        if s.startswith("!") or (s.startswith("|") and not s.startswith("|}")):
            flush()
            if cur is None:
                cur = []; raw_rows.append(cur)
            buf_cell = [s[0], s[1:]]
            continue
        if buf_cell is not None:
            buf_cell[1] += "\n" + line
    flush()

    # expandir colspan/rowspan en una rejilla
    grid: list[list[Cell]] = []
    pending: dict[tuple[int, int], Cell] = {}
    for r, row in enumerate(raw_rows):
        out: list[Cell] = []
        col = 0
        cells = list(row)
        while cells or (r, col) in pending:
            if (r, col) in pending:
                out.append(pending.pop((r, col))); col += 1; continue
            c = cells.pop(0)
            c.origin = (r, col)
            for dr in range(1, c.rowspan):
                for dc in range(c.colspan):
                    pending[(r + dr, col + dc)] = Cell(c.raw, c.header, c.colspan, c.rowspan, c.attrs, (r, col), True)
            out.append(c)
            for _ in range(1, c.colspan):
                out.append(Cell(c.raw, c.header, c.colspan, c.rowspan, c.attrs, (r, col), True))
            col += c.colspan
        grid.append(out)
    t.rows = [g for g in grid if g]
    return t


_TEMPLATE_KEEP = re.compile(r"\{\{(?:right|left|centre|center|nowrap|small)\|([^{}]*)\}\}", re.I)


def clean(raw: str) -> str:
    s = raw
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    for _ in range(3):
        s = _TEMPLATE_KEEP.sub(r"\1", s)
    s = re.sub(r"\{\{font\|[^{}]*\}\}", "", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip()


def first_number(s: str) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", s.replace(",", "") if re.search(r"\d,\d{3}", s) else s)
    if not m:
        return None
    return float(m.group().replace(",", "."))


def refs(raw: str) -> list[str]:
    return re.findall(r"\|\s*url\s*=\s*([^|}\s]+)", raw)
