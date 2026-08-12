"""Tests de prode/clock.py: el reloj simulable.

El offset se calcula UNA vez al importar el modulo, asi que no alcanza con tocar
`os.environ` desde un test: hay que recargar. Se usa `importlib.reload` con la
variable puesta, y se restaura despues para no contaminar al resto de la suite
(el modulo lo importan app_data y la UI).

Lo que se ataja:
  * que un PRODE_NOW ilegible se ignore EN SILENCIO y uno crea que el modo demo
    no anda cuando en realidad escribio mal la fecha,
  * que el reloj quede congelado en vez de correr (la cuenta regresiva es la
    mitad de la pantalla principal),
  * y que el modo demo se cuele en produccion: sin la variable, esto tiene que
    ser exactamente `datetime.now()`.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

from prode import clock


@pytest.fixture
def reloj(monkeypatch):
    """Recarga clock con el PRODE_NOW que se le pida y lo deja como estaba."""
    def _con(valor):
        if valor is None:
            monkeypatch.delenv(clock.ENV, raising=False)
        else:
            monkeypatch.setenv(clock.ENV, valor)
        return importlib.reload(clock)
    yield _con
    monkeypatch.delenv(clock.ENV, raising=False)
    importlib.reload(clock)


# --------------------------------------------------------------------------
# (a) sin la variable: tiene que ser el reloj de verdad
# --------------------------------------------------------------------------
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_sin_prode_now_es_la_hora_real(reloj, valor):
    c = reloj(valor)
    assert not c.simulado()
    assert abs((c.now() - datetime.now()).total_seconds()) < 2
    assert c.descripcion() == ""


# --------------------------------------------------------------------------
# (b) con la variable: viaja en el tiempo
# --------------------------------------------------------------------------
def test_con_prode_now_el_reloj_arranca_en_esa_fecha(reloj):
    c = reloj("2026-06-25T18:00")
    assert c.simulado()
    assert abs((c.now() - datetime(2026, 6, 25, 18, 0)).total_seconds()) < 2


def test_el_reloj_simulado_CORRE_no_queda_congelado(reloj):
    """Si quedara congelado, la cuenta regresiva del proximo partido no bajaria
    nunca y un GIF de la app mostraria una foto."""
    c = reloj("2026-06-25T18:00")
    import time
    t0 = c.now()
    time.sleep(1.1)
    assert (c.now() - t0).total_seconds() >= 1


@pytest.mark.parametrize("valor,esperado", [
    ("2026-06-25T18:00", datetime(2026, 6, 25, 18, 0)),
    ("2026-06-25 18:00", datetime(2026, 6, 25, 18, 0)),
    ("2026-06-25", datetime(2026, 6, 25, 0, 0)),
    ("2026-07-19T16:00:30", datetime(2026, 7, 19, 16, 0, 30)),
])
def test_acepta_las_formas_iso_razonables(reloj, valor, esperado):
    c = reloj(valor)
    assert abs((c.now() - esperado).total_seconds()) < 2


def test_la_descripcion_dice_que_es_demo(reloj):
    c = reloj("2026-06-25T18:00")
    assert "demo" in c.descripcion().lower()
    assert "25/06/2026" in c.descripcion()


# --------------------------------------------------------------------------
# (c) una fecha mal escrita AVISA en vez de hacerse la desentendida
# --------------------------------------------------------------------------
@pytest.mark.parametrize("basura", ["ayer", "25/06/2026", "2026-13-45", "18:00"])
def test_una_fecha_ilegible_avisa_y_cae_a_la_hora_real(reloj, capsys, basura):
    """Ignorarla sin decir nada haria pensar que el modo demo no existe."""
    c = reloj(basura)

    assert not c.simulado()
    assert abs((c.now() - datetime.now()).total_seconds()) < 2
    assert clock.ENV in capsys.readouterr().err


# --------------------------------------------------------------------------
# (d) que el modo demo no se filtre a produccion
# --------------------------------------------------------------------------
def test_el_modulo_no_importa_nada_del_proyecto():
    """clock es hoja: lo importan app_data y la UI, y un import de vuelta
    cerraria un ciclo como el que ya hubo entre app_data y groups."""
    import ast
    from pathlib import Path
    arbol = ast.parse(Path(clock.__file__).read_text(encoding="utf-8"))
    mods = {(n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
            for n in ast.walk(arbol) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names}
    assert "prode" not in mods


def test_la_suite_corre_con_el_reloj_real():
    """Meta-test: si alguien deja PRODE_NOW seteada en su maquina, media suite
    empieza a fallar por razones que no tienen nada que ver con el cambio."""
    assert not clock.simulado(), (
        f"{clock.ENV} esta seteada en el entorno: los tests asumen la hora real")
