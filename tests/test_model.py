"""Tests del motor de prediccion: predict_match_v2 (score_matrix, dc_tau,
fit_iterative, load_results) y predict_match_v3.predict.

Todo corre con parametros SINTETICOS (un dict `p` con las mismas llaves que
devuelve fit_iterative) para no tocar el dataset real, que tarda segundos en
levantar y cambia todos los dias. Los unicos tests que leen disco son los de
load_results, y usan la fixture `project` con un results.csv de 3 filas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from prode.model import predict_match_v2 as v2
from prode.model import predict_match_v3 as v3


# --------------------------------------------------------------------------
# helpers / fixtures
# --------------------------------------------------------------------------

TEAMS = ["Argentina", "Brazil", "Chile"]


def make_params(alpha=(1.0, 1.0, 1.0), beta=(1.0, 1.0, 1.0), mu=1.30, gamma=1.35):
    """Dict con la forma exacta de lo que devuelve `fit_iterative`.

    Indices: 0=Argentina, 1=Brazil, 2=Chile. alpha alto = mejor ataque,
    beta bajo = mejor defensa (beta>1 significa que recibe mas que la media).
    """
    return dict(
        teams=pd.Index(TEAMS),
        tidx={t: i for i, t in enumerate(TEAMS)},
        alpha=np.array(alpha, dtype=float),
        beta=np.array(beta, dtype=float),
        gamma=float(gamma),
        mu=float(mu),
        ngames=np.array([50, 50, 50]),
    )


def flat_elo(rating=1500.0):
    return {t: float(rating) for t in TEAMS}


@pytest.fixture
def params():
    """Parametros parejos: los tres equipos son clones."""
    return make_params()


@pytest.fixture
def elo():
    return flat_elo()


@pytest.fixture
def results_csv(project, monkeypatch):
    """`project` + `predict_match_v2.DATA` apuntando a su results.csv."""
    monkeypatch.setattr(v2, "DATA", project.base / "data" / "results.csv")
    return project


def _round_robin(sched, date="2024-01-01", tournament="Friendly", neutral=True):
    """sched: [(home, away, hs, as_), ...] -> df listo para fit_iterative."""
    rows = [dict(date=date, home_team=h, away_team=a, home_score=hs, away_score=a_s,
                 tournament=tournament, city="X", country="Y", neutral=neutral)
            for h, a, hs, a_s in sched]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# Round robin de 4 equipos: todos juegan 3 partidos, misma fecha y mismo torneo
# => el peso (decay x amistoso) es identico para todos, asi la normalizacion de
# alpha/beta es una media simple y se puede assertear.
EVEN_RR = [("A", "B", 3, 0), ("A", "C", 2, 1), ("A", "D", 1, 1),
           ("B", "C", 0, 2), ("B", "D", 1, 0), ("C", "D", 2, 2)]
AS_OF = pd.Timestamp("2024-06-01")


# --------------------------------------------------------------------------
# score_matrix / dc_tau
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lh", [0.2, 0.5, 1.0, 1.4, 2.5, 4.0])
@pytest.mark.parametrize("la", [0.2, 1.0, 4.0])
def test_score_matrix_suma_uno_y_no_es_negativa(lh, la):
    """La matriz es una distribucion valida aun en los lambdas extremos."""
    M = v2.score_matrix(lh, la)
    assert M.sum() == pytest.approx(1.0, abs=1e-12)
    assert (M >= 0).all(), f"celda negativa con lh={lh} la={la}"


def test_score_matrix_shape_respeta_kmax():
    assert v2.score_matrix(1.2, 1.0).shape == (v2.MAX_GOALS + 1, v2.MAX_GOALS + 1)
    assert v2.score_matrix(1.2, 1.0, kmax=3).shape == (4, 4)
    # con kmax chico igual renormaliza a 1
    assert v2.score_matrix(1.2, 1.0, kmax=3).sum() == pytest.approx(1.0)


def test_score_matrix_lambda_mayor_carga_probabilidad_del_lado_del_local():
    M = v2.score_matrix(2.4, 0.7)
    p_home, p_draw, p_away = _outcome_probs(M)
    assert p_home > p_away
    assert p_home + p_draw + p_away == pytest.approx(1.0)


def test_score_matrix_lambdas_iguales_da_matriz_simetrica():
    M = v2.score_matrix(1.3, 1.3)
    assert M == pytest.approx(M.T, abs=1e-15)


def _outcome_probs(M):
    k = M.shape[0] - 1
    I, J = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
    return float(M[I > J].sum()), float(M[I == J].sum()), float(M[I < J].sum())


@pytest.mark.parametrize("i,j,esperado", [
    (0, 0, 1.0 - 1.5 * 1.2 * -0.10),
    (0, 1, 1.0 + 1.5 * -0.10),
    (1, 0, 1.0 + 1.2 * -0.10),
    (1, 1, 1.0 - (-0.10)),
])
def test_dc_tau_corrige_los_cuatro_marcadores_bajos(i, j, esperado):
    assert v2.dc_tau(i, j, 1.5, 1.2, -0.10) == pytest.approx(esperado)


@pytest.mark.parametrize("i,j", [(0, 2), (2, 0), (1, 2), (2, 1), (3, 3), (8, 8)])
def test_dc_tau_no_toca_marcadores_altos(i, j):
    assert v2.dc_tau(i, j, 1.5, 1.2, -0.10) == 1.0


def test_dc_tau_con_rho_cero_es_neutro():
    """rho=0 apaga la correccion: Dixon-Coles colapsa a Poisson independiente."""
    for i in range(3):
        for j in range(3):
            assert v2.dc_tau(i, j, 2.0, 1.1, 0.0) == 1.0


def test_dc_tau_rho_negativo_infla_el_cero_a_cero():
    """Con DC_RHO<0 el 0-0 y el 1-1 pesan mas que en Poisson puro."""
    assert v2.dc_tau(0, 0, 1.5, 1.2, v2.DC_RHO) > 1.0
    assert v2.dc_tau(1, 1, 1.5, 1.2, v2.DC_RHO) > 1.0
    assert v2.dc_tau(0, 1, 1.5, 1.2, v2.DC_RHO) < 1.0


# --------------------------------------------------------------------------
# predict_match_v3.predict
# --------------------------------------------------------------------------

def test_predict_probabilidades_1x2_suman_uno(params, elo):
    r = v3.predict("Argentina", "Chile", True, params, elo)
    assert r["p_home"] + r["p_draw"] + r["p_away"] == pytest.approx(1.0)
    assert r["M"].sum() == pytest.approx(1.0)


def test_predict_favorito_tiene_mas_chances_que_el_rival(params, elo):
    """alpha alto + beta bajo (Argentina) vs alpha bajo + beta alto (Chile)."""
    p = make_params(alpha=(1.6, 1.0, 0.7), beta=(0.6, 1.0, 1.4))
    r = v3.predict("Argentina", "Chile", True, p, elo)
    assert r["p_home"] > r["p_away"]
    assert r["lh"] > r["la"]


def test_predict_con_peso_elo_cero_usa_solo_las_fuerzas(params, elo):
    """w=0 -> los lambdas blendeados son exactamente los de fuerzas."""
    p = make_params(alpha=(1.6, 1.0, 0.7), beta=(0.6, 1.0, 1.4), mu=1.3)
    r = v3.predict("Argentina", "Chile", True, p, elo, w=0.0)
    assert r["lh"] == pytest.approx(1.3 * 1.6 * 1.4)
    assert r["la"] == pytest.approx(1.3 * 0.7 * 0.6)
    assert r["lh"] == pytest.approx(r["lh_f"])
    assert r["la"] == pytest.approx(r["la_f"])
    assert r["p_home"] > r["p_away"]


def test_predict_lambdas_de_fuerzas_ignoran_gamma_en_neutral(params, elo):
    """En cancha neutral gamma no entra: lh_f = mu*alpha_local*beta_visita."""
    p = make_params(alpha=(1.2, 1.0, 0.9), beta=(0.8, 1.0, 1.1), mu=1.25, gamma=1.5)
    r = v3.predict("Argentina", "Chile", True, p, elo)
    assert r["lh_f"] == pytest.approx(1.25 * 1.2 * 1.1)
    assert r["la_f"] == pytest.approx(1.25 * 0.9 * 0.8)


def test_predict_equipos_identicos_en_neutral_es_simetrico(params, elo):
    """Clones + cancha neutral + mismo Elo => el partido no tiene favorito."""
    r = v3.predict("Argentina", "Brazil", True, params, elo)
    assert r["p_home"] == pytest.approx(r["p_away"], abs=1e-12)
    assert r["lh"] == pytest.approx(r["la"])
    assert r["M"] == pytest.approx(r["M"].T, abs=1e-15)


def test_predict_es_determinista(params, elo):
    """Misma entrada -> misma salida bit a bit (no hay sampleo adentro)."""
    a = v3.predict("Argentina", "Chile", False, params, elo)
    b = v3.predict("Argentina", "Chile", False, params, elo)
    assert np.array_equal(a["M"], b["M"])
    assert np.array_equal(a["ev"], b["ev"])
    assert a["best"] == b["best"]
    assert (a["lh"], a["la"], a["p_home"], a["p_draw"], a["p_away"], a["best_ev"]) == \
           (b["lh"], b["la"], b["p_home"], b["p_draw"], b["p_away"], b["best_ev"])


def test_predict_best_esta_dentro_de_la_matriz_y_maximiza_el_ev(params, elo):
    """El marcador sugerido es el argmax de la matriz de puntaje esperado."""
    p = make_params(alpha=(1.6, 1.0, 0.7), beta=(0.6, 1.0, 1.4))
    r = v3.predict("Argentina", "Chile", True, p, elo)
    bi, bj = r["best"]
    k = r["M"].shape[0] - 1
    assert 0 <= bi <= k and 0 <= bj <= k
    assert r["ev"].shape == r["M"].shape
    assert r["best_ev"] == pytest.approx(float(r["ev"].max()))
    assert r["ev"][bi, bj] == r["ev"].max()


def test_predict_localia_favorece_mas_al_local_que_la_cancha_neutral(params, elo):
    """gamma>1 (+ HFA del Elo): jugar de local sube p_home y baja p_away."""
    p = make_params(alpha=(1.0, 1.1, 0.9), beta=(1.0, 0.9, 1.1), gamma=1.35)
    neutral = v3.predict("Brazil", "Chile", True, p, elo)
    local = v3.predict("Brazil", "Chile", False, p, elo)
    assert local["p_home"] > neutral["p_home"]
    assert local["p_away"] < neutral["p_away"]
    assert local["lh"] > neutral["lh"]


def test_predict_elo_mas_alto_sube_la_probabilidad_del_local(params):
    """Con fuerzas identicas, la diferencia de Elo tiene que romper el empate."""
    parejo = v3.predict("Argentina", "Brazil", True, params, flat_elo())
    favorito = v3.predict("Argentina", "Brazil", True, params,
                          {"Argentina": 1800.0, "Brazil": 1300.0, "Chile": 1500.0})
    assert favorito["p_home"] > parejo["p_home"]
    assert favorito["p_away"] < parejo["p_away"]


def test_predict_equipo_sin_elo_arranca_en_1500(params):
    """`elo.get(team, 1500.0)`: un equipo nuevo no rompe la prediccion."""
    r = v3.predict("Argentina", "Brazil", True, params, {})
    assert r["eh"] == 1500.0 and r["ea"] == 1500.0
    assert r["p_home"] == pytest.approx(r["p_away"], abs=1e-12)


def test_predict_equipo_desconocido_explota_con_keyerror(params, elo):
    """`predict` no valida: el CLI chequea tidx antes (ver main())."""
    with pytest.raises(KeyError):
        v3.predict("Wakanda", "Brazil", True, params, elo)


# --------------------------------------------------------------------------
# fit_iterative
# --------------------------------------------------------------------------

def test_fit_iterative_devuelve_las_llaves_que_usa_predict():
    p = v2.fit_iterative(_round_robin(EVEN_RR), AS_OF)
    for k in ("teams", "tidx", "alpha", "beta", "gamma", "mu", "ngames"):
        assert k in p
    assert list(p["teams"]) == ["A", "B", "C", "D"]
    assert p["tidx"] == {"A": 0, "B": 1, "C": 2, "D": 3}
    assert len(p["alpha"]) == len(p["beta"]) == 4
    assert p["ngames"].tolist() == [3, 3, 3, 3]
    assert p["mu"] > 0


def test_fit_iterative_normaliza_alpha_y_beta_a_media_uno():
    """Restriccion de identificabilidad: con pesos parejos, la media da 1."""
    p = v2.fit_iterative(_round_robin(EVEN_RR), AS_OF)
    assert p["alpha"].mean() == pytest.approx(1.0)
    assert p["beta"].mean() == pytest.approx(1.0)
    assert (p["alpha"] > 0).all() and (p["beta"] > 0).all()


def test_fit_iterative_separa_al_goleador_del_flojo():
    """A hace 6 goles y recibe 2; B hace 1 y recibe 5 -> alpha_A>alpha_B,
    beta_A<beta_B (beta alto = defensa mala)."""
    p = v2.fit_iterative(_round_robin(EVEN_RR), AS_OF)
    i = p["tidx"]
    assert p["alpha"][i["A"]] > p["alpha"][i["B"]]
    assert p["beta"][i["A"]] < p["beta"][i["B"]]


def test_fit_iterative_estima_gamma_mayor_a_uno_si_el_local_rinde_mas():
    """Con partidos NO neutrales donde gana el local, la localia queda > 1."""
    sched = [("A", "B", 3, 0), ("A", "C", 2, 1), ("B", "C", 2, 0),
             ("C", "A", 1, 0), ("B", "A", 2, 1), ("C", "B", 3, 1)]
    df = _round_robin(sched, tournament="FIFA World Cup", neutral=False)
    p = v2.fit_iterative(df, AS_OF)
    assert p["gamma"] > 1.0


def test_fit_iterative_con_dataset_todo_neutral_deja_gamma_en_cero():
    """Comportamiento ACTUAL: sin partidos no-neutrales el numerador de gamma
    es 0 y queda gamma=0 (ver notas: cuidado si se predice con neutral=False)."""
    p = v2.fit_iterative(_round_robin(EVEN_RR, neutral=True), AS_OF)
    assert p["gamma"] == 0.0


def test_fit_iterative_es_determinista():
    df = _round_robin(EVEN_RR)
    a = v2.fit_iterative(df, AS_OF)
    b = v2.fit_iterative(df, AS_OF)
    assert np.array_equal(a["alpha"], b["alpha"])
    assert np.array_equal(a["beta"], b["beta"])
    assert a["gamma"] == b["gamma"] and a["mu"] == b["mu"]


def test_fit_iterative_respeta_n_iter():
    """Menos iteraciones = otro punto del ajuste; el parametro se usa de verdad."""
    df = _round_robin(EVEN_RR)
    corto = v2.fit_iterative(df, AS_OF, n_iter=1)
    largo = v2.fit_iterative(df, AS_OF, n_iter=60)
    assert not np.allclose(corto["alpha"], largo["alpha"])


def test_fit_iterative_pesa_menos_los_amistosos():
    """La misma goleada mueve menos el modelo si fue amistoso (FRIENDLY_WEIGHT)."""
    assert v2.FRIENDLY_WEIGHT < 1.0
    base = _round_robin([("C", "D", 1, 1)], date="2024-05-01",
                        tournament="FIFA World Cup")
    goleada_amistosa = _round_robin([("A", "B", 5, 0)], date="2024-05-01",
                                    tournament="Friendly")
    goleada_oficial = _round_robin([("A", "B", 5, 0)], date="2024-05-01",
                                   tournament="FIFA World Cup")
    amistoso = v2.fit_iterative(
        pd.concat([goleada_amistosa, base], ignore_index=True), AS_OF)
    oficial = v2.fit_iterative(
        pd.concat([goleada_oficial, base], ignore_index=True), AS_OF)
    # mu = nivel global de goles: el 5-0 amistoso lo arrastra menos hacia arriba
    assert amistoso["mu"] < oficial["mu"]


def test_fit_iterative_pesa_menos_los_partidos_viejos():
    """Decay temporal: un 5-0 de hace 12 anios pesa menos que uno reciente."""
    viejo = _round_robin([("A", "B", 5, 0)], date="2012-01-01")
    nuevo = _round_robin([("A", "B", 5, 0)], date="2024-05-01")
    base = _round_robin([("C", "D", 1, 1)], date="2024-05-01")
    p_viejo = v2.fit_iterative(pd.concat([viejo, base], ignore_index=True), AS_OF)
    p_nuevo = v2.fit_iterative(pd.concat([nuevo, base], ignore_index=True), AS_OF)
    # el mu global (goles esperados) se corre menos cuando la goleada es vieja
    assert p_viejo["mu"] < p_nuevo["mu"]


# --------------------------------------------------------------------------
# load_results  (no leakage)
# --------------------------------------------------------------------------

def test_load_results_filtra_estricto_antes_de_as_of(results_csv):
    """`date < as_of`: el partido del mismo dia NO entra (nada de leakage)."""
    results_csv.results([
        {"date": "2024-01-01", "home_team": "A", "away_team": "B"},
        {"date": "2024-05-01", "home_team": "C", "away_team": "D"},
        {"date": "2024-05-02", "home_team": "E", "away_team": "F"},
    ])
    df = v2.load_results(as_of=pd.Timestamp("2024-05-02"))
    assert df["home_team"].tolist() == ["A", "C"]
    assert (df["date"] < pd.Timestamp("2024-05-02")).all()


def test_load_results_sin_as_of_trae_todo_ordenado_por_fecha(results_csv):
    results_csv.results([
        {"date": "2024-05-02", "home_team": "E", "away_team": "F"},
        {"date": "2024-01-01", "home_team": "A", "away_team": "B"},
        {"date": "2024-05-01", "home_team": "C", "away_team": "D"},
    ])
    df = v2.load_results()
    assert df["home_team"].tolist() == ["A", "C", "E"]
    assert df["date"].is_monotonic_increasing
    assert df.index.tolist() == [0, 1, 2]


def test_load_results_castea_neutral_a_bool(results_csv):
    results_csv.results([
        {"home_team": "A", "away_team": "B", "neutral": True},
        {"home_team": "C", "away_team": "D", "neutral": False},
    ])
    df = v2.load_results()
    assert df["neutral"].dtype == bool
    assert df["neutral"].tolist() == [True, False]


def test_load_results_descarta_partidos_sin_marcador(results_csv):
    """Los partidos futuros (marcador vacio) se caen; los goles quedan int."""
    results_csv.results([
        {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1},
        {"home_team": "C", "away_team": "D", "home_score": None, "away_score": None},
    ])
    df = v2.load_results()
    assert df["home_team"].tolist() == ["A"]
    assert df["home_score"].dtype.kind == "i"
    assert df["away_score"].dtype.kind == "i"


def test_load_results_completa_marcadores_desde_manual_results(results_csv):
    """manual_results.csv rellena lo que martj42 todavia no publico."""
    results_csv.results([
        {"date": "2026-06-11", "home_team": "Mexico", "away_team": "Poland",
         "home_score": None, "away_score": None},
    ])
    results_csv.manual_results([
        {"date": "2026-06-11", "home_team": "Mexico", "away_team": "Poland",
         "home_score": 3, "away_score": 2},
    ])
    df = v2.load_results()
    assert len(df) == 1
    assert (int(df.loc[0, "home_score"]), int(df.loc[0, "away_score"])) == (3, 2)


def test_load_results_no_pisa_un_marcador_oficial_con_el_manual(results_csv):
    results_csv.results([
        {"date": "2026-06-11", "home_team": "Mexico", "away_team": "Poland",
         "home_score": 1, "away_score": 0},
    ])
    results_csv.manual_results([
        {"date": "2026-06-11", "home_team": "Mexico", "away_team": "Poland",
         "home_score": 9, "away_score": 9},
    ])
    df = v2.load_results()
    assert (int(df.loc[0, "home_score"]), int(df.loc[0, "away_score"])) == (1, 0)


def test_load_results_alimenta_fit_iterative_y_predict(results_csv):
    """Smoke end-to-end con 6 partidos: csv -> fit -> predict, sin dataset real."""
    results_csv.results([
        {"date": "2024-01-01", "home_team": h, "away_team": a,
         "home_score": hs, "away_score": a_s}
        for h, a, hs, a_s in EVEN_RR
    ])
    df = v2.load_results(as_of=AS_OF)
    assert len(df) == 6
    p = v2.fit_iterative(df, AS_OF)
    r = v3.predict("A", "B", True, p, {"A": 1600.0, "B": 1400.0})
    assert r["p_home"] + r["p_draw"] + r["p_away"] == pytest.approx(1.0)
    assert r["p_home"] > r["p_away"]
