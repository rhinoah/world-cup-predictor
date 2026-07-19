#!/usr/bin/env python3
"""
elo.py
======
Elo dinamico de selecciones (estilo World Football Elo): un rating de fuerza
que se actualiza partido a partido. Sin leakage por construccion (cronologico).
Ajusta por localia y por margen de gol; K mas alto en torneos importantes.

Provee:
  compute_elo(df)        -> (df + columnas elo_home_pre/elo_away_pre, dict elo final)
  blended_lambdas(...)   -> mezcla los lambdas del modelo de goles con los del Elo
"""
from __future__ import annotations

import numpy as np

HFA = 65.0           # ventaja de localia en puntos Elo (~0.4 gol)
C_SUPREMACY = 200.0  # puntos Elo por gol de supremacia esperada
TOTAL_GOALS = 2.60   # goles totales esperados base (para derivar lambdas del Elo)


def k_factor(tournament) -> float:
    t = str(tournament).lower()
    if "friendly" in t:
        return 20.0
    if "world cup" in t and "qual" not in t:
        return 60.0
    if "qual" in t:
        return 35.0
    if any(x in t for x in ["euro", "copa am", "cup of nations", "asian cup",
                            "gold cup", "nations league", "confederations"]):
        return 50.0
    return 40.0


def goal_mult(gd) -> float:
    d = abs(int(gd))
    if d <= 1:
        return 1.0
    if d == 2:
        return 1.5
    return (11.0 + d) / 8.0


def compute_elo(df):
    """Recorre el dataset cronologicamente y guarda el Elo PRE-partido de cada
    equipo en cada fila. Devuelve (df enriquecido, dict de Elo final as-of hoy)."""
    df = df.sort_values("date").reset_index(drop=True)
    elo: dict[str, float] = {}
    pre_h = np.empty(len(df))
    pre_a = np.empty(len(df))
    ht = df["home_team"].to_numpy(); at = df["away_team"].to_numpy()
    hs = df["home_score"].to_numpy(); as_ = df["away_score"].to_numpy()
    neu = df["neutral"].to_numpy(); tour = df["tournament"].to_numpy()
    for i in range(len(df)):
        h, a = ht[i], at[i]
        eh = elo.get(h, 1500.0); ea = elo.get(a, 1500.0)
        pre_h[i] = eh; pre_a[i] = ea
        dr = eh + (0.0 if neu[i] else HFA) - ea
        we = 1.0 / (1.0 + 10 ** (-dr / 400.0))     # expectativa del local
        gd = hs[i] - as_[i]
        w = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        k = k_factor(tour[i]) * goal_mult(gd)
        delta = k * (w - we)
        elo[h] = eh + delta
        elo[a] = ea - delta
    df = df.copy()
    df["elo_home_pre"] = pre_h
    df["elo_away_pre"] = pre_a
    return df, elo


def blended_lambdas(lh_f, la_f, elo_h, elo_a, neutral, w,
                    c=C_SUPREMACY, tg=TOTAL_GOALS):
    """Mezcla geometrica de los lambdas de fuerzas (modelo v2) con los derivados
    del Elo. w=0 -> solo fuerzas; w=1 -> solo Elo."""
    dr = elo_h + (0.0 if neutral else HFA) - elo_a
    sup = dr / c                                    # supremacia esperada en goles
    lh_e = max(tg / 2.0 + sup / 2.0, 0.15)
    la_e = max(tg / 2.0 - sup / 2.0, 0.15)
    lh = lh_f ** (1.0 - w) * lh_e ** w
    la = la_f ** (1.0 - w) * la_e ** w
    return lh, la
