from datetime import date

from electoral_lab.ingestion.official import parse_candidaturas, parse_convocatoria, spanish_number
from electoral_lab.ingestion.polls_wikipedia import parse_fieldwork
from electoral_lab.ingestion.results_wikipedia import _last_paren, parse_section
from electoral_lab.party_registry.registry import Registry


def test_spanish_numbers():
    assert spanish_number("Cuatro.") == 4
    assert spanish_number("Treinta y ocho") == 38
    assert spanish_number("Dieciséis.") == 16
    assert spanish_number("Treinta y dos.") == 32


def test_fieldwork_dates():
    assert parse_fieldwork("26 Oct–9 Nov", 2026) == (date(2026, 10, 26), date(2026, 11, 9))
    assert parse_fieldwork("3–5 Nov", 2026) == (date(2026, 11, 3), date(2026, 11, 5))
    assert parse_fieldwork("9 Nov", 2026) == (date(2026, 11, 9), date(2026, 11, 9))
    assert parse_fieldwork("28 Dec–4 Jan", 2026) == (date(2025, 12, 28), date(2026, 1, 4))


def test_convocatoria_annex():
    rows = []
    from electoral_lab.geography.catalog import provinces

    seats = {c: 6 for c in provinces()}
    seats["28"] = 38 + (350 - 6 * 52 - 38 + 6)  # cuadra a 350
    for c, p in provinces().items():
        from electoral_lab.ingestion.official import _TENS, _UNITS

        inv = {v: k for k, v in _UNITS.items()}
        n = seats[c]
        word = inv.get(n) or next(f"{t} y {inv[n - v]}" for t, v in _TENS.items() if 0 < n - v < 10)
        rows.append(f'<td class="cuerpo_tabla_izq">{p.name}.</td><td class="cuerpo_tabla_izq">{word.capitalize()}.</td>')
    df = parse_convocatoria("".join(rows))
    assert df.seats.sum() == 350 and len(df) == 52


def test_candidaturas_layout():
    text = """
        La Junta Electoral Provincial de Málaga, en su reunión del día de la fecha, ha
                     CONGRESO DE LOS DIPUTADOS
              1. PARTIDO SOCIALISTA OBRERO ESPAÑOL (PSOE)
          1. Fulana de Tal.
          2. Mengano Pérez.
              2. PARTIDO POPULAR (PP)
          1. Zutano Gómez.                        30132-6202-A-EOB
              3. FEMINISTAS AL CONGRESO (PFAC)
              No proclamada.
              4. Frente Amplio (FA)
          1. Otra Persona.
                     SENADO
              1. PARTIDO POPULAR (PP)
    """
    df = parse_candidaturas(text, Registry.load())
    assert df.party_id.tolist() == ["PSOE", "PP", "OTROS", "FA"]
    assert df.proclaimed.tolist() == [True, True, False, True]
    assert set(df.province) == {"29"}


def test_results_section_and_nested_parens():
    assert _last_paren("Socialist Party of the Basque Country (PSE–EE (PSOE))") == "PSE–EE (PSOE)"
    wikitext = """===2023===
{| class="wikitable"
|-
| style="background:red"|
| align="left"| [[People's Party (Spain)|People's Party]] (PP)
| 302,000 || 37.88 || +10
| '''5''' || +2
|-
| style="background:red"|
| align="left"| [[PSOE]] (PSOE)
| 239,172 || 30.00 || 0
| '''3''' || −1
|-
| align="left" colspan="2"| Blank ballots
| 7,509 || 0.95 || 0
|-
| align="left" colspan="2"| Valid votes
| 548,681 || 98 ||
|}
"""
    parties, totals = parse_section(wikitext, "2023")
    assert [(p["label"], p["votes"], p["seats"]) for p in parties] == [("PP", 302000, 5), ("PSOE", 239172, 3)]
    assert totals == {"blank": 7509, "valid": 548681}


def test_registry_mappings():
    reg = Registry.load()
    assert reg.candidacy_party("PARTIDO SOCIALISTA DE EUSKADI-EUSKADIKO EZKERRA (PSOE) PSE-EE (PSOE)") == "PSOE"
    assert reg.candidacy_party("UNIDAD DEL PUEBLO CANARIO UPC (NC-BC, PODEMOS, IU, SUMAR)") == "FA"
    assert reg.candidacy_party("COMPROMÍS: FRONT VALENCIÀ (COMPROMIS-EUPV-PODEM-ERPV)") == "FV"
    assert reg.candidacy_party("TERUEL EXISTE (TERUEL EXISTE)", "44") == "EXISTE"
    assert reg.candidacy_party("PARTIDO ANIMALISTA CON EL MEDIO AMBIENTE (PACMA)") == "OTROS"
    assert reg.poll_party("Adelante Andalucía (2021)") == "ADELANTE"
    assert reg.group("FV") == "FA_FV"
