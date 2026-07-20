"""Tests de `elo.py`.

Cubre las cuatro piezas del modulo: el K por tipo de torneo, el multiplicador
por goleada, el recorrido cronologico de `compute_elo` (sin leakage y con el
invariante de suma cero) y la mezcla `blended_lambdas` entre fuerzas y Elo.
"""
from __future__ import annotations

import pandas as pd
import pytest

import elo

RESULT_COLS = ["date", "home_team", "away_team", "home_score", "away_score",
               "neutral", "tournament"]


def make_df(rows):
    """DataFrame minimo con la forma del dataset martj42 (defaults completados)."""
    out = []
    for r in rows:
        row = {"date": "2026-06-15", "home_score": 1, "away_score": 0,
               "neutral": True, "tournament": "FIFA World Cup"}
        row.update(r)
        out.append(row)
    return pd.DataFrame(out, columns=RESULT_COLS)


# --------------------------------------------------------------------------
# k_factor
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tournament, expected", [
    ("Friendly", 20.0),
    ("FRIENDLY", 20.0),
    ("friendly", 20.0),
    ("FIFA World Cup", 60.0),
    ("fifa world cup", 60.0),
    ("FIFA World Cup qualification", 35.0),
    ("UEFA Euro qualification", 35.0),
    ("UEFA Euro", 50.0),
    ("Copa América", 50.0),
    ("African Cup of Nations", 50.0),
    ("AFC Asian Cup", 50.0),
    ("CONCACAF Gold Cup", 50.0),
    ("UEFA Nations League", 50.0),
    ("Confederations Cup", 50.0),
    ("Kirin Cup", 40.0),
    ("Baltic Cup", 40.0),
])
def test_k_factor_por_torneo(tournament, expected):
    assert elo.k_factor(tournament) == expected


def test_k_factor_es_case_insensitive():
    """Da igual como venga escrito el torneo en el CSV."""
    assert elo.k_factor("CoPa AmErIcA") == elo.k_factor("copa america") == 50.0
    assert elo.k_factor("UEFA NATIONS LEAGUE") == 50.0


def test_k_factor_amistoso_gana_sobre_las_demas_reglas():
    """El chequeo de 'friendly' es el primero: un amistoso siempre vale 20."""
    assert elo.k_factor("Friendly (World Cup warm-up)") == 20.0


def test_k_factor_clasificatorias_no_valen_como_mundial():
    """'world cup' + 'qual' cae en la rama de clasificatorias, no en la de 60."""
    assert elo.k_factor("FIFA World Cup qualification") == 35.0
    assert elo.k_factor("FIFA World Cup") == 60.0


def test_k_factor_valor_desconocido_usa_default():
    assert elo.k_factor(None) == 40.0
    assert elo.k_factor(float("nan")) == 40.0


# --------------------------------------------------------------------------
# goal_mult
# --------------------------------------------------------------------------

@pytest.mark.parametrize("gd", [0, 1, -1])
def test_goal_mult_diferencia_chica_es_neutra(gd):
    assert elo.goal_mult(gd) == 1.0


@pytest.mark.parametrize("gd", [2, -2])
def test_goal_mult_dos_goles_vale_uno_y_medio(gd):
    assert elo.goal_mult(gd) == 1.5


@pytest.mark.parametrize("gd", [3, 4, 5, 6, 7, 10])
def test_goal_mult_formula_desde_tres_goles(gd):
    """Con d>=3 el multiplicador es (11+d)/8."""
    assert elo.goal_mult(gd) == (11.0 + gd) / 8.0
    assert elo.goal_mult(-gd) == (11.0 + gd) / 8.0


def test_goal_mult_es_creciente():
    vals = [elo.goal_mult(d) for d in range(0, 9)]
    assert vals == sorted(vals)
    assert vals[0] == vals[1] == 1.0


def test_goal_mult_usa_valor_absoluto():
    assert elo.goal_mult(4) == elo.goal_mult(-4)


# --------------------------------------------------------------------------
# compute_elo
# --------------------------------------------------------------------------

def test_compute_elo_primera_aparicion_arranca_en_1500():
    """El Elo PRE de la primera aparicion de cada equipo es 1500 exacto."""
    df = make_df([
        {"date": "2026-06-01", "home_team": "Argentina", "away_team": "Brazil"},
        {"date": "2026-06-05", "home_team": "Spain", "away_team": "Argentina"},
    ])
    out, _ = elo.compute_elo(df)
    assert out.loc[0, "elo_home_pre"] == 1500.0     # Argentina debuta
    assert out.loc[0, "elo_away_pre"] == 1500.0     # Brazil debuta
    assert out.loc[1, "elo_home_pre"] == 1500.0     # Spain debuta recien aca
    assert out.loc[1, "elo_away_pre"] != 1500.0     # Argentina ya jugo


def test_compute_elo_no_tiene_leakage_del_propio_partido():
    """El pre-partido de la fila N es exactamente el Elo final tras la fila N-1."""
    rows = [
        {"date": "2026-06-01", "home_team": "Argentina", "away_team": "Brazil",
         "home_score": 2, "away_score": 0},
        {"date": "2026-06-05", "home_team": "Argentina", "away_team": "Spain",
         "home_score": 0, "away_score": 1},
    ]
    parcial, elo_tras_uno = elo.compute_elo(make_df(rows[:1]))
    total, _ = elo.compute_elo(make_df(rows))
    assert total.loc[1, "elo_home_pre"] == pytest.approx(elo_tras_uno["Argentina"])
    # y el rating final del primer partido no depende de lo que pase despues
    assert parcial.loc[0, "elo_home_pre"] == total.loc[0, "elo_home_pre"] == 1500.0


def test_compute_elo_ordena_cronologicamente():
    """Aunque el df venga desordenado, el recorrido es por fecha ascendente."""
    df = make_df([
        {"date": "2026-06-20", "home_team": "Spain", "away_team": "Argentina"},
        {"date": "2026-06-01", "home_team": "Argentina", "away_team": "Brazil"},
        {"date": "2026-06-10", "home_team": "Brazil", "away_team": "Spain"},
    ])
    out, _ = elo.compute_elo(df)
    assert list(out["date"]) == ["2026-06-01", "2026-06-10", "2026-06-20"]
    # el partido mas viejo es el unico con los dos equipos en 1500
    assert out.loc[0, "elo_home_pre"] == out.loc[0, "elo_away_pre"] == 1500.0
    assert out.loc[2, "elo_home_pre"] != 1500.0
    assert out.loc[2, "elo_away_pre"] != 1500.0


def test_compute_elo_es_de_suma_cero():
    """Cada partido suma +delta al local y -delta al visitante: sum(elo-1500)=0."""
    df = make_df([
        {"date": "2026-06-01", "home_team": "Argentina", "away_team": "Brazil",
         "home_score": 3, "away_score": 1},
        {"date": "2026-06-04", "home_team": "Spain", "away_team": "Argentina",
         "home_score": 0, "away_score": 0, "tournament": "Friendly"},
        {"date": "2026-06-08", "home_team": "Brazil", "away_team": "Japan",
         "home_score": 5, "away_score": 0, "neutral": False},
        {"date": "2026-06-12", "home_team": "Japan", "away_team": "Spain",
         "home_score": 1, "away_score": 2,
         "tournament": "FIFA World Cup qualification"},
        {"date": "2026-06-16", "home_team": "Argentina", "away_team": "Japan",
         "home_score": 2, "away_score": 2, "neutral": False},
    ])
    _, ratings = elo.compute_elo(df)
    assert set(ratings) == {"Argentina", "Brazil", "Spain", "Japan"}
    assert sum(r - 1500.0 for r in ratings.values()) == pytest.approx(0.0, abs=1e-9)


def test_compute_elo_suma_cero_tambien_con_muchos_partidos():
    teams = ["Argentina", "Brazil", "Spain", "Japan", "Nigeria", "Canada"]
    rows = []
    day = 1
    for i, h in enumerate(teams):
        for j, a in enumerate(teams):
            if i >= j:
                continue
            rows.append({"date": f"2026-06-{day:02d}", "home_team": h,
                         "away_team": a, "home_score": (i + j) % 4,
                         "away_score": j % 3, "neutral": (i + j) % 2 == 0})
            day += 1
    _, ratings = elo.compute_elo(make_df(rows))
    assert len(ratings) == len(teams)
    assert sum(r - 1500.0 for r in ratings.values()) == pytest.approx(0.0, abs=1e-9)


def test_compute_elo_ganar_sube_y_perder_baja():
    df = make_df([{"date": "2026-06-01", "home_team": "Argentina",
                   "away_team": "Brazil", "home_score": 1, "away_score": 0}])
    _, ratings = elo.compute_elo(df)
    assert ratings["Argentina"] > 1500.0
    assert ratings["Brazil"] < 1500.0
    assert ratings["Argentina"] - 1500.0 == pytest.approx(1500.0 - ratings["Brazil"])


def test_compute_elo_visitante_ganador_sube():
    """Ganar de visitante tambien suma (y mas, por la ventaja de localia)."""
    df_neutral = make_df([{"date": "2026-06-01", "home_team": "Argentina",
                           "away_team": "Brazil", "home_score": 0,
                           "away_score": 1, "neutral": True}])
    df_visita = make_df([{"date": "2026-06-01", "home_team": "Argentina",
                          "away_team": "Brazil", "home_score": 0,
                          "away_score": 1, "neutral": False}])
    _, r_neutral = elo.compute_elo(df_neutral)
    _, r_visita = elo.compute_elo(df_visita)
    assert r_neutral["Brazil"] > 1500.0
    assert r_visita["Brazil"] > r_neutral["Brazil"]


def test_compute_elo_empate_entre_iguales_en_neutral_no_mueve_nada():
    """Con Elos iguales y sin localia la expectativa es 0.5: delta = 0."""
    df = make_df([{"date": "2026-06-01", "home_team": "Argentina",
                   "away_team": "Brazil", "home_score": 1, "away_score": 1,
                   "neutral": True}])
    _, ratings = elo.compute_elo(df)
    assert ratings["Argentina"] == pytest.approx(1500.0)
    assert ratings["Brazil"] == pytest.approx(1500.0)


def test_compute_elo_empate_de_local_castiga_al_local():
    """Con localia el local era favorito: empatar le baja el rating."""
    df = make_df([{"date": "2026-06-01", "home_team": "Argentina",
                   "away_team": "Brazil", "home_score": 1, "away_score": 1,
                   "neutral": False}])
    _, ratings = elo.compute_elo(df)
    assert ratings["Argentina"] < 1500.0
    assert ratings["Brazil"] > 1500.0


def test_compute_elo_goleada_mueve_mas_que_triunfo_ajustado():
    def delta(hs, as_):
        _, r = elo.compute_elo(make_df([
            {"date": "2026-06-01", "home_team": "Argentina",
             "away_team": "Brazil", "home_score": hs, "away_score": as_}]))
        return r["Argentina"] - 1500.0

    assert delta(1, 0) < delta(3, 0) < delta(6, 0)


def test_compute_elo_amistoso_pesa_menos_que_mundial():
    def delta(tournament):
        _, r = elo.compute_elo(make_df([
            {"date": "2026-06-01", "home_team": "Argentina",
             "away_team": "Brazil", "home_score": 1, "away_score": 0,
             "tournament": tournament}]))
        return r["Argentina"] - 1500.0

    amistoso = delta("Friendly")
    mundial = delta("FIFA World Cup")
    assert 0 < amistoso < mundial
    assert mundial == pytest.approx(amistoso * 3.0)   # K 60 vs K 20


def test_compute_elo_agrega_columnas_y_no_muta_el_original():
    df = make_df([
        {"date": "2026-06-05", "home_team": "Spain", "away_team": "Argentina"},
        {"date": "2026-06-01", "home_team": "Argentina", "away_team": "Brazil"},
    ])
    original = df.copy()
    out, ratings = elo.compute_elo(df)
    assert "elo_home_pre" in out.columns and "elo_away_pre" in out.columns
    assert "elo_home_pre" not in df.columns
    pd.testing.assert_frame_equal(df, original)
    assert isinstance(ratings, dict)


def test_compute_elo_con_dataset_vacio():
    out, ratings = elo.compute_elo(make_df([]))
    assert len(out) == 0
    assert ratings == {}


# --------------------------------------------------------------------------
# blended_lambdas
# --------------------------------------------------------------------------

def _elo_lambdas(elo_h, elo_a, neutral, c=elo.C_SUPREMACY, tg=elo.TOTAL_GOALS):
    """Reimplementacion directa de los lambdas puros del Elo (referencia)."""
    dr = elo_h + (0.0 if neutral else elo.HFA) - elo_a
    sup = dr / c
    return max(tg / 2.0 + sup / 2.0, 0.15), max(tg / 2.0 - sup / 2.0, 0.15)


def test_blended_lambdas_w_cero_devuelve_las_fuerzas():
    """w=0 -> el Elo no participa: salen los lambdas del modelo de fuerzas."""
    lh, la = elo.blended_lambdas(1.37, 0.82, 1900.0, 1400.0, True, 0.0)
    assert (lh, la) == (1.37, 0.82)


def test_blended_lambdas_w_cero_ignora_el_elo():
    a = elo.blended_lambdas(1.37, 0.82, 1900.0, 1400.0, True, 0.0)
    b = elo.blended_lambdas(1.37, 0.82, 1200.0, 1800.0, False, 0.0)
    assert a == b


def test_blended_lambdas_w_uno_devuelve_los_lambdas_del_elo():
    lh, la = elo.blended_lambdas(1.37, 0.82, 1700.0, 1500.0, True, 1.0)
    esp_h, esp_a = _elo_lambdas(1700.0, 1500.0, True)
    assert lh == pytest.approx(esp_h)
    assert la == pytest.approx(esp_a)
    # con 200 puntos de ventaja: 1 gol de supremacia esperada sobre 2.60 totales
    assert lh == pytest.approx(1.80)
    assert la == pytest.approx(0.80)


def test_blended_lambdas_w_uno_ignora_las_fuerzas():
    a = elo.blended_lambdas(1.37, 0.82, 1700.0, 1500.0, True, 1.0)
    b = elo.blended_lambdas(3.90, 0.10, 1700.0, 1500.0, True, 1.0)
    assert a == pytest.approx(b)


def test_blended_lambdas_conserva_los_goles_totales_sin_piso():
    """Los lambdas puros del Elo suman TOTAL_GOALS mientras no toquen el piso."""
    lh, la = elo.blended_lambdas(1.0, 1.0, 1650.0, 1500.0, True, 1.0)
    assert lh + la == pytest.approx(elo.TOTAL_GOALS)


def test_blended_lambdas_es_intermedio_con_w_medio():
    lh_f, la_f = 1.20, 1.10
    lh, la = elo.blended_lambdas(lh_f, la_f, 1800.0, 1500.0, True, 0.5)
    esp_h, esp_a = _elo_lambdas(1800.0, 1500.0, True)
    assert lh == pytest.approx((lh_f * esp_h) ** 0.5)   # media geometrica
    assert la == pytest.approx((la_f * esp_a) ** 0.5)
    assert lh_f < lh < esp_h
    assert esp_a < la < la_f


@pytest.mark.parametrize("w", [0.25, 0.5, 0.75, 1.0])
def test_blended_lambdas_monotonia_en_elo_local(w):
    """Mas Elo local -> mas lambda local y menos lambda visitante."""
    lhs, las = [], []
    for elo_h in (1300.0, 1450.0, 1600.0, 1750.0, 1900.0):
        lh, la = elo.blended_lambdas(1.30, 1.10, elo_h, 1500.0, True, w)
        lhs.append(lh)
        las.append(la)
    assert lhs == sorted(lhs) and lhs[0] < lhs[-1]
    assert las == sorted(las, reverse=True) and las[0] > las[-1]


def test_blended_lambdas_localia_favorece_al_local():
    """Con neutral=False se le suma HFA al local."""
    lh_n, la_n = elo.blended_lambdas(1.30, 1.10, 1500.0, 1500.0, True, 1.0)
    lh_l, la_l = elo.blended_lambdas(1.30, 1.10, 1500.0, 1500.0, False, 1.0)
    assert lh_l > lh_n
    assert la_l < la_n
    assert lh_n == pytest.approx(la_n)   # empate total de Elos en cancha neutral


def test_blended_lambdas_piso_de_015_con_elos_extremos():
    """El lambda del equipo aplastado no baja de 0.15."""
    lh, la = elo.blended_lambdas(1.30, 1.10, 3000.0, 1000.0, True, 1.0)
    assert la == pytest.approx(0.15)
    assert lh > 0.15
    lh2, la2 = elo.blended_lambdas(1.30, 1.10, 1000.0, 3000.0, True, 1.0)
    assert lh2 == pytest.approx(0.15)


def test_blended_lambdas_piso_se_propaga_a_la_mezcla():
    """Con w intermedio el piso entra en la media geometrica, no se pierde."""
    lh, la = elo.blended_lambdas(1.30, 1.10, 3000.0, 1000.0, True, 0.5)
    assert la == pytest.approx((1.10 * 0.15) ** 0.5)
    assert la > 0.15


def test_blended_lambdas_nunca_devuelve_negativos():
    for elo_h, elo_a in [(3000.0, 800.0), (800.0, 3000.0), (1500.0, 1500.0)]:
        for w in (0.0, 0.3, 1.0):
            lh, la = elo.blended_lambdas(1.20, 1.05, elo_h, elo_a, True, w)
            assert lh > 0 and la > 0


def test_blended_lambdas_parametros_c_y_tg_configurables():
    """c mas chico = mas supremacia por punto Elo; tg fija el total de goles."""
    base_h, base_a = elo.blended_lambdas(1.0, 1.0, 1700.0, 1500.0, True, 1.0,
                                         c=200.0, tg=2.60)
    agresivo_h, _ = elo.blended_lambdas(1.0, 1.0, 1700.0, 1500.0, True, 1.0,
                                        c=100.0, tg=2.60)
    assert agresivo_h > base_h
    alto_h, alto_a = elo.blended_lambdas(1.0, 1.0, 1700.0, 1500.0, True, 1.0,
                                         c=200.0, tg=3.20)
    assert alto_h + alto_a == pytest.approx(3.20)
    assert base_h + base_a == pytest.approx(2.60)


def test_blended_lambdas_se_integra_con_compute_elo():
    """Los ratings que salen de compute_elo entran directo en blended_lambdas."""
    df = make_df([
        {"date": "2026-06-01", "home_team": "Argentina", "away_team": "Brazil",
         "home_score": 4, "away_score": 0},
        {"date": "2026-06-05", "home_team": "Argentina", "away_team": "Japan",
         "home_score": 3, "away_score": 0},
    ])
    _, ratings = elo.compute_elo(df)
    lh, la = elo.blended_lambdas(1.30, 1.10, ratings["Argentina"],
                                 ratings["Brazil"], True, 1.0)
    assert lh > la   # Argentina quedo mucho mejor rankeada
