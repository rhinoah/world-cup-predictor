"""Tests de `app_data.scoreboard()`.

La funcion acepta `fx` inyectado y `now` explicito, asi que casi todo se prueba
con dicts en memoria (factories `match`/`ko_match`) sin tocar disco.

`PRODES` se monkeypatchea a dos prodes conocidos para no depender de
`prodes.json` (que no esta versionado):
    P1 -> 3 exacto / 1 direccion      (indice 0 de `m["load"]`)
    P2 -> 6 exacto / 3 direccion      (indice 1 de `m["load"]`)

Igual se usa la fixture `project` en todos lados: `match_state()` consulta
`data/finished.csv` via `_finished_set()`, y sin aislar BASE leeria el archivo
real del proyecto.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from prode.data import app_data
from conftest import GROUPS_DAY, KO_DAY

# Momentos utiles: "done" para grupos (ventana 120') y para eliminacion (210').
AFTER_GROUPS = GROUPS_DAY + timedelta(hours=6)
AFTER_KO = KO_DAY + timedelta(hours=6)


@pytest.fixture
def prodes(monkeypatch):
    """Dos prodes con puntajes distintos: 3/1 y 6/3."""
    p = {"P1": (3, 1), "P2": (6, 3)}
    monkeypatch.setattr(app_data, "PRODES", p)
    return p


# --------------------------------------------------------------------------
# (a) carga parcial: no cargado en un prode = 0 puntos, pero cuenta como jugado
# --------------------------------------------------------------------------

def test_scoreboard_no_cargado_en_un_prode_no_suma_pero_cuenta_jugado(
        project, prodes, match):
    """load=(1,0): el acierto suma en P1 y en P2 cuenta jugado+fallado con 0."""
    fx = [match(pred=(2, 1), real=(2, 1), load=(1, 0))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    assert b["P1"]["total"] == 3
    assert (b["P1"]["n"], b["P1"]["exact"], b["P1"]["fail"]) == (1, 1, 0)

    assert b["P2"]["total"] == 0
    assert b["P2"]["n"] == 1            # el partido se jugo: no desaparece
    assert b["P2"]["fail"] == 1
    assert b["P2"]["exact"] == 0
    assert b["P2"]["dir"] == 0


def test_scoreboard_no_cargado_en_ninguno_cuenta_en_los_dos(project, prodes, match):
    fx = [match(pred=(1, 0), real=(1, 0), load=(0, 0))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    for name in ("P1", "P2"):
        assert b[name]["total"] == 0
        assert b[name]["n"] == 1
        assert b[name]["fail"] == 1


# --------------------------------------------------------------------------
# (b) mismo acierto, puntajes distintos por prode
# --------------------------------------------------------------------------

def test_scoreboard_acierto_exacto_puntua_3_y_6(project, prodes, match):
    """El mismo marcador clavado vale 3 en el prode 3/1 y 6 en el 6/3."""
    fx = [match(pred=(2, 1), real=(2, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    assert b["P1"]["total"] == 3
    assert b["P2"]["total"] == 6
    for name in ("P1", "P2"):
        assert b[name]["exact"] == 1
        assert b[name]["dir"] == 0
        assert b[name]["fail"] == 0
        assert b[name]["n"] == 1


def test_scoreboard_acierto_de_direccion_puntua_1_y_3(project, prodes, match):
    fx = [match(pred=(2, 1), real=(3, 0), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    assert b["P1"]["total"] == 1
    assert b["P2"]["total"] == 3
    for name in ("P1", "P2"):
        assert b[name]["dir"] == 1
        assert b[name]["exact"] == 0
        assert b[name]["fail"] == 0


def test_scoreboard_pronostico_errado_suma_cero_y_cuenta_fallado(project, prodes, match):
    fx = [match(pred=(2, 1), real=(0, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    for name in ("P1", "P2"):
        assert b[name]["total"] == 0
        assert b[name]["fail"] == 1
        assert b[name]["n"] == 1


def test_scoreboard_empate_clavado_es_exacto(project, prodes, match):
    fx = [match(pred=(1, 1), real=(1, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)
    assert (b["P1"]["total"], b["P2"]["total"]) == (3, 6)
    assert b["P1"]["exact"] == 1


def test_scoreboard_empate_con_otro_marcador_es_direccion(project, prodes, match):
    fx = [match(pred=(1, 1), real=(0, 0), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)
    assert (b["P1"]["total"], b["P2"]["total"]) == (1, 3)
    assert b["P1"]["dir"] == 1


# --------------------------------------------------------------------------
# (c) sin pronostico
# --------------------------------------------------------------------------

def test_scoreboard_sin_pronostico_cuenta_jugado_y_fallado(project, prodes, match):
    """pred=None: el partido se jugo igual -> n+1, fail+1, 0 puntos."""
    fx = [match(pred=None, real=(1, 0), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    for name in ("P1", "P2"):
        assert b[name]["total"] == 0
        assert b[name]["n"] == 1
        assert b[name]["fail"] == 1
        assert b[name]["exact"] == 0
        assert b[name]["dir"] == 0


# --------------------------------------------------------------------------
# (d) partidos no terminados
# --------------------------------------------------------------------------

def test_scoreboard_partido_no_empezado_no_cuenta(project, prodes, match):
    """now anterior al kickoff -> estado 'pre' -> ni puntos ni jugados."""
    fx = [match(pred=(2, 1), real=(2, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=GROUPS_DAY - timedelta(hours=1))

    for name in ("P1", "P2"):
        assert b[name]["total"] == 0
        assert b[name]["n"] == 0


def test_scoreboard_partido_en_curso_no_cuenta(project, prodes, match):
    """Dentro de la ventana de 120' de grupos el partido esta 'live'."""
    fx = [match(pred=(2, 1), real=(2, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=GROUPS_DAY + timedelta(minutes=90))

    for name in ("P1", "P2"):
        assert b[name]["total"] == 0
        assert b[name]["n"] == 0


def test_scoreboard_elim_usa_ventana_larga(project, prodes, ko_match):
    """A las 2 h un partido de eliminacion sigue 'live' (ventana de 210')."""
    fx = [ko_match(pred=(2, 1), real=(2, 1), load=(1, 1))]

    live = app_data.scoreboard(fx=fx, now=KO_DAY + timedelta(minutes=120))
    assert live["P1"]["n"] == 0

    done = app_data.scoreboard(fx=fx, now=KO_DAY + timedelta(minutes=211))
    assert done["P1"]["n"] == 1
    assert done["P1"]["elim"]["total"] == 3


def test_scoreboard_marcado_terminado_a_mano_cuenta_aunque_no_arranco(
        project, prodes, match):
    """data/finished.csv fuerza 'done' aunque `now` sea anterior al kickoff."""
    project.finished([("Spain", "Argentina")])
    fx = [match(home="Spain", away="Argentina", pred=(2, 1), real=(2, 1),
                load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=GROUPS_DAY - timedelta(days=2))

    assert b["P1"]["n"] == 1
    assert b["P1"]["total"] == 3


# --------------------------------------------------------------------------
# (e) sin resultado real
# --------------------------------------------------------------------------

def test_scoreboard_real_none_nunca_cuenta(project, prodes, match):
    """Sin resultado no hay nada que puntuar, ni siquiera como jugado."""
    fx = [match(pred=(2, 1), real=None, load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    for name in ("P1", "P2"):
        assert b[name]["total"] == 0
        assert b[name]["n"] == 0
        assert b[name]["fail"] == 0


def test_scoreboard_real_none_no_cuenta_ni_marcado_terminado(project, prodes, match):
    project.finished([("Spain", "Argentina")])
    fx = [match(home="Spain", away="Argentina", pred=(2, 1), real=None,
                load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)
    assert b["P1"]["n"] == 0


# --------------------------------------------------------------------------
# (f) split grupos / elim y totales combinados
# --------------------------------------------------------------------------

def test_scoreboard_separa_grupos_de_elim_por_fecha(project, prodes, match, ko_match):
    """`is_knockout(kickoff)` decide el sub-total: GROUPS_DAY vs KO_DAY."""
    fx = [
        match(home="Spain", away="Argentina", pred=(2, 1), real=(2, 1), load=(1, 1)),
        ko_match(home="Brazil", away="France", pred=(1, 0), real=(3, 0), load=(1, 1)),
    ]
    b = app_data.scoreboard(fx=fx, now=AFTER_KO)

    g, e = b["P1"]["grupos"], b["P1"]["elim"]
    assert (g["total"], g["n"], g["exact"], g["dir"], g["fail"]) == (3, 1, 1, 0, 0)
    assert (e["total"], e["n"], e["exact"], e["dir"], e["fail"]) == (1, 1, 0, 1, 0)

    g2, e2 = b["P2"]["grupos"], b["P2"]["elim"]
    assert (g2["total"], e2["total"]) == (6, 3)


def test_scoreboard_total_y_n_son_la_suma_de_ambas_etapas(project, prodes, match, ko_match):
    fx = [
        match(home="Spain", away="Argentina", pred=(2, 1), real=(2, 1), load=(1, 1)),
        match(home="Japan", away="Egypt", pred=(1, 0), real=(0, 2), load=(1, 1)),
        ko_match(home="Brazil", away="France", pred=(1, 0), real=(3, 0), load=(1, 1)),
        ko_match(home="Norway", away="Ghana", pred=None, real=(1, 1), load=(1, 1)),
    ]
    b = app_data.scoreboard(fx=fx, now=AFTER_KO)

    for name in ("P1", "P2"):
        d = b[name]
        for key in ("total", "n", "exact", "dir", "fail"):
            assert d[key] == d["grupos"][key] + d["elim"][key], (name, key)
        assert d["n"] == 4
        assert d["fail"] == 2       # el errado y el que no tiene pronostico

    assert b["P1"]["total"] == 3 + 0 + 1 + 0
    assert b["P2"]["total"] == 6 + 0 + 3 + 0


def test_scoreboard_solo_grupos_deja_elim_en_cero(project, prodes, match):
    fx = [match(pred=(2, 1), real=(2, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    assert b["P1"]["elim"] == {"total": 0, "n": 0, "exact": 0, "dir": 0, "fail": 0}
    assert b["P1"]["grupos"]["total"] == 3


# --------------------------------------------------------------------------
# forma del dict devuelto
# --------------------------------------------------------------------------

def test_scoreboard_devuelve_una_entrada_por_prode_con_su_scoring(project, prodes, match):
    fx = [match(pred=(2, 1), real=(2, 1), load=(1, 1))]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    assert list(b) == ["P1", "P2"]
    assert b["P1"]["scoring"] == (3, 1)
    assert b["P2"]["scoring"] == (6, 3)
    assert set(b["P1"]) == {"scoring", "grupos", "elim", "total", "n",
                            "exact", "dir", "fail"}


def test_scoreboard_con_fx_vacio_cae_al_fixture_de_disco(project, prodes):
    """Comportamiento actual de `fx = fx or fixture()`: una lista vacia es falsy,
    asi que scoreboard(fx=[]) NO significa "sin partidos" sino "leer el disco"."""
    project.results([])
    project.horarios([])
    project.pronosticos([])

    b = app_data.scoreboard(fx=[], now=AFTER_GROUPS)
    assert b["P1"]["n"] == 0 and b["P2"]["n"] == 0


def test_scoreboard_acumula_varios_partidos_de_la_misma_etapa(project, prodes, match):
    fx = [
        match(home="Spain", away="Argentina", pred=(2, 1), real=(2, 1), load=(1, 1)),
        match(home="Japan", away="Egypt", pred=(2, 0), real=(1, 0), load=(1, 1)),
        match(home="Norway", away="Ghana", pred=(0, 1), real=(2, 0), load=(1, 1)),
    ]
    b = app_data.scoreboard(fx=fx, now=AFTER_GROUPS)

    assert b["P1"]["total"] == 3 + 1 + 0
    assert b["P1"]["exact"] == 1
    assert b["P1"]["dir"] == 1
    assert b["P1"]["fail"] == 1
    assert b["P1"]["n"] == 3
