#!/usr/bin/env python3
"""
predict_match.py
================
Predice el MARCADOR a cargar en el prode (solo fase de grupos, scoring 3/1/0)
para un cruce puntual.

Modelo: Poisson de fuerzas ataque/defensa por seleccion, con decay temporal
(los partidos viejos pesan menos), peso reducido a los amistosos, ventaja de
localia estimada de los datos y correccion Dixon-Coles para los marcadores
bajos (0-0, 1-0, 0-1, 1-1), que es justo donde el Poisson pelado falla y donde
mas se juega el +3.

Regla de decision: maximiza el puntaje esperado del prode por partido,
    EV(m) = 2 * P(m) + P(direccion 1X2 de m)
sobre todos los marcadores plausibles. Solo hay 3 candidatos reales: el
marcador modal de cada direccion (gana local / empate / gana visita).

Sin data leakage: con --as-of FECHA, entrena solo con partidos anteriores.

Uso:
    python predict_match.py "Mexico" "South Africa"            # local vs visita
    python predict_match.py "Argentina" "Brazil" --neutral     # cancha neutral
    python predict_match.py "Mexico" "South Africa" --as-of 2010-06-11
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data/results.csv")

HALF_LIFE_YEARS = 3.0     # a los 3 anios un partido pesa la mitad
FRIENDLY_WEIGHT = 0.5     # los amistosos pesan la mitad que los oficiales
MAX_GOALS = 8             # truncamos la matriz de marcadores en 0..8
DC_RHO = -0.10            # correccion Dixon-Coles (valor tipico de la literatura)


def load_results(as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["home_score", "away_score", "date"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"] = df["neutral"].astype(str).str.upper().eq("TRUE")
    df = df.sort_values("date").reset_index(drop=True)
    if as_of is not None:
        df = df[df["date"] < as_of].reset_index(drop=True)  # sin leakage
    return df


def fit_strengths(df: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """Fuerzas de ataque/defensa por seleccion (ratios ponderados estilo Maher)."""
    age_years = (as_of - df["date"]).dt.days / 365.25
    w = (0.5 ** (age_years / HALF_LIFE_YEARS)).to_numpy()
    friendly = df["tournament"].str.contains("Friendly", case=False, na=False).to_numpy()
    w = w * np.where(friendly, FRIENDLY_WEIGHT, 1.0)

    hs = df["home_score"].to_numpy()
    as_ = df["away_score"].to_numpy()

    # ventaja de localia, desde partidos NO neutrales
    nn = ~df["neutral"].to_numpy()
    avg_home = np.average(hs[nn], weights=w[nn])
    avg_away = np.average(as_[nn], weights=w[nn])
    home_factor = math.sqrt(avg_home / avg_away)

    # baseline global de goles por equipo-partido
    mu = np.average(np.concatenate([hs, as_]), weights=np.concatenate([w, w]))

    # goles a favor / en contra ponderados por seleccion
    H = df["home_team"].to_numpy()
    A = df["away_team"].to_numpy()
    acc: dict[str, list[float]] = {}
    for i in range(len(df)):
        dh = acc.setdefault(H[i], [0.0, 0.0, 0.0, 0])
        dh[0] += w[i] * hs[i]; dh[1] += w[i] * as_[i]; dh[2] += w[i]; dh[3] += 1
        da = acc.setdefault(A[i], [0.0, 0.0, 0.0, 0])
        da[0] += w[i] * as_[i]; da[1] += w[i] * hs[i]; da[2] += w[i]; da[3] += 1

    attack, defense, ngames, wsum = {}, {}, {}, {}
    for t, (wgf, wga, ww, n) in acc.items():
        attack[t] = (wgf / ww) / mu      # >1 = ataque sobre la media
        defense[t] = (wga / ww) / mu     # <1 = defensa sobre la media (recibe poco)
        ngames[t] = n
        wsum[t] = ww
    return dict(mu=mu, home_factor=home_factor, attack=attack, defense=defense,
                ngames=ngames, wsum=wsum, avg_home=avg_home, avg_away=avg_away)


def dc_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
    """Correccion Dixon-Coles para las 4 celdas de marcadores bajos."""
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lh: float, la: float, kmax: int = MAX_GOALS) -> np.ndarray:
    ph = np.array([math.exp(-lh) * lh ** k / math.factorial(k) for k in range(kmax + 1)])
    pa = np.array([math.exp(-la) * la ** k / math.factorial(k) for k in range(kmax + 1)])
    M = np.outer(ph, pa)
    for i in (0, 1):
        for j in (0, 1):
            M[i, j] *= dc_tau(i, j, lh, la, DC_RHO)
    return M / M.sum()


def predict(home: str, away: str, neutral: bool, p: dict) -> dict:
    hf = 1.0 if neutral else p["home_factor"]
    lh = p["mu"] * p["attack"][home] * p["defense"][away] * hf
    la = p["mu"] * p["attack"][away] * p["defense"][home] / hf
    M = score_matrix(lh, la)
    k = M.shape[0] - 1
    I, J = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
    p_home = float(M[I > J].sum())
    p_draw = float(M[I == J].sum())
    p_away = float(M[I < J].sum())
    pdir = np.where(I > J, p_home, np.where(I == J, p_draw, p_away))
    ev = 2.0 * M + pdir
    bi, bj = np.unravel_index(int(np.argmax(ev)), ev.shape)
    return dict(lh=lh, la=la, M=M, p_home=p_home, p_draw=p_draw, p_away=p_away,
                ev=ev, best=(int(bi), int(bj)), best_ev=float(ev[bi, bj]))


def modal(M: np.ndarray, ev: np.ndarray, rel) -> tuple:
    """Marcador mas probable dentro de una direccion 1X2 (rel: i,j -> bool)."""
    k = M.shape[0] - 1
    cells = [(M[i, j], ev[i, j], i, j)
             for i in range(k + 1) for j in range(k + 1) if rel(i, j)]
    pm, evm, i, j = max(cells)
    return i, j, pm, evm


def main() -> None:
    ap = argparse.ArgumentParser(description="Marcador a cargar en el prode (3/1/0)")
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--neutral", action="store_true", help="Cancha neutral")
    ap.add_argument("--as-of", default=None, help="Entrenar como si fuera YYYY-MM-DD")
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of) if args.as_of else None
    df = load_results(as_of=as_of)
    if as_of is None:
        as_of = df["date"].max() + pd.Timedelta(days=1)
    p = fit_strengths(df, as_of)

    for t in (args.home, args.away):
        if t not in p["attack"]:
            near = [x for x in p["attack"] if t.lower() in x.lower() or x.lower() in t.lower()]
            print(f"ERROR: '{t}' no esta en el dataset. Quisiste decir: {near[:6]}")
            raise SystemExit(1)

    r = predict(args.home, args.away, args.neutral, p)
    venue = "cancha neutral" if args.neutral else f"{args.home} de local"
    bi, bj = r["best"]

    print(f"\n=== {args.home} vs {args.away}  ({venue}) ===")
    print(f"datos hasta: {as_of.date()}   |  half-life {HALF_LIFE_YEARS}a, "
          f"amistosos x{FRIENDLY_WEIGHT}, Dixon-Coles rho={DC_RHO}\n")

    print(f"{args.home}: ataque {p['attack'][args.home]:.2f}  defensa "
          f"{p['defense'][args.home]:.2f}  ({p['ngames'][args.home]} PJ)")
    print(f"{args.away}: ataque {p['attack'][args.away]:.2f}  defensa "
          f"{p['defense'][args.away]:.2f}  ({p['ngames'][args.away]} PJ)")
    print(f"\ngoles esperados (lambda):  {args.home} {r['lh']:.2f}  -  "
          f"{r['la']:.2f} {args.away}")

    print(f"\nprobabilidades 1X2:")
    print(f"  gana {args.home:<14} {r['p_home']*100:5.1f}%")
    print(f"  empate              {r['p_draw']*100:5.1f}%")
    print(f"  gana {args.away:<14} {r['p_away']*100:5.1f}%")

    k = r["M"].shape[0] - 1
    flat = sorted(((r["M"][i, j], i, j) for i in range(k + 1) for j in range(k + 1)),
                  reverse=True)
    print(f"\nmarcadores mas probables:")
    for pm, i, j in flat[:6]:
        tag = "  <- mas probable" if (i, j) == (flat[0][1], flat[0][2]) else ""
        print(f"  {i}-{j}   {pm*100:5.1f}%{tag}")

    print(f"\ncandidatos por direccion (marcador modal + su EV):")
    for name, rel in (("gana " + args.home, lambda i, j: i > j),
                      ("empate", lambda i, j: i == j),
                      ("gana " + args.away, lambda i, j: i < j)):
        mi, mj, mp, mev = modal(r["M"], r["ev"], rel)
        star = "  <==" if (mi, mj) == (bi, bj) else ""
        print(f"  {name:<18} {mi}-{mj}   P={mp*100:4.1f}%   EV={mev:.3f}{star}")

    print("\n" + "=" * 46)
    print(f"  CARGAR:  {args.home} {bi} - {bj} {args.away}")
    print(f"  (EV esperado = {r['best_ev']:.3f} puntos)")
    print("=" * 46 + "\n")


if __name__ == "__main__":
    main()
