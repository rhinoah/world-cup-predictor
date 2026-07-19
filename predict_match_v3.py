#!/usr/bin/env python3
"""
predict_match_v3.py
===================
Version de PRODUCCION. Modelo de fuerzas ataque/defensa (v2) BLENDEADO con Elo
dinamico (peso w=0.6). En backtest sobre 9 torneos saca ~0.90 puntos/partido,
contra ~0.825 del modelo sin Elo y del baseline "1-0 al favorito".

Usar este por defecto.

Uso:
    python predict_match_v3.py "Mexico" "South Africa"
    python predict_match_v3.py "South Korea" "Czech Republic" --neutral
    python predict_match_v3.py "Mexico" "South Africa" --as-of 2026-06-11
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from predict_match_v2 import load_results, fit_iterative, score_matrix, modal
from elo import compute_elo, blended_lambdas

ELO_WEIGHT = 0.6


def predict(home, away, neutral, p, elo, w=ELO_WEIGHT):
    th, ta = p["tidx"][home], p["tidx"][away]
    g = 1.0 if neutral else p["gamma"]
    lh_f = p["mu"] * p["alpha"][th] * p["beta"][ta] * g
    la_f = p["mu"] * p["alpha"][ta] * p["beta"][th]
    eh, ea = elo.get(home, 1500.0), elo.get(away, 1500.0)
    lh, la = blended_lambdas(lh_f, la_f, eh, ea, neutral, w)
    M = score_matrix(lh, la)
    k = M.shape[0] - 1
    I, J = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
    p_home = float(M[I > J].sum())
    p_draw = float(M[I == J].sum())
    p_away = float(M[I < J].sum())
    pdir = np.where(I > J, p_home, np.where(I == J, p_draw, p_away))
    ev = 2.0 * M + pdir
    bi, bj = np.unravel_index(int(np.argmax(ev)), ev.shape)
    return dict(lh=lh, la=la, lh_f=lh_f, la_f=la_f, eh=eh, ea=ea, M=M, ev=ev,
                p_home=p_home, p_draw=p_draw, p_away=p_away,
                best=(int(bi), int(bj)), best_ev=float(ev[bi, bj]))


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
        mi, mj, mp, mev = modal(r["M"], r["ev"], rel)
        star = "  <==" if (mi, mj) == (bi, bj) else ""
        print(f"  {name:<18}{mi}-{mj}   P={mp*100:4.1f}%  EV={mev:.3f}{star}")
    print("\n" + "=" * 46)
    print(f"  CARGAR:  {args.home} {bi} - {bj} {args.away}")
    print(f"  (EV = {r['best_ev']:.3f} pts)")
    print("=" * 46 + "\n")


if __name__ == "__main__":
    main()
