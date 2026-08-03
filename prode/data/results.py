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

from pathlib import Path

import pandas as pd

from prode.data import csv_io

MANUAL_NAME = "manual_results.csv"

_SCORES = ["home_score", "away_score"]
_KEY = ["date", "home_team", "away_team"]


def load(results_csv) -> pd.DataFrame:
    """El dataset con los resultados cargados a mano ya aplicados."""
    return apply_overrides(csv_io.read(results_csv, csv_io.RESULTS), results_csv)


def apply_overrides(df: pd.DataFrame, results_csv) -> pd.DataFrame:
    """Completa los marcadores que martj42 todavia no publico, desde
    data/manual_results.csv (mismo esquema, al lado del dataset).

    Solo rellena lo que esta vacio: nunca pisa un resultado oficial. Sirve para
    cargar un partido ya jugado mientras el dataset publico tarda en actualizarse.
    """
    man = csv_io.read(Path(results_csv).parent / MANUAL_NAME,
                      csv_io.MANUAL_RESULTS, missing_ok=True)
    man = man.dropna(subset=_KEY + _SCORES)
    if man.empty:
        return df
    df = df.merge(man[_KEY + _SCORES], on=_KEY, how="left", suffixes=("", "_m"))
    for c in _SCORES:
        df[c] = df[c].where(df[c].notna(), df[f"{c}_m"])
    return df.drop(columns=[f"{c}_m" for c in _SCORES])


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
    if not home or not away or (home, away) not in idx.index:
        return None
    rec = idx.loc[(home, away)]
    if isinstance(rec, pd.DataFrame):
        rec = rec.iloc[0]
    return int(rec["home_score"]), int(rec["away_score"])
