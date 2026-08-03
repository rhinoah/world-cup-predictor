"""Tests de csv_io.py: la lectura y escritura tipada de los 5 CSV del proyecto.

csv_io nacio de centralizar el parseo que antes repetia cada modulo a mano. El
bug de fondo no era la duplicacion sino que, SIN dtypes declarados, un solo
faltante degrada la columna entera: `actual_home`/`points` se volvian float64 y
`notes` -- una columna de TEXTO -- terminaba tipada como numero. De ahi salia el
"3.0" en los penales.

Los modos de falla que se atajan aca:

  * una columna entera con faltantes vuelve del disco como float (la regresion
    central: seccion (c)) y los enteros se guardan con decimales (seccion (d)),
  * una celda con basura -- estos CSV se editan a mano -- deja la app sin
    arrancar en vez de quedar en pd.NA (seccion (e)),
  * un archivo opcional que falta rompe, o peor: uno OBLIGATORIO que falta se
    silencia y el modelo entrena con la nada (seccion (f)),
  * una columna que el esquema no conoce se pierde en el proximo guardado, o una
    que falta hace explotar la lectura (seccion (g)),
  * las fechas se escriben con hora de mas o un NaT sale como el texto "NaT"
    (seccion (h)),
  * `to_plain()` deja un dtype nullable y el modelo recibe un masked array donde
    esperaba numpy plano (seccion (i)).

`csv_io` es un modulo hoja: se importa directo y se le escriben CSV de juguete en
`tmp_path`, sin la fixture `project` (esa es para lo que toca app_data).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from prode.data import csv_io
from prode.data.csv_io import (BOOL, DATE, FINISHED, FLOAT, HORARIOS, INT, MANUAL_RESULTS,
                    PRONOSTICOS, RESULTS, TEXT, TIMESTAMP)

TIPOS_CONOCIDOS = {TEXT, INT, FLOAT, BOOL, DATE, TIMESTAMP}

ESQUEMAS = {
    "RESULTS": RESULTS,
    "MANUAL_RESULTS": MANUAL_RESULTS,
    "PRONOSTICOS": PRONOSTICOS,
    "FINISHED": FINISHED,
    "HORARIOS": HORARIOS,
}
NOMBRES = list(ESQUEMAS)

# Una fila completa y otra con faltantes por esquema: el round trip tiene que
# sobrevivir a las dos (la del medio es la que degradaba las columnas).
FILAS = {
    "RESULTS": [
        {"date": "2026-06-15", "home_team": "Spain", "away_team": "Argentina",
         "home_score": 1, "away_score": 0, "tournament": "FIFA World Cup",
         "city": "Dallas", "country": "United States", "neutral": True},
        {"date": "2026-06-16", "home_team": "Mexico", "away_team": "Canada",
         "home_score": pd.NA, "away_score": pd.NA, "tournament": "FIFA World Cup",
         "city": "Mexico City", "country": "Mexico", "neutral": False},
    ],
    "MANUAL_RESULTS": [
        {"date": "2026-07-04", "home_team": "France", "away_team": "Brazil",
         "home_score": 1, "away_score": 1, "home_pens": 4, "away_pens": 3},
        {"date": "2026-06-15", "home_team": "Spain", "away_team": "Argentina",
         "home_score": 2, "away_score": 0, "home_pens": pd.NA, "away_pens": pd.NA},
    ],
    "PRONOSTICOS": [
        {"date": "2026-06-15", "home_team": "Spain", "away_team": "Argentina",
         "pred_home": 2, "pred_away": 1, "neutral": True, "model": "v3",
         "ev_v3": 1.25, "actual_home": 2, "actual_away": 1, "points": 3,
         "notes": "liquidado a mano", "load_gel": 1, "load_meli": 1},
        {"date": "2026-06-16", "home_team": "Mexico", "away_team": "Canada",
         "pred_home": 1, "pred_away": 0, "neutral": False, "model": "v3",
         "ev_v3": pd.NA, "actual_home": pd.NA, "actual_away": pd.NA,
         "points": pd.NA, "notes": pd.NA, "load_gel": 0, "load_meli": 0},
    ],
    "FINISHED": [
        {"home_team": "France", "away_team": "Brazil"},
        {"home_team": "Spain", "away_team": "Argentina"},
    ],
    "HORARIOS": [
        {"home_team": "Spain", "away_team": "Argentina",
         "kickoff_arg": "2026-06-15 16:00"},
        {"home_team": "France", "away_team": "Brazil", "kickoff_arg": pd.NA},
    ],
}

# (esquema, columna, dtype declarado) -- las columnas donde pegaba la degradacion.
TIPADAS = [
    ("RESULTS", "home_score", "Int64"),
    ("RESULTS", "neutral", "boolean"),
    ("MANUAL_RESULTS", "home_pens", "Int64"),
    ("MANUAL_RESULTS", "away_pens", "Int64"),
    ("PRONOSTICOS", "actual_home", "Int64"),
    ("PRONOSTICOS", "points", "Int64"),
    ("PRONOSTICOS", "ev_v3", "Float64"),
    ("PRONOSTICOS", "neutral", "boolean"),
]
TIPADAS_IDS = [f"{n}.{c}" for n, c, _ in TIPADAS]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _csv(tmp_path, texto, nombre="t.csv"):
    """Escribe un CSV a mano (crudo, como quedaria despues de editarlo)."""
    p = tmp_path / nombre
    p.write_text(texto, encoding="utf-8")
    return p


def _celda(tmp_path, kind, crudo):
    """Lee UNA celda del tipo pedido. La columna `ancla` esta para que una celda
    vacia siga siendo una fila: pandas saltea las lineas en blanco."""
    p = _csv(tmp_path, f"v,ancla\n{crudo},1\n")
    return csv_io.read(p, {"v": kind, "ancla": INT})["v"].iloc[0]


def _ida_y_vuelta(tmp_path, df, schema):
    """write -> read -> write -> read. Devuelve (path_ida, r1, path_vuelta, r2)."""
    ida, vuelta = tmp_path / "ida.csv", tmp_path / "vuelta.csv"
    csv_io.write(df, ida, schema)
    r1 = csv_io.read(ida, schema)
    csv_io.write(r1, vuelta, schema)
    return ida, r1, vuelta, csv_io.read(vuelta, schema)


def _pron_con_faltantes(tmp_path):
    """pronosticos.csv recien cargado: sin resultado, sin ev y sin notas.

    Es EXACTAMENTE el archivo que rompia el codigo viejo."""
    return _csv(tmp_path,
                ",".join(PRONOSTICOS) + "\n"
                "2026-06-15,Spain,Argentina,2,1,True,v3,,,,,,1,0\n"
                "2026-06-16,Mexico,Canada,1,0,False,v3,,,,,,0,0\n",
                "pronosticos.csv")


def _es_texto(s: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(s) and not pd.api.types.is_numeric_dtype(s)


# --------------------------------------------------------------------------
# (a) los esquemas y empty()
# --------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", NOMBRES)
def test_los_esquemas_solo_usan_tipos_conocidos(nombre):
    """`_coerce` no valida el tipo: lo que no reconoce cae en el `else` y se
    convierte a Float64. Un typo tipo `"str"` en un esquema no falla -- deja la
    columna de texto convertida en numeros vacios, en silencio.

    Vale tambien para la marca de estricta: `INT + "!!"` o `"int !"` se leerian
    como un tipo desconocido y la columna terminaria siendo numerica."""
    intrusos = {c: k for c, k in ESQUEMAS[nombre].items()
                if csv_io._kind(k) not in TIPOS_CONOCIDOS}
    assert intrusos == {}, f"{nombre} usa tipos que _coerce no conoce: {intrusos}"


@pytest.mark.parametrize("nombre", NOMBRES)
def test_empty_devuelve_las_columnas_del_esquema_en_orden(nombre):
    """`app_data.PRON_COLS` sale de este orden: alterarlo reordena el CSV entero."""
    assert list(csv_io.empty(ESQUEMAS[nombre])) == list(ESQUEMAS[nombre])


@pytest.mark.parametrize("nombre", NOMBRES)
def test_empty_no_tiene_filas(nombre):
    assert len(csv_io.empty(ESQUEMAS[nombre])) == 0


@pytest.mark.parametrize("nombre,col,dtype", TIPADAS, ids=TIPADAS_IDS)
def test_empty_ya_viene_con_los_dtypes_nullable(nombre, col, dtype):
    """Una tabla vacia sin tipar se concatena/compara como float y arrastra el
    bug de vuelta apenas se le agrega la primera fila."""
    assert str(csv_io.empty(ESQUEMAS[nombre])[col].dtype) == dtype


def test_empty_no_deja_las_columnas_de_texto_como_numericas():
    """`notes` vacia tipada como float64 es el mismo bug, del lado del texto."""
    vacia = csv_io.empty(PRONOSTICOS)
    for col in ("home_team", "model", "notes"):
        assert not pd.api.types.is_numeric_dtype(vacia[col]), col


@pytest.mark.parametrize("nombre", ["RESULTS", "MANUAL_RESULTS", "PRONOSTICOS", "HORARIOS"])
def test_empty_tipa_las_fechas_como_datetime(nombre):
    """Si arrancaran como object, el primer `.dt` o la primera comparacion contra
    una fecha revientan."""
    vacia = csv_io.empty(ESQUEMAS[nombre])
    col = "kickoff_arg" if nombre == "HORARIOS" else "date"
    assert pd.api.types.is_datetime64_any_dtype(vacia[col])


# --------------------------------------------------------------------------
# (b) round trip: escribir y releer no cambia nada
# --------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", NOMBRES)
def test_el_round_trip_conserva_valores_y_dtypes(tmp_path, nombre):
    """Contrato central del modulo: guardar y volver a leer es la identidad. Si
    algun dtype no sobrevive, el archivo se degrada un poco en cada guardado."""
    schema = ESQUEMAS[nombre]
    _, r1, _, r2 = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS[nombre]), schema)
    pd.testing.assert_frame_equal(r1, r2)


@pytest.mark.parametrize("nombre", NOMBRES)
def test_reescribir_lo_leido_da_el_archivo_identico(tmp_path, nombre):
    """Abrir la app y no tocar nada no puede reescribir el CSV: si el formato de
    salida no es punto fijo, cada arranque ensucia el diff de git."""
    ida, _, vuelta, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS[nombre]),
                                      ESQUEMAS[nombre])
    assert ida.read_bytes() == vuelta.read_bytes()


def test_el_round_trip_conserva_los_valores_de_un_pronostico(tmp_path):
    """Lo mismo que arriba pero con los valores a la vista, para que el test diga
    que se espera y no solo 'los dos frames son iguales'."""
    _, r1, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS["PRONOSTICOS"]),
                                PRONOSTICOS)
    lleno, vacio = r1.iloc[0], r1.iloc[1]
    assert (lleno["pred_home"], lleno["pred_away"]) == (2, 1)
    assert (lleno["actual_home"], lleno["points"]) == (2, 3)
    assert lleno["ev_v3"] == 1.25
    assert bool(lleno["neutral"]) is True and bool(vacio["neutral"]) is False
    assert lleno["notes"] == "liquidado a mano"
    assert lleno["date"] == pd.Timestamp("2026-06-15")
    for col in ("ev_v3", "actual_home", "actual_away", "points", "notes"):
        assert pd.isna(vacio[col]), col


@pytest.mark.parametrize("nombre", NOMBRES)
def test_el_faltante_se_escribe_como_campo_vacio(tmp_path, nombre):
    """Nunca "", ni "None", ni "nan", ni "<NA>": el CSV se lee tambien a ojo."""
    ida, _, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS[nombre]),
                                 ESQUEMAS[nombre])
    texto = ida.read_text(encoding="utf-8")
    for veneno in ('""', "None", "nan", "<NA>", "NaT"):
        assert veneno not in texto, f"{nombre} escribio {veneno!r}"


def test_escribir_no_muta_el_dataframe_que_le_pasan(tmp_path):
    """`write` tipa una COPIA: si tipara el original, el DataFrame que la app
    tiene en memoria cambiaria de dtype por el solo hecho de guardarlo."""
    df = pd.DataFrame({"home_team": ["Spain"], "away_team": ["Argentina"]})
    columnas, dtypes = list(df.columns), df.dtypes.copy()

    csv_io.write(df, tmp_path / "x.csv", MANUAL_RESULTS)

    assert list(df.columns) == columnas
    assert df.dtypes.equals(dtypes)


# --------------------------------------------------------------------------
# (c) LA REGRESION CENTRAL: un faltante no degrada la columna
# --------------------------------------------------------------------------
@pytest.mark.parametrize("nombre,col,dtype", TIPADAS, ids=TIPADAS_IDS)
def test_una_columna_con_faltantes_conserva_su_tipo(tmp_path, nombre, col, dtype):
    """EL bug del modulo: sin dtype declarado, UN solo faltante pasa la columna
    entera a float64 y los enteros empiezan a guardarse con decimales."""
    schema = ESQUEMAS[nombre]
    _, r1, _, r2 = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS[nombre]), schema)
    assert str(r1[col].dtype) == dtype
    assert str(r2[col].dtype) == dtype


def test_una_columna_entera_enteramente_vacia_sigue_siendo_entera(tmp_path):
    """El caso extremo: `actual_home`/`points` de un prode recien cargado no
    tienen NI UN valor. Es el archivo con el que empezaba cada mundial."""
    pron = csv_io.read(_pron_con_faltantes(tmp_path), PRONOSTICOS)
    for col in ("actual_home", "actual_away", "points"):
        assert str(pron[col].dtype) == "Int64", col
        assert pron[col].isna().all()
    assert str(pron["ev_v3"].dtype) == "Float64"


def test_una_columna_de_texto_vacia_no_termina_siendo_numerica(tmp_path):
    """`notes` sin una sola nota se leia como float64 y el primer `.str` o la
    primera nota escrita rompian el tipo del archivo."""
    pron = csv_io.read(_pron_con_faltantes(tmp_path), PRONOSTICOS)
    assert _es_texto(pron["notes"])
    assert pron["notes"].isna().all()


def test_pandas_crudo_si_degrada_el_mismo_archivo(tmp_path):
    """Testigo: si pandas dejara de degradar por su cuenta, los dos tests de
    arriba pasarian sin probar nada."""
    crudo = pd.read_csv(_pron_con_faltantes(tmp_path))
    assert crudo["actual_home"].dtype == "float64"
    assert crudo["points"].dtype == "float64"
    assert pd.api.types.is_numeric_dtype(crudo["notes"])   # una columna de texto


def test_una_nota_escrita_sobre_la_columna_vacia_sobrevive(tmp_path):
    """El escenario completo del bug: leer el archivo sin notas, escribir una y
    guardar. Si la columna quedo numerica, el texto se pierde o rompe el guardado."""
    p = _pron_con_faltantes(tmp_path)
    pron = csv_io.read(p, PRONOSTICOS)

    pron.loc[0, "notes"] = "definido por penales"
    csv_io.write(pron, p, PRONOSTICOS)

    releido = csv_io.read(p, PRONOSTICOS)
    assert releido.loc[0, "notes"] == "definido por penales"
    assert pd.isna(releido.loc[1, "notes"])


# --------------------------------------------------------------------------
# (d) los penales: "3", nunca "3.0"
# --------------------------------------------------------------------------
def test_los_penales_se_guardan_sin_punto_cero(tmp_path):
    """El bug historico: `home_pens` casi siempre esta vacia, la columna se volvia
    float y el CSV terminaba con "3.0". `_pens_index` despues castea, pero el
    archivo -- que se lee y se edita a mano -- quedaba ilegible."""
    ida, _, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS["MANUAL_RESULTS"]),
                                 MANUAL_RESULTS)
    texto = ida.read_text(encoding="utf-8")
    assert "2026-07-04,France,Brazil,1,1,4,3\n" in texto
    assert "4.0" not in texto and "3.0" not in texto


@pytest.mark.parametrize("nombre", NOMBRES)
def test_ninguna_columna_entera_se_escribe_con_decimales(tmp_path, nombre):
    """Generalizacion del caso de los penales a los 5 esquemas."""
    ida, _, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS[nombre]),
                                 ESQUEMAS[nombre])
    sucios = re.findall(r"(?<![\d.])\d+\.0(?=[,\n])", ida.read_text(encoding="utf-8"))
    assert sucios == [], f"{nombre} escribio enteros con decimales: {sucios}"


def test_un_csv_viejo_con_3_punto_0_se_cura_al_reescribirlo(tmp_path):
    """Los archivos que quedaron sucios de la epoca del bug se arreglan solos con
    el primer guardado, sin migracion aparte."""
    p = _csv(tmp_path,
             "date,home_team,away_team,home_score,away_score,home_pens,away_pens\n"
             "2026-07-04,France,Brazil,1.0,1.0,4.0,3.0\n")

    man = csv_io.read(p, MANUAL_RESULTS)
    csv_io.write(man, p, MANUAL_RESULTS)

    assert man["home_pens"].tolist() == [4]
    assert str(man["home_pens"].dtype) == "Int64"
    assert p.read_text(encoding="utf-8").endswith(
        "2026-07-04,France,Brazil,1,1,4,3\n")


# --------------------------------------------------------------------------
# (e) tolerancia: basura -> pd.NA, nunca una excepcion
# --------------------------------------------------------------------------
BASURA = [
    (INT, "?"), (INT, "dos"), (INT, "-"), (INT, "  "),
    (INT, "1.5"), (INT, "-2.5"),          # decimal que no es entero: no redondea
    (FLOAT, "abc"), (FLOAT, "n/d"), (FLOAT, "?"),
    (BOOL, "si"), (BOOL, "yes"), (BOOL, "verdadero"), (BOOL, "2"),
    (DATE, "no-es-fecha"), (DATE, "32/13/2026"), (DATE, "?"),
    (TIMESTAMP, "manana"), (TIMESTAMP, "16hs"),
]


@pytest.mark.parametrize("kind,crudo", BASURA, ids=[f"{k}:{v}" for k, v in BASURA])
def test_una_celda_con_basura_queda_en_na(tmp_path, kind, crudo):
    """Estos CSV se editan a mano: una celda mal tipeada no puede dejar la app
    sin arrancar. Se descarta el valor, no el archivo."""
    assert pd.isna(_celda(tmp_path, kind, crudo))


@pytest.mark.parametrize("crudo,esperado", [
    ("3", 3), ("3.0", 3), ("-1", -1), ("0", 0), (" 5 ", 5), ("+2", 2),
])
def test_los_enteros_legibles_no_se_descartan(tmp_path, crudo, esperado):
    """Contracara del test de arriba: si _to_int fuera demasiado estricto se
    comeria valores buenos (y "3.0" es justo lo que dejo escrito el bug viejo)."""
    assert _celda(tmp_path, INT, crudo) == esperado


def test_la_fila_sana_sobrevive_a_la_basura_de_una_columna_tolerante(tmp_path):
    """Tolerar no puede significar descartar la fila entera ni correr los datos."""
    p = _csv(tmp_path,
             "date,home_team,away_team,home_score,away_score,home_pens,away_pens\n"
             "2026-07-04,France,Brazil,1,1,4,3\n"
             "2026-07-05,Spain,Argentina,2,0,x,\n")

    man = csv_io.read(p, MANUAL_RESULTS)

    assert len(man) == 2
    assert man.loc[0, ["home_score", "away_score", "home_pens"]].tolist() == [1, 1, 4]
    assert man.loc[1, "home_team"] == "Spain"          # el texto no se pierde
    assert man.loc[1, ["home_score", "away_score"]].tolist() == [2, 0]
    assert man.loc[1, ["home_pens", "away_pens"]].isna().all()


@pytest.mark.parametrize("celda,columna", [
    ("ayer,Spain,Argentina,2,0,,", "date"),
    ("2026-07-05,Spain,Argentina,dos,0,,", "home_score"),
    ("2026-07-05,Spain,Argentina,2,?,,", "away_score"),
])
def test_un_dato_ilegible_en_columna_estricta_avisa_en_vez_de_evaporarse(
        tmp_path, celda, columna):
    """EL modo de falla que justifica que existan columnas estrictas: si un
    marcador mal tipeado se convirtiera en NA, `_apply_override` descartaria la
    fila por el dropna y el partido pasaria a figurar como NO JUGADO -- el
    tablero miente y no queda rastro de por que."""
    p = _csv(tmp_path,
             "date,home_team,away_team,home_score,away_score,home_pens,away_pens\n"
             "2026-07-04,France,Brazil,1,1,4,3\n" + celda + "\n")

    with pytest.raises(ValueError) as exc:
        csv_io.read(p, MANUAL_RESULTS)

    # el mensaje tiene que alcanzar para ir a arreglar la celda
    assert columna in str(exc.value)
    assert "fila 1" in str(exc.value)
    assert str(p) in str(exc.value)


def test_la_celda_vacia_no_es_un_dato_ilegible(tmp_path):
    """Estricta no es obligatoria: un partido que todavia no se jugo no tiene
    marcador, y eso es normal, no un error de carga."""
    p = _csv(tmp_path, "date,home_team,away_team,home_score,away_score\n"
                       "2026-07-04,France,Brazil,,\n")

    man = csv_io.read(p, MANUAL_RESULTS)

    assert man.loc[0, ["home_score", "away_score"]].isna().all()


def test_leer_penales_no_numericos_no_explota(tmp_path):
    """El mismo CSV sucio que exige `test_set_result_tolera_penales_no_numericos`,
    ahora contra el modulo que hace la lectura de verdad."""
    p = _csv(tmp_path,
             "date,home_team,away_team,home_score,away_score,home_pens,away_pens\n"
             "2026-07-04,France,Brazil,1,1,?,\n")

    man = csv_io.read(p, MANUAL_RESULTS)

    assert str(man["home_pens"].dtype) == "Int64"
    assert man["home_pens"].isna().all()


# OJO: se testea `isna()`, no `is pd.NA`. La convencion del modulo dice que el
# faltante es siempre pd.NA, pero en una columna de texto CON algun valor pandas
# usa np.nan y el `.where(..., pd.NA)` de `_coerce` no llega a cambiarlo (la
# columna ya pasa el `is_string_dtype` y el pd.NA se normaliza de vuelta a nan).
# O sea: el marcador de faltante de las columnas de texto no es uniforme. No se
# nota en el archivo -- los dos salen como campo vacio, que es lo que si se
# testea aca y en (b) -- pero cualquier codigo que interpole el valor en un label
# imprimiria "nan". Si algun dia se muestra `notes` en la UI, hay que arreglarlo.
def test_una_celda_de_texto_vacia_queda_en_na_y_no_en_string_vacio(tmp_path):
    """El faltante es SIEMPRE NA: un "" que se cuele como valor vuelve a salir
    entrecomillado y el archivo pasa a tener dos formas de decir "sin dato"."""
    p = _csv(tmp_path, 'home_team,away_team\nSpain,\nFrance,""\nBrazil,Peru\n')

    fin = csv_io.read(p, FINISHED)
    csv_io.write(fin, p, FINISHED)

    assert fin["away_team"].isna().tolist() == [True, True, False]
    assert "" not in fin["away_team"].dropna().tolist()
    assert '""' not in p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# (f) missing_ok: opcional de verdad vs obligatorio
# --------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", NOMBRES)
def test_sin_missing_ok_un_archivo_que_falta_explota(tmp_path, nombre):
    """results.csv y el fixture NO son opcionales: devolver una tabla vacia haria
    que el modelo entrene con la nada y prediga cualquier cosa, en silencio."""
    with pytest.raises(FileNotFoundError):
        csv_io.read(tmp_path / "no-existe.csv", ESQUEMAS[nombre])


@pytest.mark.parametrize("nombre", NOMBRES)
def test_con_missing_ok_un_archivo_que_falta_da_una_tabla_vacia(tmp_path, nombre):
    """Los overrides manuales y los pronosticos todavia sin cargar pueden no
    existir: ahi el arranque limpio es una tabla vacia, no un crash."""
    df = csv_io.read(tmp_path / "no-existe.csv", ESQUEMAS[nombre], missing_ok=True)
    assert len(df) == 0
    assert list(df) == list(ESQUEMAS[nombre])


@pytest.mark.parametrize("nombre,col,dtype", TIPADAS, ids=TIPADAS_IDS)
def test_la_tabla_vacia_de_missing_ok_ya_viene_tipada(tmp_path, nombre, col, dtype):
    """Si viniera sin tipar, el primer pronostico que se agregue arrastra el bug:
    la columna nace float y se guarda con decimales."""
    df = csv_io.read(tmp_path / "no-existe.csv", ESQUEMAS[nombre], missing_ok=True)
    assert str(df[col].dtype) == dtype


def test_missing_ok_no_ignora_el_archivo_cuando_existe(tmp_path):
    """`missing_ok` es un fallback, no un modo: si el CSV esta, se lee."""
    p = _csv(tmp_path, "home_team,away_team\nFrance,Brazil\n")

    fin = csv_io.read(p, FINISHED, missing_ok=True)

    assert fin["home_team"].tolist() == ["France"]


# --------------------------------------------------------------------------
# (g) columnas de menos y de mas
# --------------------------------------------------------------------------
def test_una_columna_del_esquema_que_falta_se_crea_vacia_y_tipada(tmp_path):
    """Un CSV viejo (sin las columnas de penales, por ejemplo) se tiene que poder
    leer igual, y la columna nueva tiene que nacer entera: si nace de texto, el
    primer penal se guarda como "4" entre comillas."""
    p = _csv(tmp_path, "date,home_team,away_team,home_score,away_score\n"
                       "2026-06-15,France,Brazil,1,1\n")

    man = csv_io.read(p, MANUAL_RESULTS)

    assert {"home_pens", "away_pens"} <= set(man)
    assert str(man["home_pens"].dtype) == "Int64"
    assert str(man["away_pens"].dtype) == "Int64"
    assert man["home_pens"].isna().all()
    assert man.loc[0, "home_score"] == 1        # lo que ya estaba no se movio


def test_las_columnas_que_faltan_se_agregan_al_final(tmp_path):
    """El orden del archivo manda: reordenar columnas al leer convierte cualquier
    guardado en un diff de git ilegible."""
    p = _csv(tmp_path, "home_team,away_team,home_score,away_score\n"
                       "France,Brazil,1,1\n")

    man = csv_io.read(p, MANUAL_RESULTS)

    assert list(man)[:4] == ["home_team", "away_team", "home_score", "away_score"]
    assert list(man)[4:] == ["date", "home_pens", "away_pens"]


def test_una_columna_que_el_esquema_no_conoce_se_conserva_al_leer(tmp_path):
    """Descartar lo que el esquema no conoce borraria datos del usuario en el
    proximo guardado, sin aviso."""
    p = _csv(tmp_path, "home_team,away_team,comentario\n"
                       "Spain,Argentina,jugado en Dallas\n")

    fin = csv_io.read(p, FINISHED)

    assert list(fin) == ["home_team", "away_team", "comentario"]
    assert fin["comentario"].tolist() == ["jugado en Dallas"]


def test_una_columna_que_el_esquema_no_conoce_sobrevive_al_reescribir(tmp_path):
    """El ciclo completo leer->guardar es el que borraria la columna."""
    p = _csv(tmp_path, "date,home_team,away_team,home_score,away_score,arbitro\n"
                       "2026-06-15,Spain,Argentina,2,0,Kuipers\n")

    csv_io.write(csv_io.read(p, MANUAL_RESULTS), p, MANUAL_RESULTS)

    texto = p.read_text(encoding="utf-8")
    assert "arbitro" in texto and "Kuipers" in texto
    assert csv_io.read(p, MANUAL_RESULTS)["arbitro"].tolist() == ["Kuipers"]


def test_un_csv_con_columnas_de_mas_y_de_menos_a_la_vez(tmp_path):
    """Los dos casos juntos, que es como llega un archivo editado a mano."""
    p = _csv(tmp_path, "home_team,away_team,comentario\nSpain,Argentina,ok\n")

    man = csv_io.read(p, MANUAL_RESULTS)

    assert list(man)[:3] == ["home_team", "away_team", "comentario"]
    assert set(MANUAL_RESULTS) <= set(man)
    assert len(man) == 1


# --------------------------------------------------------------------------
# (h) fechas: DATE sin hora, TIMESTAMP sin segundos, NaT vacio
# --------------------------------------------------------------------------
def test_date_se_escribe_sin_hora(tmp_path):
    """`date` es una fecha, no un instante: si sale como "2026-06-15 00:00:00" el
    archivo se ensucia entero y deja de cruzar contra martj42 a ojo."""
    p = _csv(tmp_path, "date,home_team,away_team,home_score,away_score\n"
                       "2026-06-15 18:30:00,France,Brazil,1,1\n")

    csv_io.write(csv_io.read(p, MANUAL_RESULTS), p, MANUAL_RESULTS)

    assert p.read_text(encoding="utf-8").splitlines()[1].startswith("2026-06-15,")
    assert "00:00" not in p.read_text(encoding="utf-8")


def test_timestamp_se_escribe_con_hora_y_sin_segundos(tmp_path):
    """El fixture ya venia asi: agregarle ":00" reescribe las 104 lineas de golpe."""
    p = _csv(tmp_path, "home_team,away_team,kickoff_arg\n"
                       "Spain,Argentina,2026-06-15 16:00:45\n")

    csv_io.write(csv_io.read(p, HORARIOS), p, HORARIOS)

    assert p.read_text(encoding="utf-8").endswith("Spain,Argentina,2026-06-15 16:00\n")


@pytest.mark.parametrize("nombre,col", [("MANUAL_RESULTS", "date"),
                                        ("HORARIOS", "kickoff_arg")])
def test_una_fecha_faltante_no_se_escribe_como_el_texto_NaT(tmp_path, nombre, col):
    """El proyecto ya tuvo el bug: `strftime` sobre NaT tiene que dar campo vacio,
    porque un "NaT" literal se relee como texto y ensucia la columna."""
    schema = ESQUEMAS[nombre]
    df = pd.DataFrame(FILAS[nombre]).copy()
    df[col] = pd.NA
    p = tmp_path / "sinfecha.csv"

    csv_io.write(df, p, schema)

    texto = p.read_text(encoding="utf-8")
    assert "NaT" not in texto and "nan" not in texto
    assert csv_io.read(p, schema)[col].isna().all()


def test_una_fecha_ilegible_no_se_guarda_vacia_a_escondidas(tmp_path):
    """Antes esto perdia el dato dos veces: la fecha quedaba en NaT al leer y el
    guardado siguiente la reemplazaba por vacio EN EL ARCHIVO -- aunque el
    usuario estuviera editando otra fila. Ahora la lectura avisa antes."""
    p = _csv(tmp_path, "date,home_team,away_team,home_score,away_score\n"
                       "el jueves,France,Brazil,1,1\n")
    original = p.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="date"):
        csv_io.read(p, MANUAL_RESULTS)

    assert p.read_text(encoding="utf-8") == original     # nada se toco


@pytest.mark.parametrize("nombre,col", [("RESULTS", "date"), ("MANUAL_RESULTS", "date"),
                                        ("PRONOSTICOS", "date"), ("HORARIOS", "kickoff_arg")])
def test_las_fechas_vuelven_como_datetime(tmp_path, nombre, col):
    """Si volvieran como texto, todo el codigo que compara contra `datetime.now()`
    o hace `.dt` explota recien en runtime."""
    _, r1, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS[nombre]), ESQUEMAS[nombre])
    assert pd.api.types.is_datetime64_any_dtype(r1[col])


# --------------------------------------------------------------------------
# (i) to_plain: de vuelta a numpy plano
# --------------------------------------------------------------------------
PLANOS = [("home_score", "int64"), ("away_score", "int64"), ("neutral", "bool")]


@pytest.fixture
def results_leido(tmp_path):
    """results.csv de juguete SIN faltantes (como el que llega al modelo)."""
    p = _csv(tmp_path,
             "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
             "2026-06-15,Spain,Argentina,1,0,FIFA World Cup,Dallas,United States,TRUE\n"
             "2026-06-16,Mexico,Canada,2,2,FIFA World Cup,Mexico City,Mexico,FALSE\n")
    return csv_io.read(p, RESULTS)


@pytest.mark.parametrize("col,dtype", PLANOS)
def test_to_plain_deja_dtypes_de_numpy(results_leido, col, dtype):
    """`fit_iterative` y `compute_elo` hacen `.to_numpy()`: un dtype nullable
    devuelve un masked array donde `~neutral` y `.astype(float)` no se portan igual."""
    plano = csv_io.to_plain(results_leido, RESULTS)
    assert plano[col].dtype == np.dtype(dtype)
    assert isinstance(plano[col].dtype, np.dtype)     # nullable no es np.dtype


@pytest.mark.parametrize("col,dtype", PLANOS)
def test_antes_de_to_plain_el_dtype_NO_es_de_numpy(results_leido, col, dtype):
    """Testigo del test de arriba: si `read` ya devolviera numpy plano, `to_plain`
    no probaria nada (y el modulo entero sobraria)."""
    assert not isinstance(results_leido[col].dtype, np.dtype)


def test_to_plain_conserva_los_valores(results_leido):
    plano = csv_io.to_plain(results_leido, RESULTS)
    assert plano["home_score"].tolist() == [1, 2]
    assert plano["neutral"].tolist() == [True, False]


@pytest.mark.parametrize("nombre,col", [("RESULTS", "home_score"), ("RESULTS", "neutral")])
def test_to_plain_explota_si_quedo_un_faltante(tmp_path, nombre, col):
    """Presupone que ya se filtraron los faltantes. Si igual queda uno, tiene que
    gritar: inventar un 0 o un False ahi corrompe el Elo sin dejar rastro."""
    df = pd.DataFrame(FILAS[nombre]).copy()
    df[col] = pd.NA
    _, r1, _, _ = _ida_y_vuelta(tmp_path, df, ESQUEMAS[nombre])

    with pytest.raises(ValueError):
        csv_io.to_plain(r1, ESQUEMAS[nombre])


def test_to_plain_convierte_los_faltantes_de_float_en_nan(tmp_path):
    """Excepcion documentada a la regla de arriba: en una columna FLOAT el
    faltante tiene representacion propia (np.nan) y pandas no protesta. Vale para
    `ev_v3`, que es opcional -- pero no se puede contar con el error ahi."""
    _, r1, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS["PRONOSTICOS"]),
                                PRONOSTICOS)

    plano = csv_io.to_plain(r1[["ev_v3"]], {"ev_v3": FLOAT})

    assert plano["ev_v3"].dtype == np.dtype("float64")
    assert plano["ev_v3"].tolist()[0] == 1.25
    assert np.isnan(plano["ev_v3"].tolist()[1])


def test_to_plain_ignora_las_columnas_del_esquema_que_no_estan(results_leido):
    """Se lo llama sobre subconjuntos (`df[cols]`): pedir una columna ausente
    tiene que ser un no-op, no un KeyError."""
    plano = csv_io.to_plain(results_leido[["home_team", "home_score"]], RESULTS)
    assert list(plano) == ["home_team", "home_score"]
    assert plano["home_score"].dtype == np.dtype("int64")


def test_to_plain_no_toca_las_columnas_que_el_esquema_no_conoce(results_leido):
    results_leido["elo_home"] = [1500.5, 1490.0]
    plano = csv_io.to_plain(results_leido, RESULTS)
    assert plano["elo_home"].tolist() == [1500.5, 1490.0]


def test_to_plain_no_muta_el_dataframe_original(results_leido):
    """El modelo sigue usando el df tipado despues de pedir la version plana."""
    dtypes = results_leido.dtypes.copy()
    csv_io.to_plain(results_leido, RESULTS)
    assert results_leido.dtypes.equals(dtypes)


# --------------------------------------------------------------------------
# (j) booleanos: TRUE/FALSE de martj42 y True/False de pandas
# --------------------------------------------------------------------------
VERDADEROS = ["TRUE", "True", "true", " TRUE ", "1", "1.0"]
FALSOS = ["FALSE", "False", "false", " false ", "0", "0.0"]


@pytest.mark.parametrize("crudo", VERDADEROS)
def test_neutral_reconoce_las_formas_de_verdadero(tmp_path, crudo):
    """martj42 escribe TRUE/FALSE y pandas True/False; el "1.0" aparece cuando la
    columna paso por float. La que no matchea no explota: queda en NA, o sea que
    el partido pierde el dato de cancha neutral -- un feature del modelo."""
    leido = _celda(tmp_path, BOOL, crudo)
    assert not pd.isna(leido), f"{crudo!r} no se reconocio y quedo en NA"
    assert bool(leido) is True


@pytest.mark.parametrize("crudo", FALSOS)
def test_neutral_reconoce_las_formas_de_falso(tmp_path, crudo):
    leido = _celda(tmp_path, BOOL, crudo)
    assert not pd.isna(leido), f"{crudo!r} no se reconocio y quedo en NA"
    assert bool(leido) is False


def test_neutral_de_martj42_y_de_pandas_dan_lo_mismo(tmp_path):
    """Las dos fuentes conviven: results.csv lo baja martj42 (TRUE) y
    manual_results/pronosticos los escribe pandas (True)."""
    columnas = "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
    fila = "2026-06-15,Spain,Argentina,1,0,FIFA World Cup,Dallas,United States,{}\n"
    martj42 = csv_io.read(_csv(tmp_path, columnas + fila.format("TRUE"), "a.csv"), RESULTS)
    pandas_ = csv_io.read(_csv(tmp_path, columnas + fila.format("True"), "b.csv"), RESULTS)

    pd.testing.assert_frame_equal(martj42, pandas_)


def test_un_booleano_ya_tipado_pasa_intacto(tmp_path):
    """`_coerce` corre tambien en `write`, o sea sobre columnas que YA son boolean:
    si ahi se perdiera el valor, guardar dos veces daria archivos distintos."""
    _, r1, _, r2 = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS["RESULTS"]), RESULTS)
    assert r1["neutral"].tolist() == [True, False]
    assert r2["neutral"].tolist() == [True, False]


def test_los_booleanos_se_escriben_como_True_y_False(tmp_path):
    """Formato de salida: pandas relee True/False, y son las dos formas que ya
    conviven en los archivos del repo."""
    ida, _, _, _ = _ida_y_vuelta(tmp_path, pd.DataFrame(FILAS["RESULTS"]), RESULTS)
    lineas = ida.read_text(encoding="utf-8").splitlines()
    assert lineas[1].endswith(",True")
    assert lineas[2].endswith(",False")
