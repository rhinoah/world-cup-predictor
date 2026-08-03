"""Tests de app_data.fixture() y knockout_fixture(): armar los partidos.

Estas dos funciones no tenian NI UN test, y son las que deciden que ve el usuario
en pantalla. Se comprobo con mutation testing que la suite entera pasaba con
bugs como estos adentro:

  * `pens[0] > pens[1]` invertido -> avanza el que PERDIO la tanda de penales,
  * el tercer puesto tomando `winners` en vez de `losers` de las semis,
  * `sealed()` devolviendo siempre True -> el bracket muestra equipos de grupos
    que todavia no terminaron,
  * el filtro `date >= WC_START` fuera -> se mezclan Mundiales viejos,
  * `next_match` tomando el ultimo partido en vez del proximo.

Los ocho sobrevivian. Este archivo los mata.

Casi todo necesita una fase de grupos COMPLETA (los cruces de 16avos solo se
revelan cuando los 12 grupos cerraron), asi que `_grupos_completos` la genera
entera y determinista: dentro de cada grupo gana siempre el que esta antes en la
lista, con lo que las posiciones quedan 9/6/3/0 puntos sin empates que desempatar.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from prode.data import app_data
from prode.tournament import bracket, teams

# El torneo esta en el pasado, asi que todo da "done" contra el reloj real.
DIA_GRUPOS = "2026-06-15"
HORA_GRUPOS = "2026-06-15 16:00"

# round-robin de 4: el indice menor gana siempre
CRUCES = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]


def _grupos_completos(project, grupos=None, goles_del_tercero=None):
    """Escribe los partidos de grupos jugados y devuelve la lista de cruces.

    `grupos`: subconjunto de letras a completar (None = los 12).
    `goles_del_tercero`: {letra: goles} para desempatar los 12 terceros entre si,
    que si no quedan todos iguales y el orden de los 8 mejores seria arbitrario.
    """
    letras = list(grupos or teams.GROUPS)
    goles_del_tercero = goles_del_tercero or {}
    res, hor = [], []
    for g in letras:
        equipos = teams.GROUPS[g]
        for i, j in CRUCES:
            h, a = equipos[i], equipos[j]
            gh, ga = (1, 0)
            if (i, j) == (2, 3):                  # el partido que gana el 3ro
                gh = goles_del_tercero.get(g, 1)
            res.append({"date": DIA_GRUPOS, "home_team": h, "away_team": a,
                        "home_score": gh, "away_score": ga})
            hor.append({"home_team": h, "away_team": a, "kickoff_arg": HORA_GRUPOS})
    project.results(res)
    project.horarios(hor)
    return res


# --------------------------------------------------------------------------
# (a) fixture(): los partidos de grupos
# --------------------------------------------------------------------------
def test_fixture_sale_del_archivo_de_horarios_y_ordena_por_kickoff(project):
    project.results([{"home_team": "Mexico", "away_team": "South Africa"}])
    project.horarios([
        {"home_team": "Brazil", "away_team": "Haiti", "kickoff_arg": "2026-06-16 22:00"},
        {"home_team": "Mexico", "away_team": "South Africa", "kickoff_arg": "2026-06-15 16:00"},
    ])

    fx = app_data.fixture()

    assert [(m["home"], m["away"]) for m in fx] == [
        ("Mexico", "South Africa"), ("Brazil", "Haiti")]


def test_fixture_trae_el_resultado_del_dataset(project):
    project.results([{"home_team": "Mexico", "away_team": "South Africa",
                      "home_score": 3, "away_score": 1}])
    project.horarios([{"home_team": "Mexico", "away_team": "South Africa",
                       "kickoff_arg": HORA_GRUPOS}])

    assert app_data.fixture()[0]["real"] == (3, 1)


def test_fixture_ignora_partidos_de_otros_torneos(project):
    """`wc_matches` filtra por torneo Y por fecha: sin eso, un Mexico-Sudafrica
    amistoso de 2019 le pondria resultado a un partido del Mundial."""
    project.results([
        {"home_team": "Mexico", "away_team": "South Africa", "home_score": 9,
         "away_score": 0, "tournament": "Friendly", "date": "2019-03-01"},
    ])
    project.horarios([{"home_team": "Mexico", "away_team": "South Africa",
                       "kickoff_arg": HORA_GRUPOS}])

    assert app_data.fixture()[0]["real"] is None


def test_fixture_ignora_mundiales_anteriores(project):
    """El mismo torneo pero antes de WC_START: es el Mundial 2022, no este."""
    project.results([
        {"home_team": "Mexico", "away_team": "South Africa", "home_score": 9,
         "away_score": 0, "date": "2022-11-25"},
    ])
    project.horarios([{"home_team": "Mexico", "away_team": "South Africa",
                       "kickoff_arg": HORA_GRUPOS}])

    assert app_data.fixture()[0]["real"] is None


def test_fixture_marca_host_solo_a_los_anfitriones(project):
    project.results([])
    project.horarios([
        {"home_team": "Mexico", "away_team": "South Africa", "kickoff_arg": HORA_GRUPOS},
        {"home_team": "Brazil", "away_team": "Haiti", "kickoff_arg": "2026-06-16 16:00"},
    ])

    porhost = {m["home"]: m["host"] for m in app_data.fixture()}
    assert porhost == {"Mexico": True, "Brazil": False}


def test_fixture_trae_el_estado_con_el_override_manual(project):
    """`state` tiene que respetar finished.csv: si no, un partido marcado a mano
    como terminado no cuenta en la tabla de posiciones."""
    futuro = "2099-06-15 16:00"
    project.results([])
    project.horarios([{"home_team": "Mexico", "away_team": "South Africa",
                       "kickoff_arg": futuro}])
    project.finished([("Mexico", "South Africa")])

    assert app_data.fixture()[0]["state"] == "done"


def test_fixture_toma_el_pronostico_y_la_carga_de_cada_prode(project):
    project.results([])
    project.horarios([{"home_team": "Mexico", "away_team": "South Africa",
                       "kickoff_arg": HORA_GRUPOS}])
    project.pronosticos([{"home_team": "Mexico", "away_team": "South Africa",
                          "pred_home": 2, "pred_away": 1,
                          "load_gel": 1, "load_meli": 0}])

    m = app_data.fixture()[0]
    assert m["pred"] == (2, 1)
    assert m["load"] == (1, 0)


def test_fixture_tolera_un_pronostico_a_medio_cargar(project):
    """Media carga (pred_home si, pred_away vacio) hacia int(pd.NA) y volteaba la
    app entera con un TypeError que no decia de que fila era."""
    project.results([])
    project.horarios([{"home_team": "Mexico", "away_team": "South Africa",
                       "kickoff_arg": HORA_GRUPOS}])
    project.pronosticos([{"home_team": "Mexico", "away_team": "South Africa",
                          "pred_home": 2, "pred_away": None}])

    assert app_data.fixture()[0]["pred"] is None


# --------------------------------------------------------------------------
# (b) next_match / first_match_on
# --------------------------------------------------------------------------
def test_next_match_devuelve_el_mas_proximo_no_el_ultimo(match):
    """El bug real que reporto el usuario: el fixture no viene ordenado por hora
    y sin el sorted() la cuenta regresiva apuntaba al partido equivocado."""
    ahora = datetime(2026, 6, 15, 12, 0)
    fx = [match(home="Brazil", away="Haiti", kickoff=datetime(2026, 6, 15, 17, 30)),
          match(home="Mexico", away="South Africa", kickoff=datetime(2026, 6, 15, 14, 0))]

    assert app_data.next_match(now=ahora, fx=fx)["home"] == "Mexico"


def test_next_match_ignora_los_que_ya_empezaron(match):
    ahora = datetime(2026, 6, 15, 16, 0)
    fx = [match(kickoff=datetime(2026, 6, 15, 14, 0)),
          match(home="Brazil", away="Haiti", kickoff=datetime(2026, 6, 15, 22, 0))]

    assert app_data.next_match(now=ahora, fx=fx)["home"] == "Brazil"


def test_next_match_devuelve_none_si_no_queda_ninguno(match):
    fx = [match(kickoff=datetime(2026, 6, 15, 14, 0))]
    assert app_data.next_match(now=datetime(2099, 1, 1), fx=fx) is None


# --------------------------------------------------------------------------
# (c) knockout_fixture(): el cuadro de eliminacion
# --------------------------------------------------------------------------
def test_knockout_devuelve_los_32_cruces(project):
    _grupos_completos(project)
    ko = app_data.knockout_fixture()

    assert len(ko) == 32
    assert {m["match"] for m in ko} == set(bracket.MATCH_DT)


def test_knockout_no_revela_equipos_con_los_grupos_abiertos(project):
    """`sealed()`: mostrar el 1ro de un grupo que sigue jugando seria mentir."""
    _grupos_completos(project, grupos=["A"])          # solo A cerrado

    ko = {m["match"]: m for m in app_data.knockout_fixture()}
    definidos = [n for n, m in ko.items() if m["defined"]]

    assert definidos == [], f"se revelaron cruces con 11 grupos abiertos: {definidos}"


def test_knockout_revela_los_16avos_cuando_cerraron_los_12_grupos(project):
    _grupos_completos(project)

    ko = {m["match"]: m for m in app_data.knockout_fixture()}

    r32 = [ko[n] for n in range(73, 89)]
    assert all(m["defined"] for m in r32), "quedaron 16avos sin definir"
    # 32 equipos distintos: nadie puede estar en dos cruces
    equipos = [m["home"] for m in r32] + [m["away"] for m in r32]
    assert len(set(equipos)) == 32


def test_el_ganador_de_una_llave_avanza_a_la_siguiente(project):
    base = _grupos_completos(project)
    ko = {m["match"]: m for m in app_data.knockout_fixture()}
    m73, m74 = ko[73], ko[74]

    # M73 y M74 alimentan a M89
    project.results(base + [
        {"date": "2026-06-28", "home_team": m73["home"], "away_team": m73["away"],
         "home_score": 2, "away_score": 0},
        {"date": "2026-06-28", "home_team": m74["home"], "away_team": m74["away"],
         "home_score": 0, "away_score": 3}])

    ko2 = {m["match"]: m for m in app_data.knockout_fixture()}
    assert ko2[73]["winner"] == m73["home"]
    assert ko2[74]["winner"] == m74["away"]
    sa, sb = bracket.TREE[89]
    assert (ko2[89]["home"], ko2[89]["away"]) == (ko2[sa]["winner"], ko2[sb]["winner"])


def test_en_un_empate_avanza_el_que_gano_los_penales(project):
    """EL test que faltaba: invertir esta comparacion hacia avanzar al perdedor
    de la tanda y la suite entera seguia en verde."""
    base = _grupos_completos(project)
    ko = {m["match"]: m for m in app_data.knockout_fixture()}
    m73 = ko[73]

    project.results(base + [{"date": "2026-06-28", "home_team": m73["home"],
                             "away_team": m73["away"], "home_score": 1, "away_score": 1}])
    project.manual_results([{"date": "2026-06-28", "home_team": m73["home"],
                             "away_team": m73["away"], "home_score": 1, "away_score": 1,
                             "home_pens": 2, "away_pens": 4}])

    m = {x["match"]: x for x in app_data.knockout_fixture()}[73]
    assert m["pens"] == (2, 4)
    assert m["winner"] == m73["away"], "avanzo el que perdio los penales"


def test_un_empate_sin_penales_cargados_no_define_ganador(project):
    base = _grupos_completos(project)
    ko = {m["match"]: m for m in app_data.knockout_fixture()}
    m73 = ko[73]
    project.results(base + [{"date": "2026-06-28", "home_team": m73["home"],
                             "away_team": m73["away"], "home_score": 1, "away_score": 1}])

    m = {x["match"]: x for x in app_data.knockout_fixture()}[73]
    assert m["real"] == (1, 1)
    assert m["winner"] is None
    assert app_data.needs_pens(m), "tendria que pedir la tanda"


def _jugar_hasta_la_final(project, base):
    """Juega TODA la eliminacion (gana siempre el local 1-0) y devuelve el cuadro.

    Hace falta jugarla de verdad para llegar al partido por el tercer puesto: las
    etiquetas ("Perd. M101") son strings fijos y no distinguen si el codigo toma
    los perdedores o los ganadores de las semis."""
    jugados = list(base)
    for _ in range(6):                     # 16avos -> 8vos -> 4tos -> semis -> ...
        ko = {m["match"]: m for m in app_data.knockout_fixture()}
        nuevos = [{"date": bracket.MATCH_DT[n][:10], "home_team": m["home"],
                   "away_team": m["away"], "home_score": 1, "away_score": 0}
                  for n, m in ko.items()
                  if m["defined"] and m["real"] is None and n != bracket.THIRD_PLACE]
        if not nuevos:
            break
        jugados += nuevos
        project.results(jugados)
    return {m["match"]: m for m in app_data.knockout_fixture()}


def test_el_tercer_puesto_lo_juegan_los_PERDEDORES_de_las_semis(project):
    """Con `winners` en vez de `losers` el partido por el 3er puesto seria una
    final repetida. Las etiquetas no lo detectan: hay que jugar las semis."""
    assert bracket.THIRD_PLACE == 103
    ko = _jugar_hasta_la_final(project, _grupos_completos(project))

    semi1, semi2 = ko[101], ko[102]
    assert semi1["winner"] and semi2["winner"], "no se jugaron las semis"

    perdedores = {semi1["away"], semi2["away"]}          # gano siempre el local
    assert {ko[103]["home"], ko[103]["away"]} == perdedores
    # y sobre todo: NO son los que juegan la final
    assert {ko[103]["home"], ko[103]["away"]} & {ko[104]["home"], ko[104]["away"]} == set()


def test_la_final_la_juegan_los_ganadores_de_las_semis(project):
    ko = _jugar_hasta_la_final(project, _grupos_completos(project))
    assert {ko[104]["home"], ko[104]["away"]} == {ko[101]["winner"], ko[102]["winner"]}


def test_los_cruces_sin_definir_muestran_una_etiqueta_y_no_none(project):
    """La UI dibuja `a_label`: si viniera vacio, el cuadro quedaria en blanco."""
    _grupos_completos(project, grupos=["A"])

    for m in app_data.knockout_fixture():
        assert m["a_label"] and m["b_label"]
        assert not m["defined"]


def test_knockout_usa_las_fechas_del_bracket(project):
    _grupos_completos(project)
    for m in app_data.knockout_fixture():
        assert m["kickoff"].strftime("%Y-%m-%d %H:%M") == bracket.MATCH_DT[m["match"]]
