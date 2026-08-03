"""Tests de bracket.py: estructura del cuadro (R32/TREE/LEFT/RIGHT/MATCH_DT),
etiquetas de slot, tabla oficial de terceros y resolucion del Round of 32.

`resolve_r32()` sin argumentos leeria el fixture de produccion, asi que todos
los tests le pasan `tables` sinteticas armadas con la fixture `group_rows`.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from prode.tournament import bracket

LETTERS = "ABCDEFGHIJKL"

# Slots de "mejor 3ro" tal como los declara R32: match -> conjunto elegible.
THIRD_SLOTS = {73 + i: set(code[2:])
               for i, pair in enumerate(bracket.R32)
               for code in pair if code.startswith("3:")}


def _parse(v):
    return datetime.strptime(v, "%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------
# (a) invariantes estructurales
# --------------------------------------------------------------------------
def test_r32_tiene_16_cruces():
    assert len(bracket.R32) == 16
    assert all(len(pair) == 2 for pair in bracket.R32)


def test_r32_codigos_bien_formados():
    """Cada slot es '1X'/'2X' de un grupo real, o '3:' + grupos elegibles."""
    for a, b in bracket.R32:
        for code in (a, b):
            if code.startswith("3:"):
                elig = code[2:]
                assert elig, f"{code!r} sin grupos elegibles"
                assert set(elig) <= set(LETTERS), code
                assert len(set(elig)) == len(elig), f"{code!r} repite grupos"
            else:
                assert code[0] in "12", code
                assert code[1:] in LETTERS, code


def test_r32_usa_cada_primero_y_segundo_exactamente_una_vez():
    codes = [c for pair in bracket.R32 for c in pair if not c.startswith("3:")]
    assert sorted(codes) == sorted([f"1{g}" for g in LETTERS] +
                                   [f"2{g}" for g in LETTERS])


def test_r32_tiene_8_slots_de_mejor_tercero():
    assert len(THIRD_SLOTS) == 8
    assert sorted(THIRD_SLOTS) == [74, 77, 79, 80, 81, 82, 85, 87]


def test_tree_cubre_89_a_102_y_104():
    assert set(bracket.TREE) == set(range(89, 103)) | {104}


def test_tree_tiene_fuentes_en_rango_valido():
    """Toda fuente es un partido anterior (73..102) del propio cuadro."""
    for m, sources in bracket.TREE.items():
        assert len(sources) == 2
        for s in sources:
            assert 73 <= s <= 102, f"M{m} toma de M{s}, fuera de rango"
            assert s < m, f"M{m} toma de M{s}, que es posterior"


def test_tree_consume_cada_partido_previo_una_sola_vez():
    """Los 30 partidos 73..102 alimentan exactamente un cruce posterior."""
    sources = [s for pair in bracket.TREE.values() for s in pair]
    assert len(sources) == 30
    assert sorted(sources) == list(range(73, 103))


def test_left_y_right_particionan_los_16_partidos_del_r32():
    izq, der = bracket.LEFT[0], bracket.RIGHT[0]
    assert len(izq) == 8 and len(der) == 8
    assert not set(izq) & set(der), "hay partidos del R32 en los dos lados"
    assert sorted(izq + der) == list(range(73, 89))


def test_left_y_right_cubren_todo_el_cuadro_sin_repetir():
    todos = [m for lado in (bracket.LEFT, bracket.RIGHT) for fila in lado for m in fila]
    assert sorted(todos) == list(range(73, 103))


def test_left_y_right_tienen_forma_8_4_2_1():
    for lado in (bracket.LEFT, bracket.RIGHT):
        assert [len(fila) for fila in lado] == [8, 4, 2, 1]


def test_final_y_tercer_puesto():
    assert bracket.FINAL_M == 104
    assert bracket.FINAL_M in bracket.TREE
    assert bracket.THIRD_PLACE == 103
    assert bracket.THIRD_PLACE not in bracket.TREE, "el 3er puesto no alimenta nada"


def test_rounds_cubre_todo_el_cuadro_mas_la_final():
    todos = [m for _, ms in bracket.ROUNDS for m in ms]
    assert sorted(todos) == sorted(list(range(73, 103)) + [104])
    assert [nombre for nombre, _ in bracket.ROUNDS] == [
        "16vos", "Octavos", "Cuartos", "Semis", "Final"]


def test_match_dt_tiene_las_32_llaves():
    assert sorted(bracket.MATCH_DT) == list(range(73, 105))


@pytest.mark.parametrize("m", sorted(bracket.MATCH_DT))
def test_match_dt_parsea_como_datetime(m):
    assert isinstance(_parse(bracket.MATCH_DT[m]), datetime)


def test_match_dt_respeta_el_orden_del_arbol():
    """Ningun cruce esta programado antes que los partidos que lo alimentan."""
    dt = {m: _parse(v) for m, v in bracket.MATCH_DT.items()}
    for m, sources in bracket.TREE.items():
        for s in sources:
            assert dt[s] < dt[m], f"M{m} arranca antes de terminar M{s}"


# --------------------------------------------------------------------------
# (b) slot_label
# --------------------------------------------------------------------------
@pytest.mark.parametrize("code,esperado", [
    ("2A", "2° A"),
    ("1L", "1° L"),
    ("3:ABCDF", "mejor 3° (ABCDF)"),
    ("3:DEIJL", "mejor 3° (DEIJL)"),
    ("", "?"),
    (None, "?"),
])
def test_slot_label(code, esperado):
    assert bracket.slot_label(code) == esperado


@pytest.mark.parametrize("code", [c for pair in bracket.R32 for c in pair])
def test_slot_label_no_devuelve_interrogante_para_codigos_reales(code):
    assert bracket.slot_label(code) != "?"


# --------------------------------------------------------------------------
# (c) tabla oficial de terceros (Annex C)
# --------------------------------------------------------------------------
def test_thirds_table_tiene_las_495_combinaciones():
    assert len(bracket._thirds_table()) == 495


def test_thirds_table_cada_fila_tiene_8_entradas():
    for combo, row in bracket._thirds_table().items():
        assert len(row) == 8, f"{combo} tiene {len(row)} entradas"


def test_thirds_table_llaves_son_combinaciones_ordenadas_de_8_grupos():
    for combo in bracket._thirds_table():
        assert len(combo) == 8
        assert set(combo) <= set(LETTERS)
        assert list(combo) == sorted(combo), f"{combo} no esta ordenada"


def test_thirds_table_asigna_los_8_slots_de_tercero():
    esperados = {str(m) for m in THIRD_SLOTS}
    for combo, row in bracket._thirds_table().items():
        assert set(row) == esperados, f"{combo} no cubre los slots de tercero"


def test_thirds_table_respeta_los_grupos_elegibles_y_no_repite():
    for combo, row in bracket._thirds_table().items():
        assert sorted(row.values()) == sorted(combo), f"{combo} no usa sus 8 grupos"
        for m, g in row.items():
            assert g in THIRD_SLOTS[int(m)], f"{combo}: M{m} recibe {g}, no elegible"


def test_thirds_table_se_cachea():
    assert bracket._thirds_table() is bracket._thirds_table()


# --------------------------------------------------------------------------
# (d) resolve_r32 con standings sinteticas
# --------------------------------------------------------------------------
def _tables(group_rows, terceros, letters=LETTERS):
    """12 grupos ya ordenados; los terceros de `terceros` clasifican (mas pts)."""
    return {g: group_rows({f"{g}1": (9, 5, 7),
                           f"{g}2": (6, 3, 5),
                           f"{g}3": (4 if g in terceros else 1, 0, 3),
                           f"{g}4": (0, -8, 1)})
            for g in letters}


def _third_slots_resueltos(rows):
    """[(match, code, equipo)] de los cruces cuyo slot es '3:...'."""
    out = []
    for r in rows:
        for side in ("a", "b"):
            if r[f"{side}_code"].startswith("3:"):
                out.append((r["match"], r[f"{side}_code"], r[side]))
    return out


def test_resolve_r32_devuelve_16_cruces(group_rows):
    rows = bracket.resolve_r32(_tables(group_rows, set("ABCDEFGH")))
    assert len(rows) == 16
    assert [r["match"] for r in rows] == list(range(73, 89))
    assert all(set(r) == {"match", "a", "b", "a_code", "b_code"} for r in rows)


def test_resolve_r32_ubica_primeros_y_segundos_segun_r32(group_rows):
    """M73 = 2A vs 2B y M74 = 1E vs mejor 3ro, con los equipos de la tabla."""
    rows = bracket.resolve_r32(_tables(group_rows, set("ABCDEFGH")))
    por_match = {r["match"]: r for r in rows}
    assert (por_match[73]["a"], por_match[73]["b"]) == ("A2", "B2")
    assert por_match[74]["a"] == "E1"
    assert (por_match[88]["a_code"], por_match[88]["b_code"]) == ("2D", "2G")
    assert (por_match[88]["a"], por_match[88]["b"]) == ("D2", "G2")


def test_resolve_r32_no_deja_ningun_cupo_sin_equipo(group_rows):
    rows = bracket.resolve_r32(_tables(group_rows, set("ABCDEFGH")))
    assert all(r["a"] and r["b"] for r in rows)


@pytest.mark.parametrize("terceros", ["ABCDEFGH", "EFGHIJKL", "ABCDEGIK",
                                      "ACEGIKBD", "DEFGHIJK"])
def test_resolve_r32_terceros_elegibles_y_sin_repetir(group_rows, terceros):
    """Cada '3:XYZ' recibe un tercero de un grupo elegible, y no se repite."""
    rows = bracket.resolve_r32(_tables(group_rows, set(terceros)))
    resueltos = _third_slots_resueltos(rows)
    assert len(resueltos) == 8
    for m, code, team in resueltos:
        assert team is not None, f"M{m} ({code}) quedo sin tercero"
        grupo = team[0]                       # equipos sinteticos: "<grupo>3"
        assert team == f"{grupo}3"
        assert grupo in code[2:], f"M{m}: grupo {grupo} no esta en {code}"
        assert grupo in terceros, f"M{m}: {grupo} no clasifico"
    assert len({t for _, _, t in resueltos}) == 8, "un tercero repetido en dos cruces"


def test_resolve_r32_usa_la_asignacion_oficial_cuando_hay_8_terceros(group_rows):
    """Con la combinacion completa manda thirds_table.json, no el backtracking."""
    terceros = "ABCDEFGH"
    fila = bracket._thirds_table()[terceros]
    rows = bracket.resolve_r32(_tables(group_rows, set(terceros)))
    for m, _code, team in _third_slots_resueltos(rows):
        assert team == f"{fila[str(m)]}3", f"M{m} no sigue la tabla oficial"


def test_resolve_r32_sin_tabla_oficial_cae_al_emparejamiento(group_rows, monkeypatch):
    """Si falta thirds_table.json, `_match_thirds` igual llena los 8 slots."""
    monkeypatch.setattr(bracket, "_thirds_table", dict)
    rows = bracket.resolve_r32(_tables(group_rows, set("ABCDEFGH")))
    resueltos = _third_slots_resueltos(rows)
    assert len({t for _, _, t in resueltos}) == 8
    for m, code, team in resueltos:
        assert team[0] in code[2:], f"M{m}: {team} no elegible en {code}"


def test_resolve_r32_con_grupos_faltantes_deja_slots_en_none(group_rows):
    """Tablas parciales (6 grupos): los cupos que no se pueden determinar son None."""
    rows = bracket.resolve_r32(_tables(group_rows, set("ABCDEF"), letters="ABCDEF"))
    assert len(rows) == 16
    por_match = {r["match"]: r for r in rows}
    assert (por_match[73]["a"], por_match[73]["b"]) == ("A2", "B2")
    assert por_match[86]["b"] is None            # 2H: el grupo H no existe
    assert all(t is None for _, _, t in _third_slots_resueltos(rows))


# --------------------------------------------------------------------------
# (e) _match_thirds aislado
# --------------------------------------------------------------------------
def test_match_thirds_emparejamiento_forzado():
    """Solo hay una asignacion posible: x es el unico slot que acepta A."""
    slots = [("x", {"A"}), ("y", {"A", "B"})]
    assert bracket._match_thirds(["A", "B"], slots) == {"x": "A", "y": "B"}


def test_match_thirds_backtrackea_cuando_la_primera_opcion_no_cierra():
    """x agarra A primero, deja a y sin candidato y tiene que retroceder."""
    slots = [("x", {"A", "B"}), ("y", {"A"})]
    assert bracket._match_thirds(["A", "B"], slots) == {"x": "B", "y": "A"}


def test_match_thirds_sin_solucion_devuelve_vacio():
    slots = [("x", {"A"}), ("y", {"A"})]
    assert bracket._match_thirds(["A"], slots) == {}


def test_match_thirds_ignora_grupos_no_elegibles():
    slots = [("x", {"B", "C"})]
    assert bracket._match_thirds(["A", "B"], slots) == {"x": "B"}


def test_match_thirds_resuelve_los_8_slots_reales():
    """Los conjuntos elegibles de R32 admiten solucion para 8 terceros cualquiera."""
    slots = [(m, elig) for m, elig in sorted(THIRD_SLOTS.items())]
    for terceros in ("ABCDEFGH", "EFGHIJKL", "ABCDEGIK"):
        res = bracket._match_thirds(sorted(terceros), slots)
        assert len(res) == 8, f"{terceros} no se pudo emparejar"
        assert sorted(res.values()) == sorted(terceros)
        for m, g in res.items():
            assert g in THIRD_SLOTS[m]
