#!/usr/bin/env python3
"""
bracket.py
==========
Proyeccion del Round of 32 del Mundial 2026 a partir de las posiciones ACTUALES
de los grupos (aunque la fase no haya terminado): un vistazo de como quedarian
los cruces si las posiciones se mantuvieran.

Estructura oficial de cruces (Annex C del reglamento FIFA). Los 8 partidos que
enfrentan a un ganador de grupo con un "mejor 3ro" se resuelven con la tabla
OFICIAL: `thirds_table.json` trae las 495 combinaciones posibles de los 8 grupos
que aportan tercero, y para cada una dice a que cruce va el tercero de cada
grupo. Si la combinacion todavia no esta completa (faltan grupos por terminar)
se cae a un backtracking que respeta los grupos elegibles de cada cruce, que es
una proyeccion razonable pero puede diferir de la asignacion final.
"""
from __future__ import annotations

from prode import paths
from prode.tournament import groups

_THIRDS = None


def _thirds_table():
    """Tabla oficial de asignacion de los 8 mejores terceros (Annex C, 495 combos),
    parseada de Wikipedia por parse_thirds.py -> thirds_table.json.
    {combinacion de grupos (str ordenado): {match (str): grupo del 3ro}}."""
    global _THIRDS
    if _THIRDS is None:
        import json
        p = paths.THIRDS_JSON
        _THIRDS = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _THIRDS

# (lado_a, lado_b) por partido del Round of 32 (M73..M88).
# "1X"/"2X" = ganador/segundo del grupo X; "3:XYZ" = mejor 3ro de esos grupos.
R32 = [
    ("2A", "2B"),            # M73
    ("1E", "3:ABCDF"),       # M74
    ("1F", "2C"),            # M75
    ("1C", "2F"),            # M76
    ("1I", "3:CDFGH"),       # M77
    ("2E", "2I"),            # M78
    ("1A", "3:CEFHI"),       # M79
    ("1L", "3:EHIJK"),       # M80
    ("1D", "3:BEFIJ"),       # M81
    ("1G", "3:AEHIJ"),       # M82
    ("2K", "2L"),            # M83
    ("1H", "2J"),            # M84
    ("1B", "3:EFGIJ"),       # M85
    ("1J", "2H"),            # M86
    ("1K", "3:DEIJL"),       # M87
    ("2D", "2G"),            # M88
]

# arbol: match -> (match fuente A, match fuente B), de octavos a la final
TREE = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
    101: (97, 98), 102: (99, 100), 104: (101, 102),
}
ROUNDS = [
    ("16vos", list(range(73, 89))),
    ("Octavos", list(range(89, 97))),
    ("Cuartos", list(range(97, 101))),
    ("Semis", [101, 102]),
    ("Final", [104]),
]

# bracket bilateral: cada lado = [R32(8), 8vos(4), 4tos(2), semi(1)] en orden vertical
LEFT = [
    [74, 77, 73, 75, 83, 84, 81, 82],
    [89, 90, 93, 94],
    [97, 98],
    [101],
]
RIGHT = [
    [76, 78, 79, 80, 86, 88, 85, 87],
    [91, 92, 95, 96],
    [99, 100],
    [102],
]
FINAL_M = 104       # Ganador M101 vs Ganador M102
THIRD_PLACE = 103   # Perdedor M101 vs Perdedor M102

# Fecha y hora de cada partido de eliminacion en HORA DE ARGENTINA (UTC-3 = ET +1h).
# TODOS los partidos (M73-M104) verificados el 29/06/2026 vs ESPN + worldcupwiki (+ dallasfwc26/FIFA
# para la semi): horarios oficiales en ET, ARG = ET + 1. (M94 Seattle 8pm ET = 21:00 ARG, confirmado.)
MATCH_DT = {
    73: "2026-06-28 16:00", 74: "2026-06-29 17:30", 75: "2026-06-29 22:00", 76: "2026-06-29 14:00",
    77: "2026-06-30 18:00", 78: "2026-06-30 14:00", 79: "2026-06-30 22:00", 80: "2026-07-01 13:00",
    81: "2026-07-01 21:00", 82: "2026-07-01 17:00", 83: "2026-07-02 20:00", 84: "2026-07-02 16:00",
    85: "2026-07-03 00:00", 86: "2026-07-03 19:00", 87: "2026-07-03 22:30", 88: "2026-07-03 15:00",
    89: "2026-07-04 18:00", 90: "2026-07-04 14:00", 91: "2026-07-05 17:00", 92: "2026-07-05 21:00",
    93: "2026-07-06 16:00", 94: "2026-07-06 21:00", 95: "2026-07-07 13:00", 96: "2026-07-07 17:00",
    97: "2026-07-09 17:00", 98: "2026-07-10 16:00", 99: "2026-07-11 18:00", 100: "2026-07-11 22:00",
    101: "2026-07-14 16:00", 102: "2026-07-15 16:00", 103: "2026-07-18 18:00", 104: "2026-07-19 16:00",
}


def _match_thirds(third_groups, slots):
    """Asigna cada grupo-tercero clasificado a un slot cuyo conjunto de grupos
    elegibles lo incluya (backtracking, 8x8)."""
    result = {}
    used = set()

    def bt(k):
        if k == len(slots):
            return True
        key, elig = slots[k]
        for g in third_groups:
            if g not in used and g in elig:
                used.add(g); result[key] = g
                if bt(k + 1):
                    return True
                used.discard(g); result.pop(key, None)
        return False

    bt(0)
    return result


def resolve_r32(tables):
    """16 dicts {match, a, b, a_code, b_code} con los equipos proyectados (o None
    si todavia no se puede determinar el cupo).

    `tables` son las posiciones que devuelve `groups.standings(fx)`. Se pasan y no
    se resuelven aca: este modulo no lee de disco."""
    _, best = groups.qualifiers(tables)
    pos = {}
    for g, tt in tables.items():
        pos[f"1{g}"], pos[f"2{g}"], pos[f"3{g}"] = tt[0]["team"], tt[1]["team"], tt[2]["team"]

    third_groups = sorted(g for g in tables if tables[g][2]["team"] in best)
    assign = {}
    row = _thirds_table().get("".join(third_groups)) if len(third_groups) == 8 else None
    if row:                              # asignacion OFICIAL de FIFA (Annex C, 495 combos)
        for i, (a, b) in enumerate(R32):
            for side, code in (("a", a), ("b", b)):
                if code.startswith("3:") and str(73 + i) in row:
                    assign[(i, side)] = row[str(73 + i)]
    else:                                # combinacion incompleta -> emparejamiento valido provisional
        slots = [((i, side), set(code[2:]))
                 for i, (a, b) in enumerate(R32)
                 for side, code in (("a", a), ("b", b)) if code.startswith("3:")]
        assign = _match_thirds(third_groups, slots)

    def team(code, i, side):
        if code.startswith("3:"):
            g = assign.get((i, side))
            return pos.get(f"3{g}") if g else None
        return pos.get(code)

    out = []
    for i, (a, b) in enumerate(R32):
        out.append({"match": 73 + i, "a": team(a, i, "a"), "b": team(b, i, "b"),
                    "a_code": a, "b_code": b})
    return out


def slot_label(code):
    """Texto de un slot todavia sin equipo: '2A' -> '2° A'; '3:ABCDF' -> 'mejor 3° (ABCDF)'."""
    if not code:
        return "?"
    if code.startswith("3:"):
        return f"mejor 3° ({code[2:]})"
    return f"{code[0]}° {code[1]}"


if __name__ == "__main__":
    from prode.data import app_data   # solo al correrlo a mano: ver la nota en groups.py

    rows = resolve_r32(groups.standings(app_data.fixture()))
    print(f"Round of 32 proyectado ({sum(1 for m in rows if m['a'] and m['b'])}/16 cruces con equipos):")
    for m in rows:
        a = m["a"] or f"[{m['a_code']}]"
        b = m["b"] or f"[{m['b_code']}]"
        print(f"  M{m['match']}: {a:<24} vs  {b}")
