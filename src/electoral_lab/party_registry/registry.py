"""Registro de partidos: correspondencias entre sondeos, candidaturas proclamadas y elecciones pasadas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from electoral_lab.storage import paths

OTHERS = "OTROS"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Party:
    id: str
    name: str
    color: str = "#999999"
    bloc: str = "other"
    poll_labels: list[str] = field(default_factory=list)
    candidacy: list[str] = field(default_factory=list)
    base: dict = field(default_factory=dict)
    local_province: str | None = None

    @property
    def is_local(self) -> bool:
        return self.local_province is not None


class Registry:
    def __init__(self, data: dict):
        self.election = data.get("election")
        self.parties: dict[str, Party] = {}
        for pid, d in data["parties"].items():
            self.parties[pid] = Party(pid, d["name"], d.get("color", "#999"), d.get("bloc", "other"),
                                      d.get("poll_labels", []), d.get("candidacy", []), d.get("base", {}))
        for pid, d in (data.get("local_parties") or {}).items():
            self.parties[pid] = Party(pid, d["name"], d.get("color", "#777"), "local", [], d.get("candidacy", []),
                                      d.get("base", {}), str(d["province"]))
        self.sumar_family: dict[str, list[str]] = data.get("sumar_family", {})
        self._poll = {_norm(lab): pid for pid, p in self.parties.items() for lab in p.poll_labels}
        self._poll.update({_norm(k): v for k, v in (data.get("poll_extra_labels") or {}).items()})
        self.national_groups: dict[str, str] = data.get("national_groups") or {}
        self._cand = [(pid, re.compile(rx, re.I)) for pid, p in self.parties.items() for rx in p.candidacy]

    @classmethod
    def load(cls, path: Path | None = None) -> Registry:
        path = path or paths.CONFIGS / "parties" / "registry_2026.yaml"
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    @property
    def national_ids(self) -> list[str]:
        return [p for p, x in self.parties.items() if not x.is_local]

    @property
    def local_ids(self) -> list[str]:
        return [p for p, x in self.parties.items() if x.is_local]

    def group(self, pid: str) -> str:
        """Entidad nacional (agregador de sondeos) a la que pertenece una entidad provincial."""
        return self.national_groups.get(pid, pid)

    @property
    def national_groups_ids(self) -> list[str]:
        seen = []
        for p in self.national_ids:
            g = self.group(p)
            if g not in seen:
                seen.append(g)
        return seen

    def poll_party(self, label: str) -> str | None:
        return self._poll.get(_norm(label))

    def candidacy_party(self, name: str, province: str | None = None) -> str:
        for pid, rx in self._cand:
            p = self.parties[pid]
            if p.is_local and province is not None and p.local_province != province:
                continue
            if rx.search(name):
                return pid
        return OTHERS

    def base_labels(self, pid: str, election: str) -> list[str]:
        spec = self.parties[pid].base.get(election)
        return spec if isinstance(spec, list) else []

    def label_owner(self, election: str) -> dict[str, str]:
        """Etiqueta histórica -> entidad (excluye la familia Sumar, que se reparte aparte)."""
        out = {}
        for pid in self.parties:
            for lab in self.base_labels(pid, election):
                out[lab] = pid
        return out


@lru_cache
def default() -> Registry:
    return Registry.load()
