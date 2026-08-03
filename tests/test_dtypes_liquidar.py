"""Tests de la capa de datos: dtypes al guardar y liquidacion de pronosticos.

Cubre el BUG HISTORICO del proyecto: escribir `""` en una columna numerica
(home_pens/away_pens) rompia el guardado en silencio. Por eso `set_result()`
fuerza `pd.to_numeric(..., errors="coerce")` y usa `np.nan` -- nunca `""`.

Bajo test:
  * `app_data._int_or0`  -- casteo defensivo de las columnas de carga.
  * `app_data.set_result` / `_pens_index` -- override manual de resultados y penales.
  * `results.apply_overrides` -- completar el dataset sin pisar lo oficial.
  * `app_data.set_prediction` / `set_confirmation` -- escritura de pronosticos.csv.
  * `liquidar.main` -- cruce por EQUIPOS (no por fecha) y re-liquidacion.

Todo corre contra la fixture `project`, que apunta `app_data.BASE` a un tmp_path.
`liquidar` usa rutas RELATIVAS al cwd (`PRON`, `RESULTS`), asi que se
monkeypatchean; y `apply_manual_overrides` resuelve su path desde
`predict_match_v2.DATA`, que tambien se redirige al tmp.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from prode.data import app_data
from prode.data import csv_io
from scripts import liquidar
from prode.model import predict_match_v2
from prode.data import results


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def read_manual(project) -> pd.DataFrame:
    return pd.read_csv(project.base / "data" / "manual_results.csv")


def raw_manual(project) -> str:
    return (project.base / "data" / "manual_results.csv").read_text(encoding="utf-8")


def read_pron(project) -> pd.DataFrame:
    return pd.read_csv(project.base / "pronosticos.csv")


@pytest.fixture
def liq(project, monkeypatch):
    """Apunta las rutas (relativas al cwd) de liquidar.py al proyecto de mentira."""
    monkeypatch.setattr(liquidar, "PRON", str(project.base / "pronosticos.csv"))
    monkeypatch.setattr(liquidar, "RESULTS", str(project.base / "data" / "results.csv"))
    # apply_manual_overrides busca DATA.parent/"manual_results.csv"
    monkeypatch.setattr(predict_match_v2, "DATA", project.base / "data" / "results.csv")
    return project


# --------------------------------------------------------------------------
# (a) _int_or0: casteo defensivo, nunca explota
# --------------------------------------------------------------------------

@pytest.mark.parametrize("valor", ["", None, np.nan, float("nan"), pd.NA])
def test_int_or0_devuelve_0_para_vacios(valor):
    """El caso del bug: la celda vacia del CSV no puede romper la lectura."""
    assert app_data._int_or0(valor) == 0


@pytest.mark.parametrize("basura", ["basura", "1.5", "  ", object(), ["x"], {}])
def test_int_or0_devuelve_0_para_basura(basura):
    """Cualquier cosa que no castee a int cae en 0 en vez de tirar excepcion."""
    assert app_data._int_or0(basura) == 0


@pytest.mark.parametrize("valor,esperado", [
    ("3", 3), ("-1", -1), ("0", 0),
    (2.0, 2), (2.7, 2),          # float -> trunca (comportamiento de int())
    (5, 5), (np.int64(7), 7), (np.float64(1.0), 1),
])
def test_int_or0_castea_numeros_y_strings_numericos(valor, esperado):
    assert app_data._int_or0(valor) == esperado


def test_int_or0_sobre_columna_leida_de_csv_con_celdas_vacias(project):
    """Escenario real: load_gel vacio en pronosticos.csv -> 0, no NaN ni crash."""
    project.pronosticos([
        {"home_team": "Spain", "away_team": "Argentina", "load_gel": "", "load_meli": 1},
    ])
    row = read_pron(project).iloc[0]
    assert app_data._int_or0(row["load_gel"]) == 0
    assert app_data._int_or0(row["load_meli"]) == 1


# --------------------------------------------------------------------------
# (b) set_result SIN penales: la columna de penales sigue siendo numerica
# --------------------------------------------------------------------------

def test_set_result_sin_penales_deja_las_columnas_de_penales_numericas(project):
    """El bug historico: si se escribia "" el dtype dejaba de ser float."""
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])

    app_data.set_result("Spain", "Argentina", 2, 1)

    man = read_manual(project)                      # se relee del disco a proposito
    assert pd.api.types.is_numeric_dtype(man["home_pens"])
    assert pd.api.types.is_numeric_dtype(man["away_pens"])
    assert man["home_pens"].isna().all()
    assert man["away_pens"].isna().all()
    assert '""' not in raw_manual(project)          # nunca un string vacio literal
    assert app_data._pens_index() == {}


def test_set_result_sin_penales_guarda_el_marcador(project):
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])

    app_data.set_result("Spain", "Argentina", 2, 1)

    man = read_manual(project)
    assert len(man) == 1
    assert (int(man.iloc[0]["home_score"]), int(man.iloc[0]["away_score"])) == (2, 1)
    assert man.iloc[0]["date"] == "2026-06-15"      # fecha tomada del dataset


def test_set_result_sin_penales_no_pisa_los_penales_de_otra_fila(project):
    """Guardar un partido sin penales no puede ensuciar la fila del que si tiene."""
    project.results([{"home_team": "Spain", "away_team": "Argentina"},
                     {"home_team": "France", "away_team": "Brazil"}])
    project.manual_results([
        {"home_team": "France", "away_team": "Brazil", "home_score": 1,
         "away_score": 1, "home_pens": 4, "away_pens": 3},
    ])

    app_data.set_result("Spain", "Argentina", 2, 1)

    man = read_manual(project)
    assert pd.api.types.is_numeric_dtype(man["home_pens"])
    assert app_data._pens_index() == {("France", "Brazil"): (4, 3)}


def test_set_result_tolera_penales_no_numericos_previos(project):
    """Si el CSV quedo sucio (columna de texto), to_numeric lo limpia a NaN."""
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])
    (project.base / "data" / "manual_results.csv").write_text(
        "date,home_team,away_team,home_score,away_score,home_pens,away_pens\n"
        "2026-07-04,France,Brazil,1,1,?,\n", encoding="utf-8")

    app_data.set_result("Spain", "Argentina", 2, 1)

    man = read_manual(project)
    assert pd.api.types.is_numeric_dtype(man["home_pens"])
    assert man["home_pens"].isna().all()
    assert app_data._pens_index() == {}


def test_set_result_agrega_columnas_de_penales_si_faltaban(project):
    """CSV viejo sin columnas de penales: se crean numericas, no de texto."""
    project.results([{"home_team": "France", "away_team": "Brazil"}])
    (project.base / "data" / "manual_results.csv").write_text(
        "date,home_team,away_team,home_score,away_score\n"
        "2026-06-15,France,Brazil,1,1\n", encoding="utf-8")

    app_data.set_result("France", "Brazil", 2, 1)

    man = read_manual(project)
    assert list(man.columns)[-2:] == ["home_pens", "away_pens"]
    assert pd.api.types.is_numeric_dtype(man["home_pens"])


# --------------------------------------------------------------------------
# (c) set_result CON penales + _pens_index
# --------------------------------------------------------------------------

def test_set_result_con_penales_los_guarda_y_pens_index_los_devuelve(project):
    project.results([{"home_team": "France", "away_team": "Brazil",
                      "date": "2026-07-04"}])

    app_data.set_result("France", "Brazil", 1, 1, pens=(4, 3))

    idx = app_data._pens_index()
    assert idx == {("France", "Brazil"): (4, 3)}
    hp, ap = idx[("France", "Brazil")]
    assert isinstance(hp, int) and isinstance(ap, int)   # ints, no numpy/float


def test_pens_index_ignora_filas_sin_ambos_penales(project):
    """Falta uno de los dos -> la fila no entra al indice."""
    project.manual_results([
        {"home_team": "France", "away_team": "Brazil", "home_score": 1,
         "away_score": 1, "home_pens": 4, "away_pens": None},
        {"home_team": "Spain", "away_team": "Argentina", "home_score": 0,
         "away_score": 0, "home_pens": None, "away_pens": 5},
        {"home_team": "Ghana", "away_team": "Peru", "home_score": 2,
         "away_score": 2, "home_pens": 5, "away_pens": 4},
    ])

    assert app_data._pens_index() == {("Ghana", "Peru"): (5, 4)}


def test_pens_index_vacio_si_no_hay_manual_results(project):
    assert app_data._pens_index() == {}


def test_pens_index_castea_penales_float_a_int(project):
    """El CSV los devuelve como 4.0/3.0; el indice tiene que dar ints."""
    project.manual_results([
        {"home_team": "France", "away_team": "Brazil", "home_score": 1,
         "away_score": 1, "home_pens": 4.0, "away_pens": 3.0},
    ])

    assert app_data._pens_index() == {("France", "Brazil"): (4, 3)}


# --------------------------------------------------------------------------
# (d) set_result sobre un partido ya cargado: actualiza, no duplica
# --------------------------------------------------------------------------

def test_set_result_actualiza_en_vez_de_duplicar(project):
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])

    app_data.set_result("Spain", "Argentina", 1, 0)
    app_data.set_result("Spain", "Argentina", 3, 2)

    man = read_manual(project)
    assert len(man) == 1
    assert (int(man.iloc[0]["home_score"]), int(man.iloc[0]["away_score"])) == (3, 2)


def test_set_result_actualiza_los_penales_de_una_fila_existente(project):
    project.results([{"home_team": "France", "away_team": "Brazil"}])

    app_data.set_result("France", "Brazil", 1, 1, pens=(4, 3))
    app_data.set_result("France", "Brazil", 1, 1, pens=(5, 4))

    assert len(read_manual(project)) == 1
    assert app_data._pens_index() == {("France", "Brazil"): (5, 4)}


def test_set_result_sin_penales_limpia_los_penales_previos(project):
    """Corregir el marcador sin pasar pens BORRA los penales cargados antes."""
    project.results([{"home_team": "France", "away_team": "Brazil"}])

    app_data.set_result("France", "Brazil", 1, 1, pens=(4, 3))
    app_data.set_result("France", "Brazil", 2, 1)

    man = read_manual(project)
    assert len(man) == 1
    assert pd.api.types.is_numeric_dtype(man["home_pens"])
    assert man["home_pens"].isna().all()
    assert app_data._pens_index() == {}


def test_set_result_de_partido_desconocido_deja_la_fecha_vacia(project):
    """Si el cruce no esta en results.csv, `_match_date` devuelve NA (no rompe)."""
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])

    app_data.set_result("Ghana", "Peru", 0, 0)

    man = read_manual(project)
    fila = man[man["home_team"] == "Ghana"].iloc[0]
    assert pd.isna(fila["date"]) or fila["date"] == ""
    assert (int(fila["home_score"]), int(fila["away_score"])) == (0, 0)


# --------------------------------------------------------------------------
# (e) results.apply_overrides: completa lo que falta, no pisa lo oficial
# --------------------------------------------------------------------------

def _results_csv(project):
    return project.base / "data" / "results.csv"


def _results_df(project):
    return csv_io.read(_results_csv(project), csv_io.RESULTS)


def _override(project, res=None):
    """El override tal como lo aplican app_data y el modelo (misma funcion)."""
    return results.apply_overrides(
        _results_df(project) if res is None else res, _results_csv(project))


def test_apply_override_completa_faltantes_sin_pisar_oficiales(project):
    project.results([
        {"home_team": "Spain", "away_team": "Argentina",
         "home_score": 1, "away_score": 0},                       # oficial
        {"home_team": "France", "away_team": "Brazil", "date": "2026-06-16",
         "home_score": None, "away_score": None},                 # sin cargar
    ])
    project.manual_results([
        {"home_team": "Spain", "away_team": "Argentina",
         "home_score": 9, "away_score": 9},                       # intento de pisar
        {"home_team": "France", "away_team": "Brazil", "date": "2026-06-16",
         "home_score": 3, "away_score": 2},
    ])

    out = _override(project)

    esp = out[out["home_team"] == "Spain"].iloc[0]
    fra = out[out["home_team"] == "France"].iloc[0]
    assert (esp["home_score"], esp["away_score"]) == (1, 0)       # oficial intacto
    assert (fra["home_score"], fra["away_score"]) == (3, 2)       # completado


def test_apply_override_no_deja_columnas_con_sufijo(project):
    """El merge crea home_score_m/away_score_m y tiene que limpiarlas."""
    project.results([{"home_team": "France", "away_team": "Brazil",
                      "home_score": None, "away_score": None}])
    project.manual_results([{"home_team": "France", "away_team": "Brazil",
                             "home_score": 3, "away_score": 2}])

    out = _override(project)

    assert list(out.columns) == list(project.RESULT_COLS)
    assert len(out) == 1


def test_apply_override_sin_archivo_devuelve_lo_mismo(project):
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])
    res = _results_df(project)

    out = _override(project, res)

    assert out is res


def test_apply_override_ignora_filas_manuales_incompletas(project):
    """Una fila del override sin marcador se descarta (dropna), no rompe el merge."""
    project.results([{"home_team": "France", "away_team": "Brazil",
                      "home_score": None, "away_score": None}])
    project.manual_results([{"home_team": "France", "away_team": "Brazil",
                             "home_score": None, "away_score": None}])

    out = _override(project)

    assert len(out) == 1
    assert pd.isna(out.iloc[0]["home_score"])


def test_apply_override_cruza_por_fecha_ademas_de_equipos(project):
    """A diferencia de liquidar, el override matchea date+equipos: si la fecha
    no coincide, no completa nada (comportamiento actual)."""
    project.results([{"home_team": "France", "away_team": "Brazil",
                      "date": "2026-07-05", "home_score": None, "away_score": None}])
    project.manual_results([{"home_team": "France", "away_team": "Brazil",
                             "date": "2026-07-04", "home_score": 3, "away_score": 2}])

    out = _override(project)

    assert pd.isna(out.iloc[0]["home_score"])


# --------------------------------------------------------------------------
# (e2) results.by_teams / score_of: el indice que comparten fixture,
#      knockout_fixture y liquidar
# --------------------------------------------------------------------------
def _idx(filas):
    return results.by_teams(pd.DataFrame(filas))


def test_score_of_encuentra_el_marcador_por_equipos():
    idx = _idx([{"home_team": "Spain", "away_team": "France", "home_score": 2, "away_score": 1}])
    assert results.score_of(idx, "Spain", "France") == (2, 1)


def test_score_of_no_confunde_el_orden_de_los_equipos():
    """(local, visitante) es una clave ordenada: Spain-France no es France-Spain,
    y devolver el marcador dado vuelta invertiria quien gano la llave."""
    idx = _idx([{"home_team": "Spain", "away_team": "France", "home_score": 2, "away_score": 1}])
    assert results.score_of(idx, "France", "Spain") is None


@pytest.mark.parametrize("home,away", [("Spain", "Brazil"), (None, "France"),
                                       ("Spain", None), (None, None)])
def test_score_of_devuelve_none_si_no_hay_cruce(home, away):
    """Los llamadores le pasan equipos sin definir todo el tiempo: en el bracket
    la mitad de las llaves todavia no tienen rival."""
    idx = _idx([{"home_team": "Spain", "away_team": "France", "home_score": 2, "away_score": 1}])
    assert results.score_of(idx, home, away) is None


def test_una_llave_sin_definir_no_matchea_una_fila_con_el_equipo_vacio():
    """Pandas da por iguales None y NaN al buscar en el indice: sin la guarda,
    una llave todavia sin rival (home=None) encuentra una fila del dataset a la
    que le falta el equipo, y el bracket resuelve un ganador inventado."""
    idx = _idx([
        {"home_team": None, "away_team": "France", "home_score": 9, "away_score": 0},
        {"home_team": "Spain", "away_team": "France", "home_score": 2, "away_score": 1},
    ])
    assert (None, "France") in idx.index          # la trampa esta puesta
    assert results.score_of(idx, None, "France") is None


def test_by_teams_deja_afuera_los_partidos_sin_jugar():
    """Un partido del fixture sin marcador no puede figurar como 0-0."""
    idx = _idx([
        {"home_team": "Spain", "away_team": "France", "home_score": 2, "away_score": 1},
        {"home_team": "Mexico", "away_team": "Canada", "home_score": None, "away_score": None},
    ])
    assert results.score_of(idx, "Mexico", "Canada") is None
    assert len(idx) == 1


def test_score_of_con_el_cruce_repetido_no_explota():
    """Si el mismo cruce aparece dos veces `.loc` devuelve un DataFrame y no una
    fila: `int()` sobre eso revienta. Es la razon de ser del helper."""
    idx = _idx([
        {"home_team": "Spain", "away_team": "France", "home_score": 2, "away_score": 1},
        {"home_team": "Spain", "away_team": "France", "home_score": 3, "away_score": 0},
    ])
    assert results.score_of(idx, "Spain", "France") == (2, 1)


def test_score_of_devuelve_enteros_de_python():
    """Van a un dict que la GUI formatea y `liquidar` compara: un Int64 de pandas
    ahi arrastra dtypes raros y `pd.NA` en vez de valores."""
    idx = _idx([{"home_team": "Spain", "away_team": "France",
                 "home_score": 2, "away_score": 1}])
    assert [type(x) for x in results.score_of(idx, "Spain", "France")] == [int, int]


# --------------------------------------------------------------------------
# set_prediction / set_confirmation
# --------------------------------------------------------------------------

def test_set_prediction_crea_la_fila_con_cargas_en_cero(project):
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])

    app_data.set_prediction("Spain", "Argentina", 2, 1)

    pron = read_pron(project)
    assert len(pron) == 1
    r = pron.iloc[0]
    assert (int(r["pred_home"]), int(r["pred_away"])) == (2, 1)
    assert r["date"] == "2026-06-15"           # fecha tomada del dataset
    assert r["model"] == "manual"
    assert bool(r["neutral"]) is True          # Spain no es anfitrion
    assert (int(r["load_gel"]), int(r["load_meli"])) == (0, 0)


def test_set_prediction_marca_no_neutral_para_anfitriones(project):
    project.results([{"home_team": "Mexico", "away_team": "Argentina"}])

    app_data.set_prediction("Mexico", "Argentina", 1, 1)

    assert bool(read_pron(project).iloc[0]["neutral"]) is False


def test_set_prediction_actualiza_y_resetea_las_cargas(project):
    """Cambiar el pronostico obliga a recargarlo en los dos prodes."""
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])
    project.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                          "pred_home": 1, "pred_away": 1,
                          "load_gel": 1, "load_meli": 1}])

    app_data.set_prediction("Spain", "Argentina", 3, 0)

    pron = read_pron(project)
    assert len(pron) == 1                      # actualiza, no duplica
    r = pron.iloc[0]
    assert (int(r["pred_home"]), int(r["pred_away"])) == (3, 0)
    assert (int(r["load_gel"]), int(r["load_meli"])) == (0, 0)
    assert r["model"] == "manual"


def test_set_prediction_deja_columnas_numericas_legibles(project):
    """Las columnas vacias vuelven como NaN, no como el string "" (regresion)."""
    project.results([{"home_team": "Spain", "away_team": "Argentina"}])

    app_data.set_prediction("Spain", "Argentina", 2, 1)

    pron = read_pron(project)
    assert pd.api.types.is_numeric_dtype(pron["pred_home"])
    for c in ("ev_v3", "actual_home", "actual_away", "points"):
        assert pron[c].isna().all()
    assert '""' not in (project.base / "pronosticos.csv").read_text(encoding="utf-8")


def test_set_confirmation_marca_un_prode_sin_tocar_el_otro(project):
    project.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                          "pred_home": 2, "pred_away": 1,
                          "load_gel": 0, "load_meli": 0}])

    app_data.set_confirmation("Spain", "Argentina", gel=True)

    r = read_pron(project).iloc[0]
    assert (int(r["load_gel"]), int(r["load_meli"])) == (1, 0)


def test_set_confirmation_puede_desmarcar(project):
    project.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                          "pred_home": 2, "pred_away": 1,
                          "load_gel": 1, "load_meli": 1}])

    app_data.set_confirmation("Spain", "Argentina", gel=False)

    r = read_pron(project).iloc[0]
    assert (int(r["load_gel"]), int(r["load_meli"])) == (0, 1)


def test_set_confirmation_crea_la_fila_si_le_pasan_pred(project):
    project.results([{"home_team": "France", "away_team": "Brazil"}])

    app_data.set_confirmation("France", "Brazil", meli=True, pred=(1, 1))

    pron = read_pron(project)
    assert len(pron) == 1
    r = pron.iloc[0]
    assert (int(r["pred_home"]), int(r["pred_away"])) == (1, 1)
    assert (int(r["load_gel"]), int(r["load_meli"])) == (0, 1)


def test_set_confirmation_sin_fila_ni_pred_no_hace_nada(project):
    project.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                          "pred_home": 2, "pred_away": 1}])
    antes = (project.base / "pronosticos.csv").read_text(encoding="utf-8")

    app_data.set_confirmation("Ghana", "Peru", gel=True)

    despues = (project.base / "pronosticos.csv").read_text(encoding="utf-8")
    assert despues == antes                      # ni crea la fila ni reescribe
    assert len(read_pron(project)) == 1


# --------------------------------------------------------------------------
# (f) liquidar: cruce por equipos y re-liquidacion
# --------------------------------------------------------------------------

def test_liquidar_cruza_por_equipos_aunque_la_fecha_difiera(liq):
    """Fix de zona horaria: el pronostico dice 04/07 y el dataset 05/07 -> igual liquida."""
    liq.pronosticos([{"date": "2026-07-04", "home_team": "France", "away_team": "Brazil",
                      "pred_home": 1, "pred_away": 0}])
    liq.results([{"date": "2026-07-05", "home_team": "France", "away_team": "Brazil",
                  "home_score": 2, "away_score": 1}])

    liquidar.main()

    r = read_pron(liq).iloc[0]
    assert (int(r["actual_home"]), int(r["actual_away"])) == (2, 1)
    assert int(r["points"]) == 1                 # acerto la direccion, no el marcador
    assert r["date"] == "2026-07-04"             # la fecha del pronostico no se toca


def test_liquidar_puntua_marcador_exacto(liq):
    liq.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                      "pred_home": 2, "pred_away": 1}])
    liq.results([{"home_team": "Spain", "away_team": "Argentina",
                  "home_score": 2, "away_score": 1}])

    liquidar.main()

    assert int(read_pron(liq).iloc[0]["points"]) == 3


def test_liquidar_corrige_un_resultado_que_cambio(liq):
    """Ya estaba liquidado con 1-0 y el dataset ahora dice 3-3 -> se recalcula."""
    liq.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                      "pred_home": 2, "pred_away": 2,
                      "actual_home": 1, "actual_away": 0, "points": 0}])
    liq.results([{"home_team": "Spain", "away_team": "Argentina",
                  "home_score": 3, "away_score": 3}])

    liquidar.main()

    r = read_pron(liq).iloc[0]
    assert (int(r["actual_home"]), int(r["actual_away"])) == (3, 3)
    assert int(r["points"]) == 1                 # 2-2 vs 3-3: empate acertado


def test_liquidar_no_reescribe_si_ya_estaba_liquidado_igual(liq):
    liq.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                      "pred_home": 2, "pred_away": 1,
                      "actual_home": 2, "actual_away": 1, "points": 3}])
    liq.results([{"home_team": "Spain", "away_team": "Argentina",
                  "home_score": 2, "away_score": 1}])
    antes = (liq.base / "pronosticos.csv").read_text(encoding="utf-8")

    liquidar.main()

    assert (liq.base / "pronosticos.csv").read_text(encoding="utf-8") == antes


def test_liquidar_ignora_partidos_todavia_no_jugados(liq):
    liq.pronosticos([{"home_team": "France", "away_team": "Brazil",
                      "pred_home": 1, "pred_away": 0}])
    liq.results([{"home_team": "France", "away_team": "Brazil",
                  "home_score": None, "away_score": None}])

    liquidar.main()

    r = read_pron(liq).iloc[0]
    assert pd.isna(r["points"])
    assert pd.isna(r["actual_home"])


def test_liquidar_ignora_partidos_fuera_del_mundial(liq):
    """Mismo cruce pero amistoso / previo al torneo: no cuenta para el prode."""
    liq.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                      "pred_home": 1, "pred_away": 0}])
    liq.results([{"home_team": "Spain", "away_team": "Argentina",
                  "date": "2025-03-20", "tournament": "Friendly",
                  "home_score": 4, "away_score": 0}])

    liquidar.main()

    assert pd.isna(read_pron(liq).iloc[0]["points"])


def test_liquidar_no_cruza_con_los_equipos_invertidos(liq):
    """El indice es (local, visitante): Brazil-France no liquida France-Brazil."""
    liq.pronosticos([{"home_team": "France", "away_team": "Brazil",
                      "pred_home": 1, "pred_away": 0}])
    liq.results([{"home_team": "Brazil", "away_team": "France",
                  "home_score": 2, "away_score": 1}])

    liquidar.main()

    assert pd.isna(read_pron(liq).iloc[0]["points"])


def test_liquidar_usa_los_overrides_manuales(liq):
    """El resultado cargado a mano completa lo que martj42 todavia no publico."""
    liq.pronosticos([{"home_team": "France", "away_team": "Brazil",
                      "pred_home": 1, "pred_away": 0}])
    liq.results([{"home_team": "France", "away_team": "Brazil",
                  "home_score": None, "away_score": None}])
    liq.manual_results([{"home_team": "France", "away_team": "Brazil",
                         "home_score": 2, "away_score": 0}])

    liquidar.main()

    r = read_pron(liq).iloc[0]
    assert (int(r["actual_home"]), int(r["actual_away"])) == (2, 0)
    assert int(r["points"]) == 1


def test_liquidar_escribe_los_resultados_como_enteros(liq):
    """Sin el cast a Int64 el CSV quedaba con 2.0/1.0 (regresion de formato)."""
    liq.pronosticos([{"home_team": "Spain", "away_team": "Argentina",
                      "pred_home": 2, "pred_away": 1}])
    liq.results([{"home_team": "Spain", "away_team": "Argentina",
                  "home_score": 2, "away_score": 1}])

    liquidar.main()

    texto = (liq.base / "pronosticos.csv").read_text(encoding="utf-8")
    assert "2.0" not in texto and "1.0" not in texto
    pron = read_pron(liq)
    for c in ("actual_home", "actual_away", "points"):
        assert pd.api.types.is_integer_dtype(pron[c])


def test_liquidar_liquida_varios_y_deja_los_pendientes(liq):
    """Mezcla: uno jugado, uno sin jugar y uno que no esta en el dataset."""
    liq.pronosticos([
        {"home_team": "Spain", "away_team": "Argentina", "pred_home": 1, "pred_away": 0},
        {"home_team": "France", "away_team": "Brazil", "pred_home": 2, "pred_away": 2},
        {"home_team": "Ghana", "away_team": "Peru", "pred_home": 0, "pred_away": 1},
    ])
    liq.results([
        {"home_team": "Spain", "away_team": "Argentina", "home_score": 1, "away_score": 0},
        {"home_team": "France", "away_team": "Brazil", "home_score": None, "away_score": None},
    ])

    liquidar.main()

    pron = read_pron(liq).set_index("home_team")
    assert int(pron.loc["Spain", "points"]) == 3
    assert pd.isna(pron.loc["France", "points"])
    assert pd.isna(pron.loc["Ghana", "points"])
