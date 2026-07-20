"""Tests de `scoring.py`: reglas de puntaje del prode y regla de decision EV.

El modulo existe para ser la fuente UNICA de verdad del puntaje (antes estaba
duplicado en app_data, liquidar y los dos backtests), asi que buena parte de
estos tests verifica justamente eso: que las cinco puertas de entrada den el
mismo numero en los mismos casos.
"""
from __future__ import annotations

import numpy as np
import pytest

import app_data
import backtest
import backtest_elo
import liquidar
import scoring
from predict_match_v2 import score_matrix

# ---------------------------------------------------------------- casos base
# (pred, real, outcome esperado). Cubre exacto (incluido 0-0 y empate),
# direccion (local / empate / visita) y fallado (incluye empate<->no empate).
CASES = [
    ((2, 1), (2, 1), "exact"),   # marcador clavado, local
    ((0, 0), (0, 0), "exact"),   # empate 0-0 clavado
    ((1, 1), (1, 1), "exact"),   # empate clavado
    ((0, 3), (0, 3), "exact"),   # marcador clavado, visita
    ((2, 1), (3, 0), "dir"),     # gano el local, otro marcador
    ((1, 0), (4, 2), "dir"),     # idem, goleada
    ((1, 1), (2, 2), "dir"),     # empate, otro marcador
    ((0, 2), (1, 3), "dir"),     # gano la visita, otro marcador
    ((2, 1), (1, 2), "miss"),    # direccion invertida
    ((1, 1), (2, 1), "miss"),    # empate pronosticado, gano el local
    ((2, 1), (1, 1), "miss"),    # local pronosticado, terminó empate
    ((0, 1), (1, 1), "miss"),    # visita pronosticada, terminó empate
]

EXPECTED_31 = {"exact": 3, "dir": 1, "miss": 0}
EXPECTED_63 = {"exact": 6, "dir": 3, "miss": 0}


def _ids(cases):
    return [f"{p[0]}-{p[1]}_vs_{r[0]}-{r[1]}_{o}" for p, r, o in cases]


# ------------------------------------------------------------------ points()

@pytest.mark.parametrize("pred,real,kind", CASES, ids=_ids(CASES))
def test_points_puntaje_por_defecto_3_1(pred, real, kind):
    """Con el puntaje clasico: 3 exacto / 1 direccion / 0 fallado."""
    assert scoring.points(pred, real) == EXPECTED_31[kind]


@pytest.mark.parametrize("pred,real,kind", CASES, ids=_ids(CASES))
def test_points_puntaje_6_3(pred, real, kind):
    """El puntaje es parametrizable: 6/3/0 escala los mismos resultados."""
    assert scoring.points(pred, real, 6, 3) == EXPECTED_63[kind]


def test_points_defaults_son_3_y_1():
    assert (scoring.DEFAULT_EXACT, scoring.DEFAULT_DIR) == (3, 1)
    assert scoring.points((2, 1), (2, 1)) == scoring.DEFAULT_EXACT
    assert scoring.points((2, 1), (3, 0)) == scoring.DEFAULT_DIR


@pytest.mark.parametrize("pred,real", [
    (None, (1, 0)),
    ((1, 0), None),
    (None, None),
])
def test_points_da_cero_si_falta_pronostico_o_resultado(pred, real):
    """Sin pronostico o sin resultado no hay puntos (no explota)."""
    assert scoring.points(pred, real) == 0
    assert scoring.points(pred, real, 6, 3) == 0


def test_points_devuelve_int_python():
    assert isinstance(scoring.points((1, 0), (1, 0)), int)
    assert isinstance(scoring.points((1, 0), (0, 1)), int)


# --------------------------------------------- consistencia entre los modulos

@pytest.mark.parametrize("pred,real,kind", CASES, ids=_ids(CASES))
def test_todas_las_implementaciones_dan_el_mismo_puntaje(pred, real, kind):
    """La razon de ser del modulo: cinco puertas de entrada, un solo numero."""
    ph, pa = pred
    rh, ra = real
    esperado = EXPECTED_31[kind]
    assert scoring.points(pred, real) == esperado
    assert app_data._points(ph, pa, rh, ra, 3, 1) == esperado
    assert liquidar.prode_points(ph, pa, rh, ra) == esperado
    assert backtest.prode_points(pred, real) == esperado
    assert backtest_elo.prode_points(pred, real) == esperado


def test_los_backtests_reexportan_la_misma_funcion():
    """No son copias: `prode_points` es literalmente `scoring.points`."""
    assert backtest.prode_points is scoring.points
    assert backtest_elo.prode_points is scoring.points


@pytest.mark.parametrize("pred,real,kind", CASES, ids=_ids(CASES))
def test_app_data_points_propaga_el_puntaje_custom(pred, real, kind):
    """`app_data._points` toma (exact, direction) del prode, no los defaults."""
    ph, pa = pred
    rh, ra = real
    assert app_data._points(ph, pa, rh, ra, 6, 3) == EXPECTED_63[kind]


def test_liquidar_prode_points_usa_siempre_el_puntaje_por_defecto():
    """liquidar no parametriza el puntaje: siempre 3/1/0."""
    assert liquidar.prode_points(2, 1, 2, 1) == 3
    assert liquidar.prode_points(2, 1, 3, 0) == 1
    assert liquidar.prode_points(2, 1, 0, 1) == 0


# ----------------------------------------------------------------- outcome()

@pytest.mark.parametrize("pred,real,kind", CASES, ids=_ids(CASES))
def test_outcome_clasifica_exacto_direccion_y_fallado(pred, real, kind):
    assert scoring.outcome(pred, real) == kind


@pytest.mark.parametrize("pred,real", [
    (None, (1, 0)),
    ((1, 0), None),
    (None, None),
])
def test_outcome_es_none_si_falta_pred_o_real(pred, real):
    """None (no 'miss'): "no jugado / no cargado" no es lo mismo que errar."""
    assert scoring.outcome(pred, real) is None


def test_outcome_el_exacto_gana_sobre_la_direccion():
    """Un marcador clavado nunca se reporta como 'dir'."""
    assert scoring.outcome((3, 1), (3, 1)) == "exact"
    assert scoring.outcome((3, 1), (2, 1)) == "dir"


# ---------------------------------------------------------------- ev_ratio()

def test_ev_ratio_por_defecto_es_2():
    """3/1 -> el exacto vale 2 aciertos de direccion EXTRA (el viejo hardcode)."""
    assert scoring.ev_ratio() == 2.0
    assert scoring.ev_ratio(3, 1) == 2.0


def test_ev_ratio_6_3_es_1_no_2():
    """HALLAZGO: 6/3 NO es equivalente a 3/1 para la regla EV (ratio 1 vs 2)."""
    assert scoring.ev_ratio(6, 3) == 1.0
    assert scoring.ev_ratio(6, 3) != scoring.ev_ratio(3, 1)


@pytest.mark.parametrize("exact,direction,ratio", [
    (3, 1, 2.0),
    (6, 3, 1.0),
    (1, 1, 0.0),    # el exacto no premia nada extra
    (5, 1, 4.0),
    (2, 1, 1.0),    # mismo ratio que 6/3
])
def test_ev_ratio_tabla(exact, direction, ratio):
    assert scoring.ev_ratio(exact, direction) == pytest.approx(ratio)


# ------------------------------------------------------------ outcome_probs()

LAMBDAS = [(1.5, 1.2), (2.1, 0.7), (1.0, 1.0), (0.9, 1.6), (1.3, 1.25)]


@pytest.mark.parametrize("lh,la", LAMBDAS)
def test_outcome_probs_suma_uno(lh, la):
    p_home, p_draw, p_away = scoring.outcome_probs(score_matrix(lh, la))
    assert p_home + p_draw + p_away == pytest.approx(1.0, abs=1e-9)
    assert all(0.0 <= p <= 1.0 for p in (p_home, p_draw, p_away))


@pytest.mark.parametrize("lh,la", LAMBDAS)
def test_outcome_probs_coincide_con_la_suma_manual_de_celdas(lh, la):
    M = score_matrix(lh, la)
    k = M.shape[0]
    esperado_home = sum(M[i, j] for i in range(k) for j in range(k) if i > j)
    esperado_draw = sum(M[i, i] for i in range(k))
    esperado_away = sum(M[i, j] for i in range(k) for j in range(k) if i < j)
    p_home, p_draw, p_away = scoring.outcome_probs(M)
    assert p_home == pytest.approx(esperado_home)
    assert p_draw == pytest.approx(esperado_draw)
    assert p_away == pytest.approx(esperado_away)


def test_outcome_probs_favorece_al_equipo_con_mas_lambda():
    p_home, _, p_away = scoring.outcome_probs(score_matrix(2.1, 0.7))
    assert p_home > p_away
    p_home, _, p_away = scoring.outcome_probs(score_matrix(0.9, 1.6))
    assert p_away > p_home


def test_outcome_probs_simetrico_si_lambdas_iguales():
    p_home, _, p_away = scoring.outcome_probs(score_matrix(1.4, 1.4))
    assert p_home == pytest.approx(p_away)


# -------------------------------------------------------------- ev_matrix()

@pytest.mark.parametrize("lh,la", LAMBDAS)
def test_ev_matrix_devuelve_ev_y_las_tres_probabilidades(lh, la):
    M = score_matrix(lh, la)
    out = scoring.ev_matrix(M)
    assert len(out) == 4
    ev, p_home, p_draw, p_away = out
    assert ev.shape == M.shape
    assert (p_home, p_draw, p_away) == scoring.outcome_probs(M)


@pytest.mark.parametrize("exact,direction", [(3, 1), (6, 3)])
def test_ev_matrix_es_ratio_por_p_marcador_mas_p_direccion(exact, direction):
    """EV(i,j) = ratio * P(i-j) + P(direccion de i-j), celda por celda."""
    M = score_matrix(1.5, 1.2)
    ev, p_home, p_draw, p_away = scoring.ev_matrix(M, exact, direction)
    ratio = scoring.ev_ratio(exact, direction)
    k = M.shape[0]
    for i in range(k):
        for j in range(k):
            pdir = p_home if i > j else (p_draw if i == j else p_away)
            assert ev[i, j] == pytest.approx(ratio * M[i, j] + pdir)


def test_ev_matrix_con_ratio_cero_es_solo_la_probabilidad_de_direccion():
    """Si exacto == direccion, clavar el marcador no aporta nada extra."""
    M = score_matrix(1.5, 1.2)
    ev, p_home, p_draw, p_away = scoring.ev_matrix(M, 1, 1)
    assert ev[2, 1] == pytest.approx(p_home)
    assert ev[1, 1] == pytest.approx(p_draw)
    assert ev[0, 1] == pytest.approx(p_away)


# ------------------------------------------ best_ev_score vs most_likely_score

def test_most_likely_score_es_el_argmax_de_la_matriz():
    M = score_matrix(1.5, 1.2)
    i, j = scoring.most_likely_score(M)
    assert M[i, j] == pytest.approx(M.max())
    assert (i, j) == (1, 1)


def test_best_ev_difiere_del_mas_probable_ahi_esta_la_gracia():
    """1.5 vs 1.2: el marcador mas probable es el empate 1-1, pero conviene 2-1."""
    M = score_matrix(1.5, 1.2)
    assert scoring.most_likely_score(M) == (1, 1)
    assert scoring.best_ev_score(M) == (2, 1)


@pytest.mark.parametrize("lh,la", LAMBDAS)
def test_best_ev_score_maximiza_el_ev_incluso_contra_el_mas_probable(lh, la):
    M = score_matrix(lh, la)
    ev, *_ = scoring.ev_matrix(M)
    bi, bj = scoring.best_ev_score(M)
    mi, mj = scoring.most_likely_score(M)
    assert ev[bi, bj] == pytest.approx(ev.max())
    assert ev[bi, bj] >= ev[mi, mj]


def test_best_ev_score_puede_cambiar_segun_el_puntaje_del_prode():
    """HALLAZGO documentado: 3/1 y 6/3 pueden sugerir marcadores distintos."""
    M = score_matrix(1.3, 1.25)
    assert scoring.best_ev_score(M, 3, 1) == (1, 1)
    assert scoring.best_ev_score(M, 6, 3) == (1, 0)


def test_best_ev_score_con_ratio_enorme_converge_al_mas_probable():
    """Si el exacto paga muchisimo, la regla EV degenera en 'jugar el modal'."""
    M = score_matrix(1.5, 1.2)
    assert scoring.best_ev_score(M, 101, 1) == scoring.most_likely_score(M)


def test_best_ev_score_con_ratio_cero_juega_la_direccion_mas_probable():
    """Sin premio extra por el exacto, alcanza con caer en la direccion top."""
    M = score_matrix(1.5, 1.2)
    p_home, p_draw, p_away = scoring.outcome_probs(M)
    assert p_home == max(p_home, p_draw, p_away)
    i, j = scoring.best_ev_score(M, 1, 1)
    assert i > j                       # elige una victoria local...
    assert (i, j) == (1, 0)            # ...la primera celda en orden row-major


def test_best_ev_score_y_most_likely_devuelven_ints_python():
    M = score_matrix(1.5, 1.2)
    for par in (scoring.best_ev_score(M), scoring.most_likely_score(M)):
        assert all(isinstance(x, int) and not isinstance(x, np.integer) for x in par)


# -------------------------------------------------------------------- modal()

@pytest.mark.parametrize("rel,nombre", [
    (lambda i, j: i > j, "local"),
    (lambda i, j: i == j, "empate"),
    (lambda i, j: i < j, "visita"),
])
def test_modal_respeta_la_direccion_pedida(rel, nombre):
    M = score_matrix(1.5, 1.2)
    ev, *_ = scoring.ev_matrix(M)
    i, j, p, e = scoring.modal(M, ev, rel)
    assert rel(i, j), f"{i}-{j} no cae en la direccion {nombre}"
    assert p == pytest.approx(M[i, j])
    assert e == pytest.approx(ev[i, j])


@pytest.mark.parametrize("rel", [
    lambda i, j: i > j,
    lambda i, j: i == j,
    lambda i, j: i < j,
])
def test_modal_es_el_marcador_mas_probable_dentro_de_la_direccion(rel):
    M = score_matrix(1.8, 1.1)
    ev, *_ = scoring.ev_matrix(M)
    i, j, p, _ = scoring.modal(M, ev, rel)
    k = M.shape[0]
    mejor = max(M[a, b] for a in range(k) for b in range(k) if rel(a, b))
    assert p == pytest.approx(mejor)


def test_modal_valores_concretos_por_direccion():
    """1.5 vs 1.2: 2-1 el local, 1-1 el empate, 1-2 la visita."""
    M = score_matrix(1.5, 1.2)
    ev, *_ = scoring.ev_matrix(M)
    assert scoring.modal(M, ev, lambda i, j: i > j)[:2] == (2, 1)
    assert scoring.modal(M, ev, lambda i, j: i == j)[:2] == (1, 1)
    assert scoring.modal(M, ev, lambda i, j: i < j)[:2] == (1, 2)


def test_modal_del_empate_coincide_con_el_mas_probable_de_la_diagonal():
    M = score_matrix(2.1, 0.7)
    ev, *_ = scoring.ev_matrix(M)
    i, j, p, _ = scoring.modal(M, ev, lambda a, b: a == b)
    assert i == j
    assert p == pytest.approx(max(M[d, d] for d in range(M.shape[0])))


def test_modal_de_la_direccion_ganadora_coincide_con_best_ev_score():
    """Con 3/1 la sugerencia global sale de la direccion mas probable."""
    M = score_matrix(1.5, 1.2)
    ev, *_ = scoring.ev_matrix(M)
    i, j, _, _ = scoring.modal(M, ev, lambda a, b: a > b)
    assert (i, j) == scoring.best_ev_score(M)
