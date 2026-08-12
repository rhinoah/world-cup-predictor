#!/usr/bin/env python3
"""
results.py
==========
Los resultados del torneo: el dataset de martj42 mas los partidos que se
cargaron a mano, y la busqueda de un marcador por (local, visitante).

Por que existe como modulo aparte: esto lo necesitan tanto la capa de datos de
la app (`app_data`) como el modelo (`predict_match_v2`) y la liquidacion
(`liquidar`). Vivia duplicado -- `_apply_override` y `apply_manual_overrides`
eran la misma funcion con la ruta escrita distinto, y el indice por equipos
estaba copiado tres veces, incluida la parte fea de desempatar cuando el indice
devuelve varias filas. Ponerlo en `app_data` obligaria al modelo a depender de
la capa de la GUI, y al reves seria peor; asi que va en el medio, donde los tres
pueden importarlo sin ciclos.

Las rutas se pasan por parametro y no se resuelven al importar: los tests
apuntan `app_data.BASE` y `predict_match_v2.DATA` a un directorio temporal, y
eso solo funciona si el valor se lee en el momento de la llamada.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from prode.data import csv_io

MANUAL_NAME = "manual_results.csv"

_SCORES = ["home_score", "away_score"]
_KEY = ["date", "home_team", "away_team"]


def load(results_csv) -> pd.DataFrame:
    """El dataset con los resultados cargados a mano ya aplicados."""
    return apply_overrides(csv_io.read(results_csv, csv_io.RESULTS), results_csv)


def apply_overrides(df: pd.DataFrame, results_csv, avisar=True) -> pd.DataFrame:
    """Aplica data/manual_results.csv sobre el dataset.

    Hay dos casos y no son el mismo:

    COMPLETAR (lo habitual). Se carga un partido a mano porque martj42 todavia
    no lo publico. Cuando lo publique, gana el oficial. Eso NO es capricho: es lo
    que corrige los errores de tipeo. Sobre las 101 cargas manuales de este repo,
    2 difieren del oficial (`England 3-2 Croatia` contra el 4-2 real) -- typos al
    cargar apurado, que esta regla arregla sola.

    CORREGIR (`corrige=True`). Se edito un partido que el dataset YA traia. Ahi
    la intencion es otra: alguien miro el marcador oficial, lo vio mal y lo
    cambio a proposito. Ese pisa. Sin esto el boton "editar resultado" de la app
    no hacia nada: escribia la fila y el oficial la ignoraba, sin avisar.

    `avisar`: informa por stderr los overrides que quedaron descartados por
    diferir del oficial. Son justamente los typos, que si no no se ven nunca.
    """
    man = csv_io.read(Path(results_csv).parent / MANUAL_NAME,
                      csv_io.MANUAL_RESULTS, missing_ok=True)
    man = man.dropna(subset=_KEY + _SCORES)
    if man.empty:
        return df
    # Sin esto el merge es 1-a-N y un cruce repetido en el override DUPLICA el
    # partido en el dataset: el Elo lo aplicaria dos veces y score_of elegiria
    # uno de los dos marcadores al azar. Gana el ultimo, que es el mas reciente.
    man = man.drop_duplicates(subset=_KEY, keep="last")
    if "corrige" not in man.columns:
        man = man.assign(corrige=pd.NA)
    df = df.merge(man[_KEY + _SCORES + ["corrige"]], on=_KEY, how="left",
                  suffixes=("", "_m"))

    pisa = df["corrige"].fillna(False).astype(bool) & df["home_score_m"].notna()
    if avisar:
        _avisar_descartados(df, pisa)
    for c in _SCORES:
        # el override entra si el oficial esta vacio, o si viene marcado para pisar
        df[c] = df[f"{c}_m"].where(pisa | df[c].isna() & df[f"{c}_m"].notna(), df[c])
    return df.drop(columns=[f"{c}_m" for c in _SCORES] + ["corrige"])


def _avisar_descartados(df: pd.DataFrame, pisa: pd.Series) -> None:
    """Los overrides que difieren del oficial y NO estan marcados para pisar.

    Se descartan (bien), pero en silencio no se enteraria nadie de que hay una
    carga mal tipeada dando vueltas."""
    distinto = (df["home_score"].notna() & df["home_score_m"].notna() & ~pisa
                & ((df["home_score"] != df["home_score_m"])
                   | (df["away_score"] != df["away_score_m"])))
    if not distinto.any():
        return
    print(f"aviso: {int(distinto.sum())} resultado(s) cargados a mano difieren del "
          "oficial y se descartan (el oficial manda salvo que se corrija a "
          "proposito desde la app):", file=sys.stderr)
    for _, r in df[distinto].head(5).iterrows():
        print(f"  {r['home_team']} vs {r['away_team']}: oficial "
              f"{r['home_score']}-{r['away_score']}, cargado "
              f"{r['home_score_m']}-{r['away_score_m']}", file=sys.stderr)


def by_teams(df: pd.DataFrame) -> pd.DataFrame:
    """Indexa los partidos JUGADOS por (local, visitante) para buscar marcadores.

    Los que no tienen marcador quedan afuera: dentro del Mundial cada cruce es
    unico, asi que la clave alcanza para encontrarlo."""
    jugados = df.dropna(subset=_SCORES)
    return jugados.set_index(["home_team", "away_team"])[_SCORES].sort_index()


def score_of(idx: pd.DataFrame, home, away):
    """(goles_local, goles_visitante) de un cruce, o None si no figura jugado.

    El `isinstance` no es paranoia: si el mismo cruce aparece repetido, `.loc`
    devuelve un DataFrame en vez de una fila y `int()` explotaria."""
    # pd.isna antes que el `not`: `not pd.NA` levanta "boolean value of NA is
    # ambiguous", y un equipo vacio en un CSV llega justamente como pd.NA.
    if home is None or away is None or pd.isna(home) or pd.isna(away):
        return None
    if (home, away) not in idx.index:
        return None
    rec = idx.loc[(home, away)]
    if isinstance(rec, pd.DataFrame):
        rec = rec.iloc[0]
    return int(rec["home_score"]), int(rec["away_score"])
