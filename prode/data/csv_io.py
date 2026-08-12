#!/usr/bin/env python3
"""
csv_io.py
=========
Lectura y escritura tipada de los CSV del proyecto. Fuente UNICA de los dtypes:
antes cada modulo re-parseaba a mano y cada copia podia quedar distinta --
`neutral` se convertia con `.astype(str).str.upper().eq("TRUE")` en cuatro
archivos, las fechas en seis, y antes de cada `to_csv` habia que acordarse de
castear a `Int64` para que las columnas enteras no se guardaran como decimales.

EL BUG QUE MOTIVA EL MODULO
---------------------------
Sin dtypes declarados, UN SOLO faltante degrada la columna entera. Guardando dos
pronosticos recien cargados (todavia sin resultado) y volviendo a leer el CSV,
el codigo viejo devolvia esto:

    pred_home     int64        <- ok, no tiene faltantes
    actual_home   float64      <- goles con coma
    points        float64      <- puntos con coma
    notes         float64      <- una columna de TEXTO, tipada como numero

De ahi salio el bug de los penales: `home_pens` casi siempre esta vacia, asi que
la columna era float y los penales se guardaban como "3.0" en vez de "3". Por
eso `set_result` tenia que acordarse de re-castear con `to_numeric` en CADA
guardado, y `liquidar`/`backfill_ev` repetian un `.astype("Int64")` antes de
cada `to_csv` para que el archivo no se degradara solo.

La solucion son los dtypes NULLABLE de pandas (`Int64`, `Float64`, `boolean`),
que hacen round-trip exacto por CSV: el faltante se escribe como campo vacio y
se relee como `pd.NA`, sin arrastrar la columna a float.

(Aparte, escribir `""` a mano para decir "sin dato" -- como hacia
`set_prediction` -- funciona de casualidad: pandas lo normaliza a campo vacio
al guardar. Pero en una columna de object la escribe ENTRECOMILLADA y ahi si
queda un `""` literal en el archivo. Por eso aca el faltante es siempre pd.NA.)

CONVENCIONES
------------
* El faltante SIEMPRE es `pd.NA`. Nunca `""`, nunca 0, nunca "None".
* VACIO no es lo mismo que ILEGIBLE. Que un partido no tenga marcador es normal
  (no se jugo todavia); que tenga escrito "2-1" en la columna de goles no. Las
  columnas marcadas con STRICT distinguen los dos casos y avisan del segundo:
  ver el comentario de STRICT mas abajo.
* El texto se tipa en el parser, no despues: una columna de notas que contiene
  "5" tiene que volver como "5" y no como "5.0".
* `read()` tolera que falte una columna del esquema (la crea vacia) y NO
  descarta las columnas de mas: si un CSV trae datos que el esquema no conoce,
  se conservan tal cual en vez de perderse en el proximo guardado.
* `to_plain()` es la contracara: el modelo hace `.to_numpy()` sobre estas
  columnas y los dtypes nullable son *masked arrays* que romperian ese codigo.
  Despues de filtrar los faltantes se vuelve a int64/bool planos.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# tipos logicos de columna
# --------------------------------------------------------------------------
TEXT = "text"            # texto (se lee como string, nunca como numero)
INT = "int"              # entero que admite faltantes -> Int64
FLOAT = "float"          # decimal que admite faltantes -> Float64
BOOL = "bool"            # booleano que admite faltantes -> boolean
DATE = "date"            # fecha sin hora, se guarda como YYYY-MM-DD
TIMESTAMP = "timestamp"  # fecha con hora, se guarda como YYYY-MM-DD HH:MM

# Sufijo que marca una columna ESTRICTA: vacia se admite (un partido sin jugar no
# tiene marcador), pero un valor escrito que no se entiende es un error y no un
# faltante. La diferencia importa: si un "2-1" tipeado mal en el marcador se
# convierte en NA, el partido pasa a figurar como NO JUGADO y el tablero miente
# sin dejar rastro. En una columna opcional (penales, notas) tolerar es correcto;
# en las que sostienen el resto, callarse no.
STRICT = "!"

# Formato de salida de cada tipo temporal. Sin segundos: es el que ya tenia
# fixture_horarios.csv, y asi guardar un archivo no lo reescribe entero.
DATE_FMT = "%Y-%m-%d"
TIMESTAMP_FMT = "%Y-%m-%d %H:%M"
_TIME_FORMAT = {DATE: DATE_FMT, TIMESTAMP: TIMESTAMP_FMT}

# --------------------------------------------------------------------------
# esquemas: una entrada por CSV del proyecto
# --------------------------------------------------------------------------
# El dataset de martj42 (data/results.csv). No lo escribimos nosotros: lo baja
# build_features.py, asi que el esquema solo describe como leerlo.
RESULTS = {
    "date": DATE + STRICT,           # ordena y filtra todo el dataset
    "home_team": TEXT,
    "away_team": TEXT,
    "home_score": INT + STRICT,      # vacio = todavia no se jugo; ilegible = error
    "away_score": INT + STRICT,
    "tournament": TEXT,
    "city": TEXT,
    "country": TEXT,
    "neutral": BOOL + STRICT,        # decide si aplica la localia
}

# Resultados cargados a mano (data/manual_results.csv): completan lo que martj42
# todavia no publico. Los penales son enteros que casi siempre faltan -- son
# justo la columna donde pegaba el bug del dtype degradado.
MANUAL_RESULTS = {
    "date": DATE + STRICT,
    "home_team": TEXT,
    "away_team": TEXT,
    "home_score": INT + STRICT,      # este archivo se tipea a mano: un marcador
    "away_score": INT + STRICT,      # mal escrito tiene que avisar, no evaporarse
    "home_pens": INT,                # casi siempre vacia: tolerante a proposito
    "away_pens": INT,
    # "este marcador PISA al oficial". Lo pone `set_result` solo cuando se edita
    # un partido que el dataset YA traia: si no hay oficial, completar es lo
    # normal y no hay nada que pisar. Ver `results.apply_overrides`.
    "corrige": BOOL,
}

# Los pronosticos del usuario (pronosticos.csv).
PRONOSTICOS = {
    "date": DATE + STRICT,
    "home_team": TEXT,
    "away_team": TEXT,
    "pred_home": INT + STRICT,       # es EL dato del prode
    "pred_away": INT + STRICT,
    "neutral": BOOL,
    "model": TEXT,
    "ev_v3": FLOAT,
    "actual_home": INT + STRICT,
    "actual_away": INT + STRICT,
    "points": INT + STRICT,
    "notes": TEXT,
    "load_gel": INT,
    "load_meli": INT,
}

# Partidos marcados como terminados a mano (data/finished.csv).
FINISHED = {
    "home_team": TEXT,
    "away_team": TEXT,
}

# Fixture con los horarios en hora argentina (fixture_horarios.csv).
HORARIOS = {
    "home_team": TEXT,
    "away_team": TEXT,
    # Estricta: un horario ilegible se colaba como NaT hasta la GUI, donde
    # `f"{kickoff:%H:%M}"` explota con un error que no dice de que partido es.
    "kickoff_arg": TIMESTAMP + STRICT,
}


# --------------------------------------------------------------------------
# lectura / escritura
# --------------------------------------------------------------------------
def empty(schema: dict) -> pd.DataFrame:
    """DataFrame vacio con las columnas y los dtypes del esquema.

    Tiene que dar los MISMOS dtypes que `read()` de un archivo sin filas: si no,
    un test que arranca de una tabla vacia no representa lo que pasa en serio."""
    df = pd.DataFrame({c: pd.Series(dtype="string") for c in schema})
    return _coerce(df, schema)


def read(path, schema: dict, *, missing_ok: bool = False) -> pd.DataFrame:
    """Lee un CSV aplicando el esquema.

    Las columnas que falten se crean vacias y las que sobren se conservan (un
    CSV con datos que el esquema no conoce no los pierde al volver a guardarlo).

    `missing_ok=True` devuelve una tabla vacia si el archivo no existe o esta en
    blanco; es para los que son opcionales de verdad (los overrides manuales,
    los pronosticos todavia no cargados). Por defecto se propaga el
    FileNotFoundError: que falte results.csv o el fixture es un error, y devolver
    una tabla vacia ahi haria que el modelo entrene con la nada y prediga
    cualquier cosa en silencio."""
    path = Path(path)
    if missing_ok and not path.exists():
        return empty(schema)
    # El texto se tipa en el parser y no despues: si no, una columna de notas con
    # "5" adentro se lee como numero y al reescribirla queda "5.0".
    text_cols = {c: "string" for c, k in schema.items() if _kind(k) == TEXT}
    try:
        df = pd.read_csv(path, dtype=text_cols)
    except pd.errors.EmptyDataError:
        if not missing_ok:
            raise
        return empty(schema)
    return _coerce(df, schema, source=path)


def write(df: pd.DataFrame, path, schema: dict) -> None:
    """Guarda respetando los dtypes: los faltantes quedan como campo vacio.

    Las columnas del esquema van primero y en su orden; las de mas quedan
    detras. Las fechas se escriben sin hora y los timestamps sin segundos.

    La escritura es ATOMICA (archivo temporal + reemplazo): pronosticos.csv es
    el unico dato del proyecto que no se puede regenerar, y un corte en la mitad
    de un `to_csv` lo dejaria truncado."""
    path = Path(path)
    out = _coerce(df.copy(), schema, source=path)
    for col, kind in schema.items():
        if (k := _kind(kind)) in _TIME_FORMAT:
            out[col] = out[col].dt.strftime(_TIME_FORMAT[k])
    out = out[[c for c in schema] + [c for c in out.columns if c not in schema]]

    tmp = path.with_suffix(path.suffix + ".tmp")
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)


def to_plain(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """Pasa los dtypes nullable a numpy planos (Int64 -> int64, boolean -> bool).

    Hace falta antes de darle el DataFrame al modelo: `fit_iterative` y
    `compute_elo` trabajan con `.to_numpy()`, y un dtype nullable devuelve un
    masked array donde `~neutral` o `.astype(float)` no se comportan igual.
    Presupone que ya se filtraron los faltantes de esas columnas: si queda
    alguno, `astype` avisa con un error en vez de inventar un valor."""
    out = df.copy()
    for col, kind in schema.items():
        if col not in out.columns:
            continue
        k = _kind(kind)
        if k == INT:
            out[col] = out[col].astype("int64")
        elif k == BOOL:
            out[col] = out[col].astype("bool")
        elif k == FLOAT:
            out[col] = out[col].astype("float64")
    return out


def _kind(marked: str) -> str:
    """Tipo de la columna, sin la marca de estricta."""
    return marked[:-len(STRICT)] if marked.endswith(STRICT) else marked


def _coerce(df: pd.DataFrame, schema: dict, source=None) -> pd.DataFrame:
    """Aplica el esquema: crea lo que falta, convierte, y no toca lo de mas.

    En las columnas normales la conversion es TOLERANTE: lo que no se entiende
    queda en `pd.NA` en vez de reventar, porque estos CSV se editan a mano y una
    celda con basura no puede dejar la app sin arrancar. En las marcadas con
    STRICT es al reves: un valor escrito que no se entiende levanta un error que
    nombra archivo, columna y fila. La celda VACIA se admite en las dos (que un
    partido no tenga marcador es el estado normal antes de jugarse)."""
    for col, marked in schema.items():
        kind = _kind(marked)
        if col not in df.columns:
            df[col] = pd.NA
        antes = df[col]
        if kind in _TIME_FORMAT:
            # format="mixed" parsea cada celda por su cuenta: sin eso, UNA fila
            # con otro formato manda a NaT a todas las demas de la columna.
            despues = pd.to_datetime(antes, errors="coerce", format="mixed")
        elif kind == TEXT:
            despues = antes.astype("string")
        elif kind == BOOL:
            despues = _to_bool(antes)
        elif kind == INT:
            despues = _to_int(antes)
        else:
            despues = pd.to_numeric(antes, errors="coerce").astype("Float64")
        if marked.endswith(STRICT):
            _check_strict(antes, despues, col, source)
        df[col] = despues.where(despues.notna(), pd.NA) if kind == TEXT else despues
    return df


def _check_strict(antes: pd.Series, despues: pd.Series, col: str, source) -> None:
    """Levanta si una celda con contenido no se pudo interpretar.

    Vacia -> NA esta bien; "2-1" -> NA no, porque el partido pasaria a figurar
    como no jugado y nadie se enteraria."""
    tenia_algo = antes.notna() & (antes.astype("string").str.strip() != "")
    ilegibles = despues.isna() & tenia_algo
    if not ilegibles.any():
        return
    filas = despues.index[ilegibles][:5]
    detalle = ", ".join(f"fila {i}: {antes[i]!r}" for i in filas)
    mas = "..." if int(ilegibles.sum()) > len(filas) else ""
    donde = f"{source}: " if source is not None else ""
    raise ValueError(f"{donde}la columna '{col}' tiene "
                     f"{int(ilegibles.sum())} valor(es) que no se entienden "
                     f"({detalle}{mas}). Corregilos o dejalos vacios.")


def _to_int(s: pd.Series) -> pd.Series:
    """A entero con faltantes. Un decimal que no es entero es basura para estas
    columnas (goles, penales, puntos), asi que se descarta en vez de redondear.

    El acotado a 2^53 no es capricho: sin el, un `inf` o un numero mas grande que
    int64 hacen que `astype` tire OverflowError y la app no abra."""
    num = pd.to_numeric(s, errors="coerce")
    entero_razonable = (num > -2**53) & (num < 2**53) & (num == num.round())
    return num.where(num.isna() | entero_razonable).astype("Int64")


def _to_bool(s: pd.Series) -> pd.Series:
    """A booleano con faltantes, aceptando lo que escriben las distintas fuentes:
    el dataset de martj42 usa TRUE/FALSE y pandas escribe True/False."""
    txt = s.astype("string").str.strip().str.lower()
    return txt.map({"true": True, "1": True, "1.0": True,
                    "false": False, "0": False, "0.0": False}).astype("boolean")
