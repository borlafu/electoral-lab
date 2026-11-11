from electoral_lab.ingestion.interior import parse_03, parse_07, parse_08, to_label


def _fixed(fields, width):
    line = [" "] * width
    for start, val in fields:
        for i, ch in enumerate(val):
            line[start - 1 + i] = ch
    return "".join(line)


def test_fixed_width_files():
    l03 = _fixed([(1, "02"), (3, "2023"), (7, "07"), (9, "000123"), (15, "EAJ-PNV"), (65, "EUZKO ALDERDI JELTZALEA")], 232)
    l07 = _fixed([(1, "02"), (3, "2023"), (7, "07"), (9, "1"), (10, "16"), (12, "48"), (14, "9"),
                  (86, "00959702"), (126, "00005000"), (134, "00006000"), (142, "00600000"), (150, "000008")], 172)
    l08 = _fixed([(1, "02"), (3, "2023"), (7, "07"), (9, "1"), (10, "16"), (12, "48"), (14, "9"),
                  (15, "000123"), (21, "00150000"), (29, "00002")], 33)
    c03, c07, c08 = parse_03(l03), parse_07(l07), parse_08(l08)
    assert c03.siglas.iloc[0] == "EAJ-PNV"
    r = c07.iloc[0]
    assert (r.province, r.electors, r.blank, r.null, r.valid, r.seats) == ("48", 959702, 5000, 6000, 605000, 8)
    assert c08.iloc[0].votes == 150000 and c08.iloc[0].seats == 2
    assert to_label("EAJ-PNV", {"EAJ-PNV": "EAJ/PNV"}) == "EAJ/PNV"
    assert to_label("PSC-PSOE", {}) == "PSC–PSOE"
