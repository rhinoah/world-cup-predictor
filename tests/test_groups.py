"""Tests de groups.py: integridad de GROUPS, tablas, desempates y clasificados.

OJO: `groups.standings()` cuenta solo los partidos con `state == "done"`, y el
factory `match` de conftest calcula ese estado contra el reloj real. Por eso
todos los partidos de estos tests usan `LONG_AGO` como kickoff: siempre dan
"done", corra cuando corra (y `FUTURO`, nunca).
"""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from prode.data import app_data
from prode.tournament import groups
from prode.tournament import teams
from conftest import LONG_AGO

FUTURO = datetime(2099, 6, 15, 16, 0)   # nunca "done" contra el reloj real

ALL_TEAMS = [t for teams in groups.GROUPS.values() for t in teams]


# --------------------------------------------------------------------------
# (a) integridad de GROUPS
# --------------------------------------------------------------------------
def test_groups_tiene_12_grupos_con_llaves_A_a_L():
    assert list(groups.GROUPS) == list("ABCDEFGHIJKL")


def test_groups_tiene_4_equipos_por_grupo():
    for g, teams in groups.GROUPS.items():
        assert len(teams) == 4, f"grupo {g} no tiene 4 equipos"


def test_groups_tiene_48_equipos_sin_repetir():
    assert len(ALL_TEAMS) == 48
    assert len(set(ALL_TEAMS)) == 48, "hay selecciones duplicadas entre grupos"


# --------------------------------------------------------------------------
# (b) re-exports: groups y app_data siguen exponiendo lo que la app importa
# --------------------------------------------------------------------------
# Antes aca vivian tests que chequeaban que GROUPS, ABBR y FLAG_ISO estuvieran
# SINCRONIZADOS entre si. Desde que los tres derivan de teams.TEAMS eso no puede
# fallar por construccion, asi que se fueron: los invariantes del padron (y el
# typo en un nombre canonico, que es el modo de falla que los reemplaza) se
# testean contra un testigo externo en tests/test_teams.py.
def test_groups_y_app_data_reexportan_el_padron():
    """La app importa groups.GROUPS y app_data.ABBR/FLAG_ISO: si un re-export se
    cae, prode_app.py explota al arrancar y ningun otro test lo nota."""
    assert groups.GROUPS is teams.GROUPS
    assert groups.team_group is teams.team_group
    assert app_data.ABBR is teams.ABBR
    assert app_data.FLAG_ISO is teams.FLAG_ISO
    assert app_data.HOSTS is teams.HOSTS


# --------------------------------------------------------------------------
# (c) team_group
# --------------------------------------------------------------------------
@pytest.mark.parametrize("team,grupo", [
    ("Mexico", "A"), ("Canada", "B"), ("Brazil", "C"), ("United States", "D"),
    ("Curaçao", "E"), ("Japan", "F"), ("New Zealand", "G"), ("Cape Verde", "H"),
    ("France", "I"), ("Argentina", "J"), ("DR Congo", "K"), ("Panama", "L"),
])
def test_team_group_devuelve_el_grupo_correcto(team, grupo):
    assert groups.team_group(team) == grupo


@pytest.mark.parametrize("team", ["Italy", "", "MEX", "curaçao", None])
def test_team_group_devuelve_none_para_desconocidos(team):
    assert groups.team_group(team) is None


def test_team_group_es_consistente_con_groups():
    for g, teams in groups.GROUPS.items():
        for t in teams:
            assert groups.team_group(t) == g


# --------------------------------------------------------------------------
# (d) standings: puntos, goles, partidos jugados
# --------------------------------------------------------------------------
def _fx(match, triples):
    """triples: [(home, away, gh, ga)] -> lista de partidos terminados."""
    return [match(home=h, away=a, kickoff=LONG_AGO, real=(gh, ga))
            for h, a, gh, ga in triples]


def test_standings_devuelve_los_12_grupos_con_4_filas():
    tb = groups.standings([{"home": "Mexico", "away": "South Africa",
                            "kickoff": LONG_AGO, "real": None}])
    assert list(tb) == list("ABCDEFGHIJKL")
    for g, filas in tb.items():
        assert len(filas) == 4
        assert {r["team"] for r in filas} == set(groups.GROUPS[g])


def test_standings_calcula_puntos_goles_y_pj(match):
    """3 por ganar, 1 por empatar, 0 por perder; gf/gc/dg/pj acumulados."""
    fx = _fx(match, [
        ("Mexico", "South Africa", 2, 0),
        ("South Korea", "Czech Republic", 1, 1),
        ("Mexico", "South Korea", 1, 3),
    ])
    tabla = {r["team"]: r for r in groups.standings(fx)["A"]}

    assert tabla["Mexico"] == dict(team="Mexico", pj=2, g=1, e=0, p=1,
                                   gf=3, gc=3, dg=0, pts=3)
    assert tabla["South Korea"] == dict(team="South Korea", pj=2, g=1, e=1, p=0,
                                        gf=4, gc=2, dg=2, pts=4)
    assert tabla["Czech Republic"] == dict(team="Czech Republic", pj=1, g=0, e=1,
                                           p=0, gf=1, gc=1, dg=0, pts=1)
    assert tabla["South Africa"] == dict(team="South Africa", pj=1, g=0, e=0, p=1,
                                         gf=0, gc=2, dg=-2, pts=0)


def test_standings_ordena_por_puntos(match):
    fx = _fx(match, [
        ("Mexico", "South Africa", 2, 0),
        ("South Korea", "Czech Republic", 1, 1),
        ("Mexico", "South Korea", 1, 3),
    ])
    orden = [r["team"] for r in groups.standings(fx)["A"]]
    assert orden == ["South Korea", "Mexico", "Czech Republic", "South Africa"]


def test_standings_deja_en_cero_a_los_grupos_sin_partidos(match):
    fx = _fx(match, [("Mexico", "South Africa", 2, 0)])
    for r in groups.standings(fx)["L"]:
        assert (r["pj"], r["pts"], r["gf"], r["gc"], r["dg"]) == (0, 0, 0, 0, 0)


def test_standings_ignora_partidos_sin_resultado(match):
    fx = [match(home="Mexico", away="South Africa", kickoff=LONG_AGO, real=None)]
    for r in groups.standings(fx)["A"]:
        assert r["pj"] == 0


def test_standings_ignora_partidos_que_no_terminaron(match):
    """Kickoff en el futuro -> match_state != 'done' -> no suma nada."""
    fx = [match(home="Mexico", away="South Africa", kickoff=FUTURO, real=(2, 0))]
    for r in groups.standings(fx)["A"]:
        assert r["pj"] == 0


def test_standings_ignora_equipos_fuera_de_groups(match):
    """Un amistoso contra alguien que no esta en el Mundial no entra en ninguna tabla."""
    fx = _fx(match, [("Mexico", "Italy", 3, 0)])
    tabla = {r["team"]: r for r in groups.standings(fx)["A"]}
    assert tabla["Mexico"]["pj"] == 0


# --------------------------------------------------------------------------
# (e) desempates: pts -> dg -> gf -> head to head
# --------------------------------------------------------------------------
def test_standings_desempata_por_diferencia_de_gol(match):
    """Mismos puntos: primero el de mejor DG."""
    fx = _fx(match, [
        ("Brazil", "Haiti", 1, 0),        # BRA 3 pts, DG +1
        ("Morocco", "Scotland", 4, 0),    # MAR 3 pts, DG +4
    ])
    orden = [r["team"] for r in groups.standings(fx)["C"]]
    assert orden[:2] == ["Morocco", "Brazil"]


def test_standings_desempata_por_goles_a_favor(match):
    """Mismos puntos y misma DG: primero el que hizo mas goles."""
    fx = _fx(match, [
        ("Brazil", "Haiti", 1, 0),        # BRA 3 pts, DG +1, GF 1
        ("Morocco", "Scotland", 3, 2),    # MAR 3 pts, DG +1, GF 3
    ])
    orden = [r["team"] for r in groups.standings(fx)["C"]]
    assert orden[:2] == ["Morocco", "Brazil"]


def test_standings_desempata_por_enfrentamiento_directo(match):
    """Canada y Bosnia quedan iguales en pts/DG/GF: manda el mano a mano.

    Bosnia 1-0 Canada, Canada 1-0 Qatar, Suiza 1-0 Bosnia
      -> ambos 3 pts, DG 0, GF 1; Bosnia gano el cruce -> Bosnia arriba.
    """
    fx = _fx(match, [
        ("Bosnia and Herzegovina", "Canada", 1, 0),
        ("Canada", "Qatar", 1, 0),
        ("Switzerland", "Bosnia and Herzegovina", 1, 0),
    ])
    tb = groups.standings(fx)["B"]
    tabla = {r["team"]: r for r in tb}

    # premisa del test: estan realmente empatados en los tres criterios globales
    for t in ("Canada", "Bosnia and Herzegovina"):
        assert (tabla[t]["pts"], tabla[t]["dg"], tabla[t]["gf"]) == (3, 0, 1)

    orden = [r["team"] for r in tb]
    assert orden == ["Switzerland", "Bosnia and Herzegovina", "Canada", "Qatar"]


def test_standings_h2h_no_altera_a_los_que_no_estan_empatados(match):
    """El que gano el mano a mano igual queda abajo si tiene menos puntos."""
    fx = _fx(match, [
        ("Qatar", "Switzerland", 1, 0),      # Qatar le gana a Suiza...
        ("Switzerland", "Canada", 5, 0),     # ...pero Suiza golea y llega a 3 pts
        ("Qatar", "Bosnia and Herzegovina", 0, 3),
    ])
    orden = [r["team"] for r in groups.standings(fx)["B"]]
    assert orden.index("Switzerland") < orden.index("Qatar")


# --------------------------------------------------------------------------
# (f) qualifiers: 24 directos + 8 mejores terceros
# --------------------------------------------------------------------------
@pytest.fixture
def tablas_sinteticas(group_rows):
    """12 grupos ya ordenados; los 3ros se diferencian solo por GF (0..11)."""
    tb = {}
    for i, (g, teams) in enumerate(groups.GROUPS.items()):
        tb[g] = group_rows({
            teams[0]: (9, 9, 20),
            teams[1]: (6, 5, 15),
            teams[2]: (3, 0, i),     # <- el GF define el ranking de terceros
            teams[3]: (0, -9, 1),
        })
    return tb


def test_qualifiers_devuelve_24_directos_y_8_terceros(tablas_sinteticas):
    direct, best = groups.qualifiers(tablas_sinteticas)
    assert len(direct) == 24
    assert len(best) == 8
    assert direct & best == set()


def test_qualifiers_toma_primero_y_segundo_de_cada_grupo(tablas_sinteticas):
    direct, _ = groups.qualifiers(tablas_sinteticas)
    esperados = {tt[0]["team"] for tt in tablas_sinteticas.values()}
    esperados |= {tt[1]["team"] for tt in tablas_sinteticas.values()}
    assert direct == esperados


def test_qualifiers_elige_los_8_mejores_terceros(tablas_sinteticas):
    """Los 3ros de E..L tienen mas GF que los de A..D -> pasan ellos."""
    _, best = groups.qualifiers(tablas_sinteticas)
    assert best == {groups.GROUPS[g][2] for g in "EFGHIJKL"}
    afuera = {groups.GROUPS[g][2] for g in "ABCD"}
    assert best & afuera == set()


def test_qualifiers_sobre_standings_reales(match):
    """Integracion: standings -> qualifiers sigue dando 24 + 8."""
    fx = _fx(match, [
        ("Mexico", "South Africa", 2, 0),
        ("South Korea", "Czech Republic", 1, 1),
        ("Argentina", "Algeria", 3, 1),
    ])
    direct, best = groups.qualifiers(groups.standings(fx))
    assert len(direct) == 24
    assert len(best) == 8
    assert "Mexico" in direct and "Argentina" in direct


# --------------------------------------------------------------------------
# (g) qualification_status
# --------------------------------------------------------------------------
def test_qualification_status_etiqueta_a_los_48(tablas_sinteticas):
    status = groups.qualification_status(tablas_sinteticas)
    assert len(status) == 48
    assert set(status) == set(ALL_TEAMS)
    assert set(status.values()) == {"direct", "third", "out"}


def test_qualification_status_reparte_24_8_y_16(tablas_sinteticas):
    status = groups.qualification_status(tablas_sinteticas)
    conteo = {v: sum(1 for x in status.values() if x == v) for v in set(status.values())}
    assert conteo == {"direct": 24, "third": 8, "out": 16}


def test_qualification_status_marca_direct_third_y_out(tablas_sinteticas):
    status = groups.qualification_status(tablas_sinteticas)
    l_group = groups.GROUPS["L"]
    a_group = groups.GROUPS["A"]
    assert status[l_group[0]] == "direct"
    assert status[l_group[1]] == "direct"
    assert status[l_group[2]] == "third"      # 3ro con GF 11 -> entra
    assert status[l_group[3]] == "out"
    assert status[a_group[2]] == "out"        # 3ro con GF 0 -> queda afuera


# --------------------------------------------------------------------------
# group_matches
# --------------------------------------------------------------------------
def test_group_matches_filtra_por_grupo_y_ordena_por_kickoff(match):
    tarde = datetime(2000, 1, 1, 20, 0)
    fx = [
        match(home="Mexico", away="South Africa", kickoff=tarde, real=(2, 0)),
        match(home="South Korea", away="Czech Republic", kickoff=LONG_AGO, real=(1, 1)),
        match(home="Argentina", away="Algeria", kickoff=LONG_AGO, real=(3, 1)),
    ]
    ms = groups.group_matches("A", fx)
    assert [(m["home"], m["away"]) for m in ms] == [
        ("South Korea", "Czech Republic"), ("Mexico", "South Africa")]


# --------------------------------------------------------------------------
# comportamiento actual documentado (ver notas)
# --------------------------------------------------------------------------
def test_standings_no_lee_de_disco(project):
    """groups es computo puro: sin partidos devuelve las 12 tablas en cero, no se
    va a buscar el fixture. Antes tenia un `fx or app_data.fixture()` que hacia
    justo eso, y era la mitad del ciclo de imports app_data <-> groups.

    El `project` apunta BASE a un tmp vacio: si quedara alguna lectura, explota."""
    tb = groups.standings([])

    assert list(tb) == list("ABCDEFGHIJKL")
    assert all(r["pj"] == 0 for filas in tb.values() for r in filas)


def test_groups_no_importa_app_data():
    """El ciclo se cierra en el import, asi que hay que fijarlo en el import: si
    alguien vuelve a poner `import app_data` arriba, este test lo ataja."""
    arbol = ast.parse(Path(groups.__file__).read_text(encoding="utf-8"))
    de_modulo = {(n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
                 for n in arbol.body if isinstance(n, (ast.Import, ast.ImportFrom))
                 for a in n.names}
    assert "app_data" not in de_modulo
    assert "bracket" not in de_modulo


def test_standings_ignora_un_cruce_entre_grupos_distintos(match):
    """Antes sumaba en LAS DOS tablas. `standings` recibe la lista de partidos y
    no controla quien se la pasa: un cruce de eliminacion (o un amistoso) le
    daria puntos de fase de grupos a los dos equipos."""
    fx = _fx(match, [("Mexico", "Brazil", 1, 0)])       # A vs C
    tb = groups.standings(fx)

    assert {r["team"]: r["pts"] for r in tb["A"]}["Mexico"] == 0
    assert {r["team"]: r["pj"] for r in tb["C"]}["Brazil"] == 0
