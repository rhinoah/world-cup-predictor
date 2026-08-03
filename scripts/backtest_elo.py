#!/usr/bin/env python3
"""
backtest_elo.py
===============
Como backtest.py pero prueba BLENDEAR el modelo de fuerzas (v2) con el Elo,
para ver si discrimina mejor a los favoritos y supera al baseline "1-0 al
favorito". Reporta puntos/partido (regla EV) para varios pesos w del Elo.
"""
from __future__ import annotations

from prode.model.predict_match_v2 import load_results, fit_iterative, score_matrix
from prode.model.elo import compute_elo, blended_lambdas, HFA
from prode.model.scoring import points as prode_points, best_ev_score as best_ev

TARGET = ["FIFA World Cup", "UEFA Euro", "Copa América"]
MIN_YEAR = 2016
# El Mundial 2026 YA esta en data/results.csv y queda AFUERA a proposito: es el
# out-of-sample contra el que se contrasta lo que promete este backtest. Si
# entrara, el numero "esperado" incluiria al torneo que valida ese esperado.
MAX_YEAR = 2024
# w=0.6 es el de PRODUCCION (predict_match_v3.ELO_WEIGHT): tiene que estar en la
# grilla, si no el unico numero que importa hay que interpolarlo a ojo.
WEIGHTS = [0.0, 0.3, 0.5, 0.6, 0.7, 1.0]


def main():
    full = load_results()
    full, _ = compute_elo(full)

    games = []
    for patt in TARGET:
        sub = full[(full["tournament"] == patt)
                   & (full["date"].dt.year >= MIN_YEAR)
                   & (full["date"].dt.year <= MAX_YEAR)]
        for yr, g in sub.groupby(sub["date"].dt.year):
            games.append((f"{patt} {yr}", g))
    games.sort(key=lambda r: r[1]["date"].min())

    tot = {w: 0 for w in WEIGHTS}
    tot["fav"] = 0
    N = 0
    head = f"{'torneo':<22}{'PJ':>4}  " + "".join(f"{'w='+str(w):<8}" for w in WEIGHTS) + f"{'1-0fav':>8}"
    print(head)
    print("-" * len(head))
    for label, g in games:
        start = g["date"].min()
        train = full[full["date"] < start]
        if len(train) < 5000:
            continue
        p = fit_iterative(train, start)
        s = {w: 0 for w in WEIGHTS}
        s["fav"] = 0
        n = 0
        for _, m in g.iterrows():
            h, a = m["home_team"], m["away_team"]
            if h not in p["tidx"] or a not in p["tidx"]:
                continue
            real = (int(m["home_score"]), int(m["away_score"]))
            neutral = bool(m["neutral"])
            th, ta = p["tidx"][h], p["tidx"][a]
            gg = 1.0 if neutral else p["gamma"]
            lh_f = p["mu"] * p["alpha"][th] * p["beta"][ta] * gg
            la_f = p["mu"] * p["alpha"][ta] * p["beta"][th]
            eh, ea = m["elo_home_pre"], m["elo_away_pre"]
            for w in WEIGHTS:
                lh, la = blended_lambdas(lh_f, la_f, eh, ea, neutral, w)
                s[w] += prode_points(best_ev(score_matrix(lh, la)), real)
            drr = eh + (0.0 if neutral else HFA) - ea
            fav = (1, 0) if drr > 0 else ((0, 1) if drr < 0 else (1, 1))
            s["fav"] += prode_points(fav, real)
            n += 1
        if n == 0:
            continue
        for w in WEIGHTS:
            tot[w] += s[w]
        tot["fav"] += s["fav"]
        N += n
        row = "".join(f"{s[w]/n:<8.3f}" for w in WEIGHTS)
        print(f"{label:<22}{n:>4}  {row}{s['fav']/n:>8.3f}")

    print("-" * len(head))
    row = "".join(f"{tot[w]/N:<8.3f}" for w in WEIGHTS)
    print(f"{'TOTAL':<22}{N:>4}  {row}{tot['fav']/N:>8.3f}")
    print("\nw = peso del Elo en el blend (w=0 solo fuerzas de goles, w=1 solo Elo)")
    print("numeros = puntos/partido (3/1/0) con la regla EV")


if __name__ == "__main__":
    main()
