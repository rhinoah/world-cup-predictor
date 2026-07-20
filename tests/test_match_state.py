"""Tests del 'reloj' del torneo: estado de un partido, dia logico y borde de eliminacion.

Todo lo que depende del tiempo recibe `now=` explicito; lo unico que se apoya en el
reloj real es `LONG_AGO`, que esta tan lejos que siempre cae en "done".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import app_data
from conftest import GROUPS_DAY, KO_DAY, LONG_AGO


# ---------------------------------------------------------------- pre / live / done

def test_match_state_pre_antes_del_kickoff():
    """Un minuto antes de que empiece todavia es 'pre'."""
    now = GROUPS_DAY - timedelta(minutes=1)
    assert app_data.match_state(GROUPS_DAY, now=now) == "pre"


def test_match_state_pre_muy_anticipado():
    now = GROUPS_DAY - timedelta(days=3)
    assert app_data.match_state(GROUPS_DAY, now=now) == "pre"


def test_match_state_live_justo_en_el_kickoff():
    """En el instante exacto del kickoff ya cuenta como 'live', no como 'pre'."""
    assert app_data.match_state(GROUPS_DAY, now=GROUPS_DAY) == "live"


def test_match_state_live_en_el_entretiempo():
    now = GROUPS_DAY + timedelta(minutes=55)
    assert app_data.match_state(GROUPS_DAY, now=now) == "live"


def test_match_state_done_pasada_la_ventana():
    now = GROUPS_DAY + timedelta(hours=5)
    assert app_data.match_state(GROUPS_DAY, now=now) == "done"


def test_match_state_done_justo_al_cerrar_la_ventana():
    """kickoff + MATCH_MINUTES exacto ya es 'done' (el corte es estricto)."""
    now = GROUPS_DAY + timedelta(minutes=app_data.MATCH_MINUTES)
    assert app_data.match_state(GROUPS_DAY, now=now) == "done"


def test_match_state_live_un_minuto_antes_de_cerrar():
    now = GROUPS_DAY + timedelta(minutes=app_data.MATCH_MINUTES - 1)
    assert app_data.match_state(GROUPS_DAY, now=now) == "live"


def test_match_state_done_con_fecha_del_pasado_sin_now():
    """Sin `now`, un partido del ano 2000 esta terminado contra el reloj real."""
    assert app_data.match_state(LONG_AGO) == "done"


# ------------------------------------------------- ventana 120' grupos vs 210' elim

def test_ventanas_definidas_120_y_210():
    assert app_data.MATCH_MINUTES == 120
    assert app_data.MATCH_MINUTES_KO == 210


def test_a_150_minutos_grupos_esta_done():
    """150' > 120': en fase de grupos el partido ya termino."""
    now = GROUPS_DAY + timedelta(minutes=150)
    assert app_data.match_state(GROUPS_DAY, now=now) == "done"


def test_a_150_minutos_eliminacion_sigue_live():
    """150' < 210': en eliminacion todavia puede haber alargue/penales."""
    now = KO_DAY + timedelta(minutes=150)
    assert app_data.match_state(KO_DAY, now=now) == "live"


def test_eliminacion_done_recien_pasados_los_210():
    now = KO_DAY + timedelta(minutes=app_data.MATCH_MINUTES_KO)
    assert app_data.match_state(KO_DAY, now=now) == "done"


def test_eliminacion_live_a_209_minutos():
    now = KO_DAY + timedelta(minutes=app_data.MATCH_MINUTES_KO - 1)
    assert app_data.match_state(KO_DAY, now=now) == "live"


@pytest.mark.parametrize("minutos,esperado", [(0, "live"), (119, "live"), (120, "done"),
                                              (150, "done"), (300, "done")])
def test_match_state_grupos_por_minuto(minutos, esperado):
    now = GROUPS_DAY + timedelta(minutes=minutos)
    assert app_data.match_state(GROUPS_DAY, now=now) == esperado


@pytest.mark.parametrize("minutos,esperado", [(0, "live"), (150, "live"), (209, "live"),
                                              (210, "done"), (400, "done")])
def test_match_state_eliminacion_por_minuto(minutos, esperado):
    now = KO_DAY + timedelta(minutes=minutos)
    assert app_data.match_state(KO_DAY, now=now) == esperado


# --------------------------------------------------------- override de finished.csv

def test_finished_csv_fuerza_done_aunque_el_partido_no_empezo(project):
    """El override se chequea ANTES del reloj: gana incluso contra un 'pre'."""
    project.finished([("Spain", "Argentina")])
    now = GROUPS_DAY - timedelta(days=2)
    assert app_data.match_state(GROUPS_DAY, now=now, home="Spain", away="Argentina") == "done"


def test_finished_csv_fuerza_done_sobre_un_live(project):
    project.finished([("Spain", "Argentina")])
    now = GROUPS_DAY + timedelta(minutes=30)
    assert app_data.match_state(GROUPS_DAY, now=now, home="Spain", away="Argentina") == "done"


def test_finished_no_afecta_a_otro_partido(project):
    """Solo el par (home, away) marcado se fuerza; el resto sigue el reloj."""
    project.finished([("Spain", "Argentina")])
    now = GROUPS_DAY + timedelta(minutes=30)
    assert app_data.match_state(GROUPS_DAY, now=now, home="Brazil", away="France") == "live"


def test_finished_es_direccional(project):
    """(home, away) invertido NO matchea: la tupla se guarda ordenada."""
    project.finished([("Spain", "Argentina")])
    now = GROUPS_DAY + timedelta(minutes=30)
    assert app_data.match_state(GROUPS_DAY, now=now, home="Argentina", away="Spain") == "live"


def test_sin_home_y_away_el_override_se_ignora(project):
    """Si no se pasan los equipos no hay con que buscar en finished.csv."""
    project.finished([("Spain", "Argentina")])
    now = GROUPS_DAY + timedelta(minutes=30)
    assert app_data.match_state(GROUPS_DAY, now=now) == "live"
    # solo uno de los dos tampoco alcanza
    assert app_data.match_state(GROUPS_DAY, now=now, home="Spain") == "live"


def test_finished_set_vacio_si_no_existe_el_csv(project):
    assert app_data._finished_set() == set()


def test_finished_set_lee_todos_los_pares(project):
    project.finished([("Spain", "Argentina"), ("Brazil", "France")])
    assert app_data._finished_set() == {("Spain", "Argentina"), ("Brazil", "France")}


def test_finished_set_cachea_en_global(project):
    """La segunda llamada devuelve el cache: borrar el CSV no cambia el resultado."""
    project.finished([("Spain", "Argentina")])
    primero = app_data._finished_set()
    (project.base / "data" / "finished.csv").unlink()
    assert app_data._finished_set() == primero == {("Spain", "Argentina")}


# ------------------------------------------------------------------ set_finished

def test_set_finished_crea_el_csv_y_agrega_el_par(project):
    app_data.set_finished("Spain", "Argentina")
    df = pd.read_csv(project.base / "data" / "finished.csv")
    assert list(zip(df["home_team"], df["away_team"])) == [("Spain", "Argentina")]


def test_set_finished_invalida_el_cache(project):
    """Tras marcarlo, `_finished_set()` tiene que ver el par nuevo sin reiniciar nada."""
    assert app_data._finished_set() == set()          # cachea el vacio
    app_data.set_finished("Spain", "Argentina")
    assert app_data._FINISHED is None                 # el cache quedo invalidado
    assert app_data._finished_set() == {("Spain", "Argentina")}


def test_set_finished_afecta_match_state(project):
    now = GROUPS_DAY + timedelta(minutes=30)
    assert app_data.match_state(GROUPS_DAY, now=now, home="Spain", away="Argentina") == "live"
    app_data.set_finished("Spain", "Argentina")
    assert app_data.match_state(GROUPS_DAY, now=now, home="Spain", away="Argentina") == "done"


def test_set_finished_no_duplica_si_ya_estaba(project):
    app_data.set_finished("Spain", "Argentina")
    app_data.set_finished("Spain", "Argentina")
    df = pd.read_csv(project.base / "data" / "finished.csv")
    assert len(df) == 1


def test_set_finished_val_false_saca_el_par(project):
    project.finished([("Spain", "Argentina"), ("Brazil", "France")])
    app_data.set_finished("Spain", "Argentina", val=False)
    assert app_data._finished_set() == {("Brazil", "France")}
    now = GROUPS_DAY + timedelta(minutes=30)
    assert app_data.match_state(GROUPS_DAY, now=now, home="Spain", away="Argentina") == "live"


def test_set_finished_val_false_sobre_par_inexistente_no_rompe(project):
    project.finished([("Brazil", "France")])
    app_data.set_finished("Spain", "Argentina", val=False)
    assert app_data._finished_set() == {("Brazil", "France")}


# -------------------------------------------------------------------- logical_date

def test_logical_date_0359_cuenta_como_dia_anterior():
    """Antes de las 4 AM el dia logico sigue siendo el del partido nocturno."""
    assert app_data.logical_date(datetime(2026, 6, 16, 3, 59)) == date(2026, 6, 15)


def test_logical_date_0400_ya_es_el_mismo_dia():
    assert app_data.logical_date(datetime(2026, 6, 16, 4, 0)) == date(2026, 6, 16)


def test_logical_date_medianoche_es_dia_anterior():
    assert app_data.logical_date(datetime(2026, 6, 16, 0, 0)) == date(2026, 6, 15)


def test_logical_date_mediodia_es_el_mismo_dia():
    assert app_data.logical_date(datetime(2026, 6, 16, 12, 0)) == date(2026, 6, 16)


def test_logical_date_cruza_fin_de_mes():
    assert app_data.logical_date(datetime(2026, 7, 1, 2, 30)) == date(2026, 6, 30)


def test_logical_date_usa_la_constante_de_rollover():
    assert app_data.DAY_ROLLOVER_HOUR == 4


def test_logical_date_acepta_timestamp_de_pandas():
    """Los kickoffs vienen de pandas; `.hour`/`.date()` funcionan igual."""
    assert app_data.logical_date(pd.Timestamp("2026-06-16 03:00")) == date(2026, 6, 15)


def test_logical_today_delega_en_logical_date():
    now = datetime(2026, 6, 16, 1, 15)
    assert app_data.logical_today(now=now) == date(2026, 6, 15)
    assert app_data.logical_today(now=datetime(2026, 6, 16, 9, 0)) == date(2026, 6, 16)


def test_logical_today_sin_argumento_devuelve_una_fecha():
    assert isinstance(app_data.logical_today(), date)


# --------------------------------------------------------------------- is_knockout

def test_is_knockout_false_el_27_de_junio():
    """27/06 es el ultimo dia de grupos: GROUPS_END todavia NO es eliminacion."""
    assert app_data.is_knockout(date(2026, 6, 27)) is False


def test_is_knockout_true_el_28_de_junio():
    assert app_data.is_knockout(date(2026, 6, 28)) is True


def test_is_knockout_false_en_pleno_grupos():
    assert app_data.is_knockout(date(2026, 6, 15)) is False


def test_is_knockout_true_en_la_final():
    assert app_data.is_knockout(date(2026, 7, 19)) is True


def test_is_knockout_acepta_string():
    assert app_data.is_knockout("2026-06-27") is False
    assert app_data.is_knockout("2026-06-28") is True


def test_is_knockout_con_datetime_del_27_da_true_por_la_hora():
    """Comportamiento actual: con hora > 00:00 del 27 el timestamp supera GROUPS_END.
    Por eso `match_state` le pasa `kickoff.date()` y no el datetime completo."""
    assert app_data.is_knockout(datetime(2026, 6, 27, 16, 0)) is True
    assert app_data.is_knockout(datetime(2026, 6, 27, 16, 0).date()) is False


def test_match_state_usa_la_fecha_del_kickoff_para_la_ventana():
    """Un partido del 27/06 a la tarde usa la ventana de grupos (120'), no la de KO."""
    kickoff = datetime(2026, 6, 27, 16, 0)
    assert app_data.match_state(kickoff, now=kickoff + timedelta(minutes=150)) == "done"


def test_groups_end_es_el_27_de_junio():
    assert app_data.GROUPS_END == pd.Timestamp("2026-06-27")


# ---------------------------------------------------------------------- needs_pens

def test_needs_pens_true_empate_en_ko_terminado(project, ko_match):
    """Empate en eliminacion, terminado y sin penales cargados -> falta la tanda."""
    m = ko_match(real=(1, 1), kickoff=LONG_AGO)
    assert app_data.needs_pens(m) is True


def test_needs_pens_false_en_fase_de_grupos(project, match):
    """En grupos el empate es un resultado valido: no hace falta ninguna tanda."""
    m = match(real=(1, 1), kickoff=LONG_AGO)
    assert app_data.needs_pens(m) is False


def test_needs_pens_false_si_no_hubo_empate(project, ko_match):
    m = ko_match(real=(2, 1), kickoff=LONG_AGO)
    assert app_data.needs_pens(m) is False


def test_needs_pens_false_si_ya_hay_penales_cargados(project, ko_match):
    m = ko_match(real=(1, 1), pens=(4, 2), kickoff=LONG_AGO)
    assert app_data.needs_pens(m) is False


def test_needs_pens_false_si_pens_es_none_explicito_pero_falta_resultado(project, ko_match):
    m = ko_match(real=None, pens=None, kickoff=LONG_AGO)
    assert app_data.needs_pens(m) is False


def test_needs_pens_false_si_el_partido_todavia_no_termino(project, ko_match):
    """Con el kickoff en el futuro el estado no es 'done' -> todavia no aplica."""
    m = ko_match(real=(1, 1), kickoff=datetime(2099, 7, 4, 16, 0))
    assert app_data.needs_pens(m) is False


def test_needs_pens_false_sin_stage_ko(project, match):
    """Sin la marca stage='ko' se lo trata como partido de grupos."""
    m = match(real=(0, 0), kickoff=LONG_AGO)
    assert "stage" not in m
    assert app_data.needs_pens(m) is False


def test_needs_pens_true_con_empate_0_0(project, ko_match):
    m = ko_match(real=(0, 0), kickoff=LONG_AGO)
    assert app_data.needs_pens(m) is True


def test_needs_pens_respeta_el_override_de_finished(project, ko_match):
    """El partido no llego a la ventana de 210' pero esta marcado terminado a mano."""
    kickoff = datetime(2099, 7, 4, 16, 0)
    m = ko_match(home="Spain", away="Argentina", real=(1, 1), kickoff=kickoff)
    assert app_data.needs_pens(m) is False
    project.finished([("Spain", "Argentina")])
    assert app_data.needs_pens(m) is True
