"""Descarga y archivo inmutable de documentos originales (data/raw/<fuente>/<fecha>_<hash>.<ext>)."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from electoral_lab.storage import catalog, paths

# Wikimedia y otros servidores piden un User-Agent con contacto. Configúralo con ELECTORAL_LAB_CONTACT.
USER_AGENT = f"electoral-lab/0.1 ({os.environ.get('ELECTORAL_LAB_CONTACT', 'uso personal; investigación electoral local')})"


@dataclass
class RawDoc:
    source_id: str
    url: str | None
    path: Path
    sha256: str

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.path.read_text(encoding=encoding)


def _store(source_id: str, url: str | None, content: bytes, ext: str, note: str = "") -> RawDoc:
    sha = hashlib.sha256(content).hexdigest()
    d = paths.RAW / source_id
    d.mkdir(parents=True, exist_ok=True)
    existing = list(d.glob(f"*_{sha[:12]}.{ext}"))
    if existing:
        return RawDoc(source_id, url, existing[0], sha)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    p = d / f"{ts}_{sha[:12]}.{ext}"
    p.write_bytes(content)
    catalog.record_raw(source_id, url, sha, str(p.relative_to(paths.ROOT)), len(content), note)
    return RawDoc(source_id, url, p, sha)


def fetch(source_id: str, url: str, ext: str, params: dict | None = None, timeout: float = 60.0) -> RawDoc:
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "text/html" in ctype and ext not in ("html", "htm") and b"Just a moment" in r.content[:2000]:
            raise RuntimeError(
                f"{url} devolvió una página de verificación anti-bots. Descárgalo con el navegador y usa la importación manual."
            )
        full = str(r.url)
        return _store(source_id, full, r.content, ext)


def register_local(source_id: str, file: Path, note: str = "importación manual") -> RawDoc:
    file = Path(file).expanduser()
    content = file.read_bytes()
    ext = file.suffix.lstrip(".") or "bin"
    doc = _store(source_id, f"file://{file.name}", content, ext, note)
    return doc


def latest(source_id: str, ext: str | None = None) -> RawDoc | None:
    d = paths.RAW / source_id
    if not d.exists():
        return None
    files = sorted(d.glob(f"*.{ext}" if ext else "*"))
    if not files:
        return None
    p = files[-1]
    return RawDoc(source_id, None, p, hashlib.sha256(p.read_bytes()).hexdigest())


def copy_to(doc: RawDoc, dest: Path) -> None:
    shutil.copy2(doc.path, dest)
