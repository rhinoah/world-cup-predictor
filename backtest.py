#!/usr/bin/env python3
"""
backtest.py
===========
Valida el modelo midiendo el PUNTAJE DEL PRODE (3/1/0) que habria sacado en
torneos pasados, contra baselines tontos. Para cada torneo entrena SOLO con
partidos anteriores a su inicio (sin leakage) y predice cada partido.

Compara, en puntos promedio por partido:
  - EV      : modelo v2 + regla de decision EV = 2*P(m) + P(direccion)
  - MLpred  : modelo v2, marcador mas probable (sin la regla EV) -> aisla su valor
  - 1-0fav  : baseline "1-0 (o 0-1) al favorito por lambda"
  - 1-1     : baseline "siempre empate 1-1"

Uso:
    python backtest.py
"""
from __future__ import annotations

import numpy as np

from predict_match_v2 import load_results, fit_iterative, score_matrix
from scoring import points as prode_points, best_ev_score, most_likely_score

# torneos finales (no clasificatorias) a evaluar
TARGET_TOURNAMENTS = ["FIFA World Cup", "UEFA Euro", "Copa América"]
MIN_YEAR = 2016


def lambdas(h, a, neutral, p):
    th, ta = p["tidx"][h], p["tidx"][a]
    g = 1.0 if neutral else p["gamma"]
    return (p["mu"] * p["alpha"][th] * p["beta"][ta] * g,
            p["mu"] * p["alpha"][ta] * p["beta"][th])


def main():
    full = load_results()
    games = []
    for patt in TARGET_TOURNAMENTS:
        sub = full[(full["tournament"] == patt) & (full["date"].dt.year >= MIN_YEAR)]
        for yr, g in sub.groupby(sub["date"].dt.year):
            games.append((f"{patt} {yr}", g))
    games.sort(key=lambda r: r[1]["date"].min())

    agg = {"EV": 0, "MLE": 0, "fav": 0, "draw": 0, "n": 0}
    hdr = f"{'torneo':<22}{'PJ':>4}{'EV':>8}{'MLpred':>8}{'1-0fav':>8}{'1-1':>8}"
    print(hdr)
    print("-" * len(hdr))
    for label, g in games:
        start = g["date"].min()
        train = full[full["date"] < start]
        if len(train) < 5000:
            continue
        p = fit_iterative(train, start)
        s = {"EV": 0, "MLE": 0, "fav": 0, "draw": 0}
        n = 0
        for _, m in g.iterrows():
            h, a = m["home_team"], m["away_team"]
            if h not in p["tidx"] or a not in p["tidx"]:
                continue
            real = (int(m["home_score"]), int(m["away_score"]))
            lh, la = lambdas(h, a, bool(m["neutral"]), p)
            M = score_matrix(lh, la)
            s["EV"] += prode_points(best_ev_score(M), real)
            s["MLE"] += prode_points(most_likely_score(M), real)
            fav = (1, 0) if lh > la else ((0, 1) if la > lh else (1, 1))
            s["fav"] += prode_points(fav, real)
            s["draw"] += prode_points((1, 1), real)
            n += 1
        if n == 0:
            continue
        for k in s:
            agg[k] += s[k]
        agg["n"] += n
        print(f"{label:<22}{n:>4}{s['EV']/n:>8.3f}{s['MLE']/n:>8.3f}"
              f"{s['fav']/n:>8.3f}{s['draw']/n:>8.3f}")

    n = max(agg["n"], 1)
    print("-" * len(hdr))
    print(f"{'TOTAL':<22}{agg['n']:>4}{agg['EV']/n:>8.3f}{agg['MLE']/n:>8.3f}"
          f"{agg['fav']/n:>8.3f}{agg['draw']/n:>8.3f}")
    print("\n(numeros = puntos promedio por partido bajo el scoring 3/1/0)")


if __name__ == "__main__":
    main()
