#!/usr/bin/env python3
"""
predict_match_v3.py
===================
El modelo de PRODUCCION. Usar este por defecto.

Toma el motor de predict_match_v2 (carga de datos, fuerzas de ataque/defensa,
matriz de marcadores) y le blendea el Elo dinamico de elo.py con peso w=0.6.
Lo unico que agrega este archivo es ese blend: son 13 lineas.

POR QUE EXISTE: las fuerzas de goles solas no le ganan al baseline tonto. Sobre
los mismos 9 torneos (2016-2024), "1-0 al favorito" saca 0.835 y el modelo de
fuerzas 0.827 -- pierde. El blend saca 0.912 (`backtest_elo.py`, w=0.6), y en el
Mundial 2026, out-of-sample, rindio 0.88.

QUE APORTA EL ELO, MEDIDO: no es elegir mejor al favorito. Sobre esos 399
partidos, el favorito por fuerzas y el favorito por Elo aciertan la direccion
EXACTAMENTE igual (219/399 los dos), eligen al mismo en 354 y empatan 13 a 13 en
los 45 que discrepan. Lo que aporta es la ESCALA: `blended_lambdas` ancla los
goles totales en TOTAL_GOALS=2.60 repartidos por supremacia, y eso corrige un
sesgo del modelo de fuerzas, que los subestimaba.

    goles totales reales      media 2.49
    solo fuerzas (w=0)        media 2.33   sd 0.38   -> 57 marcadores exactos
    blend con Elo (w=0.6)     media 2.47   sd 0.16   -> 69 marcadores exactos

O sea: el Elo no mejora QUIEN gana sino CUANTOS goles, y como el prode paga
triple el marcador exacto, ahi esta el salto de 0.827 a 0.912.

Quien lo corre: build_pronosticos.py (los sugeridos de la app),
predict_matchday.py (la jornada del dia) y backfill_ev.py (el EV as-of).

Uso:
    python -m prode.model.predict_match_v3 "Mexico" "South Africa"
    python -m prode.model.predict_match_v3 "South Korea" "Czech Republic" --neutral
    python -m prode.model.predict_match_v3 "Mexico" "South Africa" --as-of 2026-06-11
"""
from __future__ import annotations

import argparse

import pandas as pd

from prode.model import scoring
from prode.model.predict_match_v2 import load_results, fit_iterative, score_matrix
from prode.model.elo import compute_elo, blended_lambdas

ELO_WEIGHT = 0.6


def predict(home, away, neutral, p, elo, w=ELO_WEIGHT):
    th, ta = p["tidx"][home], p["tidx"][away]
    g = 1.0 if neutral else p["gamma"]
    lh_f = p["mu"] * p["alpha"][th] * p["beta"][ta] * g
    la_f = p["mu"] * p["alpha"][ta] * p["beta"][th]
    eh, ea = elo.get(home, 1500.0), elo.get(away, 1500.0)
    lh, la = blended_lambdas(lh_f, la_f, eh, ea, neutral, w)
    M = score_matrix(lh, la)
    ev, p_home, p_draw, p_away = scoring.ev_matrix(M)
    bi, bj = scoring.best_ev_score(M)
    return dict(lh=lh, la=la, lh_f=lh_f, la_f=la_f, eh=eh, ea=ea, M=M, ev=ev,
                p_home=p_home, p_draw=p_draw, p_away=p_away,
                best=(bi, bj), best_ev=float(ev[bi, bj]))


def main():
    ap = argparse.ArgumentParser(description="Marcador a cargar (v3: fuerzas + Elo)")
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--neutral", action="store_true")
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of) if args.as_of else None
    df = load_results(as_of=as_of)
    if as_of is None:
        as_of = df["date"].max() + pd.Timedelta(days=1)
    _, elo = compute_elo(df)
    p = fit_iterative(df, as_of)

    for t in (args.home, args.away):
        if t not in p["tidx"]:
            near = [x for x in p["teams"] if t.lower() in x.lower() or x.lower() in t.lower()]
            print(f"ERROR: '{t}' no esta. Quisiste decir: {near[:6]}")
            raise SystemExit(1)

    r = predict(args.home, args.away, args.neutral, p, elo)
    bi, bj = r["best"]
    venue = "cancha neutral" if args.neutral else f"{args.home} de local"
    print(f"\n=== [v3 Elo-blend] {args.home} vs {args.away}  ({venue}) ===")
    print(f"Elo: {args.home} {r['eh']:.0f}  -  {r['ea']:.0f} {args.away}")
    print(f"lambda fuerzas {r['lh_f']:.2f}-{r['la_f']:.2f}  ->  blend Elo (w={ELO_WEIGHT}): "
          f"{r['lh']:.2f}-{r['la']:.2f}")
    print(f"\nprobabilidades 1X2:")
    print(f"  gana {args.home:<16}{r['p_home']*100:5.1f}%")
    print(f"  empate                {r['p_draw']*100:5.1f}%")
    print(f"  gana {args.away:<16}{r['p_away']*100:5.1f}%")
    k = r["M"].shape[0] - 1
    flat = sorted(((r["M"][i, j], i, j) for i in range(k + 1) for j in range(k + 1)),
                  reverse=True)
    print(f"\nmarcadores mas probables:")
    for pm, i, j in flat[:6]:
        print(f"  {i}-{j}   {pm*100:5.1f}%")
    print(f"\ncandidatos por direccion (modal + EV):")
    for name, rel in (("gana " + args.home, lambda i, j: i > j),
                      ("empate", lambda i, j: i == j),
                      ("gana " + args.away, lambda i, j: i < j)):
        mi, mj, mp, mev = scoring.modal(r["M"], r["ev"], rel)
        star = "  <==" if (mi, mj) == (bi, bj) else ""
        print(f"  {name:<18}{mi}-{mj}   P={mp*100:4.1f}%  EV={mev:.3f}{star}")
    print("\n" + "=" * 46)
    print(f"  CARGAR:  {args.home} {bi} - {bj} {args.away}")
    print(f"  (EV = {r['best_ev']:.3f} pts)")
    print("=" * 46 + "\n")


if __name__ == "__main__":
    main()
