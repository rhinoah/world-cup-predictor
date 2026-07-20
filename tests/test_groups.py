"""Tests de groups.py: integridad de GROUPS, tablas, desempates y clasificados.

OJO: `groups.standings()` llama a `app_data.match_state(m["kickoff"])` sin pasar
`now`, asi que compara contra el reloj real. Por eso todos los partidos de estos
tests usan `LONG_AGO` como kickoff: siempre dan "done", corra cuando corra.
"""
from __future__ import annotations

from datetime import datetime

import pytest

import app_data
import groups
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
# (b) cobertura en app_data.ABBR / app_data.FLAG_ISO (ataja typos)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("team", sorted(set(ALL_TEAMS)))
def test_todo_equipo_tiene_abbr_y_bandera(team):
    """Un typo tipo 'Curacao' vs 'Curaçao' rompe el bracket y la UI."""
    assert team in app_data.ABBR, f"{team!r} no esta en app_data.ABBR"
    assert team in app_data.FLAG_ISO, f"{team!r} no esta en app_data.FLAG_ISO"


def test_abbr_y_flag_iso_no_tienen_equipos_de_mas():
    """Las tablas de siglas/banderas cubren exactamente a los 48 clasificados."""
    teams = set(ALL_TEAMS)
    assert set(app_data.ABBR) - teams == set()
    assert set(app_data.FLAG_ISO) - teams == set()


def test_las_siglas_son_de_tres_letras_y_unicas():
    siglas = [app_data.ABBR[t] for t in ALL_TEAMS]
    assert all(len(s) == 3 for s in siglas)
    assert len(set(siglas)) == 48, "hay siglas repetidas en ABBR"


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
def test_standings_con_lista_vacia_cae_al_fixture_de_disco(project):
    """`fx or app_data.fixture()`: una lista vacia es falsy y se va a leer el CSV."""
    with pytest.raises(FileNotFoundError):
        groups.standings([])


def test_standings_cuenta_cruces_entre_grupos(match):
    """Hoy un partido entre equipos de grupos distintos suma en ambas tablas."""
    fx = _fx(match, [("Mexico", "Brazil", 1, 0)])
    tb = groups.standings(fx)
    assert {r["team"]: r["pts"] for r in tb["A"]}["Mexico"] == 3
    assert {r["team"]: r["pj"] for r in tb["C"]}["Brazil"] == 1
