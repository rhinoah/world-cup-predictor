"""Tests de la estructura del proyecto: rutas, pipeline y el atajo de la raiz.

Son las tres piezas que quedaron sin cobertura despues de reestructurar el repo
en paquetes, y las tres fallan de una manera particularmente molesta: no revientan
al importar sino cuando el usuario intenta usarlas. Se comprobo que la suite
pasaba entera con `Paso("liquidar")` escrito `"liquidarr"`, con el paso de
liquidacion borrado del flujo diario, y con el shim de la raiz importando un
nombre que no existe.

Ninguno de estos tests lanza subprocesos: leen el AST o los datos declarados.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import run
from prode import paths

RAIZ = paths.ROOT


# --------------------------------------------------------------------------
# (a) paths.py: el unico calculo de rutas del proyecto
# --------------------------------------------------------------------------
def test_root_es_la_raiz_del_repo():
    """paths.py vive en prode/, asi que ROOT es su abuelo. Si alguien mueve el
    archivo de lugar, todas las rutas del proyecto apuntan a otro lado."""
    assert (RAIZ / "run.py").exists()
    assert (RAIZ / "prode" / "paths.py").exists()
    assert (RAIZ / "pyproject.toml").exists()


@pytest.mark.parametrize("nombre,esperado", [
    ("RESULTS_CSV", "data/results.csv"),
    ("HORARIOS_CSV", "fixture_horarios.csv"),
    ("THIRDS_JSON", "thirds_table.json"),
    ("PRONOSTICOS_CSV", "pronosticos.csv"),
    ("PRONOSTICOS_JSON", "pronosticos_detalle.json"),
    ("ICO", "prode.ico"),
])
def test_cada_ruta_apunta_al_archivo_que_dice(nombre, esperado):
    """Un typo en un nombre de archivo no rompe nada al importar: aparece como
    'no hay datos' mucho despues."""
    ruta = getattr(paths, nombre)
    assert ruta == RAIZ / esperado


def test_todas_las_rutas_cuelgan_de_root():
    rutas = [v for k, v in vars(paths).items()
             if isinstance(v, Path) and not k.startswith("_") and k != "ROOT"]
    assert rutas, "no se encontro ninguna ruta en paths.py"
    for r in rutas:
        assert RAIZ in r.parents or r == RAIZ, f"{r} no cuelga de ROOT"


def test_no_hay_constante_para_los_archivos_que_los_tests_aislan():
    """manual_results.csv, finished.csv y prodes.json los lee app_data colgando
    de su propio BASE, que los tests apuntan a un tmp. Una constante aca seria
    una trampa: el que la use se saltea el sandbox y toca los datos reales."""
    for prohibida in ("MANUAL_RESULTS_CSV", "FINISHED_CSV", "PRODES_JSON"):
        assert not hasattr(paths, prohibida), (
            f"paths.{prohibida} se saltearia el monkeypatch de app_data.BASE")


# --------------------------------------------------------------------------
# (b) run.py: el pipeline
# --------------------------------------------------------------------------
TODOS_LOS_PASOS = [p for pasos in run.FLUJOS.values() for p in pasos]


def test_los_tres_flujos_estan_declarados():
    assert set(run.FLUJOS) == {"setup", "update", "analisis"}


@pytest.mark.parametrize("paso", TODOS_LOS_PASOS, ids=lambda p: p.script)
def test_cada_paso_apunta_a_un_script_que_existe(paso):
    """Un typo en el nombre no falla hasta que alguien corre ese flujo, y ahi
    falla con un ModuleNotFoundError en el medio del pipeline."""
    assert (RAIZ / "scripts" / f"{paso.script}.py").exists()


@pytest.mark.parametrize("paso", TODOS_LOS_PASOS, ids=lambda p: p.script)
def test_cada_paso_dice_que_hace_y_que_produce(paso):
    assert paso.que_hace.strip()
    assert paso.produce.strip()


def test_el_ciclo_diario_hace_las_cuatro_cosas():
    """Es lo que corre la tarea programada: si se cae un paso, deja de
    actualizarse algo y nadie se entera hasta que mira los datos."""
    assert [p.script for p in run.UPDATE] == [
        "build_features", "liquidar", "predict_matchday", "build_pronosticos"]


def test_los_pasos_que_bajan_cosas_de_internet_son_opcionales():
    """Banderas, icono y la tabla de terceros no hacen falta para predecir: si
    fueran obligatorios, un clon sin internet no podria ni arrancar."""
    opcionales = {p.script for p in run.SETUP if p.opcional}
    assert opcionales == {"parse_thirds", "build_flags", "make_icon"}


def test_solo_predict_matchday_redirige_su_salida():
    con_salida = {p.script: p.stdout_a for p in TODOS_LOS_PASOS if p.stdout_a}
    assert con_salida == {"predict_matchday": "predicciones_jornada.txt"}


# --------------------------------------------------------------------------
# (c) prode_app.py: el atajo de la raiz
# --------------------------------------------------------------------------
# Se verifica por AST y no importando: importar la app trae customtkinter, que
# no esta instalado en CI a proposito.
SHIM = RAIZ / "prode_app.py"


def _importa_de_la_app():
    arbol = ast.parse(SHIM.read_text(encoding="utf-8"))
    return {a.name for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)
            and n.module == "prode.ui.app" for a in n.names}


def test_el_atajo_de_la_raiz_existe():
    """Es el unico punto de entrada del usuario: Prode.bat y el acceso directo
    del Inicio apuntan aca."""
    assert SHIM.exists()


def test_lo_que_el_atajo_importa_existe_de_verdad_en_la_app():
    """Si alguien renombra `main()` en prode/ui/app.py, esto explota recien
    cuando el usuario hace doble clic, sin ventana ni mensaje."""
    nombres = _importa_de_la_app()
    assert nombres, "el atajo no importa nada de prode.ui.app"

    arbol = ast.parse((RAIZ / "prode" / "ui" / "app.py").read_text(encoding="utf-8"))
    definidos = {n.name for n in arbol.body
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}
    faltan = nombres - definidos
    assert not faltan, f"prode/ui/app.py no define: {sorted(faltan)}"


def test_los_bat_apuntan_a_archivos_que_existen():
    """Los .bat son la forma en que se usa esto de verdad; un rename los rompe
    en silencio porque nadie los ejecuta al correr los tests."""
    for bat, esperado in [("Prode.bat", "prode_app.py"),
                          ("update_dataset.bat", "run.py")]:
        texto = (RAIZ / bat).read_text(encoding="utf-8", errors="replace")
        assert esperado in texto, f"{bat} no menciona {esperado}"
        assert (RAIZ / esperado).exists()
