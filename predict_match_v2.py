#!/usr/bin/env python3
"""
predict_match_v2.py
===================
Igual que predict_match.py pero con fuerzas de ataque/defensa estimadas
AJUSTANDO POR LA FUERZA DEL RIVAL (estimacion iterativa de maxima verosimilitud
estilo Maher / Dixon-Coles), en vez de promedios crudos.

Por que importa: el metodo de ratios del v1 trata igual un gol a un rival
flojo que a uno fuerte. Mexico juega muchos rivales debiles (CONCACAF) -> su
ataque queda inflado; Sudafrica juega rivales africanos medios -> su defensa
queda mal calibrada. El ajuste iterativo reparte el credito segun contra quien
se jugo: alpha_i (ataque) y beta_j (defensa) se resuelven simultaneamente.

Mantiene: decay temporal, peso menor a amistosos, localia (gamma), correccion
Dixon-Coles para marcadores bajos y la regla de EV = 2*P(m) + P(direccion).

Uso:
    python predict_match_v2.py "Mexico" "South Africa"
    python predict_match_v2.py "Argentina" "Brazil" --neutral
    python predict_match_v2.py "Mexico" "South Africa" --as-of 2010-06-11
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

import csv_io
import scoring

DATA = Path("data/results.csv")

HALF_LIFE_YEARS = 3.0
FRIENDLY_WEIGHT = 0.5
MAX_GOALS = 8
DC_RHO = -0.10
N_ITER = 60


def apply_manual_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Completa marcadores que martj42 todavia no publico, desde
    data/manual_results.csv (mismo esquema: date,home_team,away_team,
    home_score,away_score). Solo rellena los que estan vacios; nunca pisa un
    resultado oficial. Sirve para cargar a mano un partido ya jugado mientras
    el dataset publico tarda en actualizarse."""
    man = csv_io.read(DATA.parent / "manual_results.csv", csv_io.MANUAL_RESULTS,
                      missing_ok=True)
    man = man.dropna(subset=["date", "home_team", "away_team",
                             "home_score", "away_score"])
    if man.empty:
        return df
    key = ["date", "home_team", "away_team"]
    df = df.merge(man[key + ["home_score", "away_score"]], on=key,
                  how="left", suffixes=("", "_m"))
    for c in ("home_score", "away_score"):
        df[c] = df[c].where(df[c].notna(), df[f"{c}_m"])
    return df.drop(columns=["home_score_m", "away_score_m"])


def load_results(as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    df = csv_io.read(DATA, csv_io.RESULTS)
    df = apply_manual_overrides(df)
    df = df.dropna(subset=["home_score", "away_score", "date"])
    # Una sede sin dato se cuenta como NO neutral, que es lo que hacia el parseo
    # viejo (`str(NaN).upper() != "TRUE"`). Se deja explicito para que no
    # dependa de un accidente del casteo.
    df["neutral"] = df["neutral"].fillna(False)
    # A partir de aca manda numpy: fit_iterative y compute_elo hacen .to_numpy()
    # y los dtypes nullable devuelven masked arrays.
    df = csv_io.to_plain(df, csv_io.RESULTS)
    df = df.sort_values("date").reset_index(drop=True)
    if as_of is not None:
        df = df[df["date"] < as_of].reset_index(drop=True)
    return df


def fit_iterative(df: pd.DataFrame, as_of: pd.Timestamp, n_iter: int = N_ITER) -> dict:
    """Ataque (alpha) y defensa (beta) por punto fijo, ajustando por rival.

    Modelo: lambda_local = mu * alpha_local * beta_visita * gamma
            lambda_visita = mu * alpha_visita * beta_local
    Restriccion de identificabilidad: media ponderada de alpha y beta = 1.
    beta > 1 => recibe mas que la media (mala defensa).
    """
    age = (as_of - df["date"]).dt.days.to_numpy() / 365.25
    w = 0.5 ** (age / HALF_LIFE_YEARS)
    friendly = df["tournament"].str.contains("Friendly", case=False, na=False).to_numpy()
    w = w * np.where(friendly, FRIENDLY_WEIGHT, 1.0)

    teams = pd.Index(sorted(set(df["home_team"]) | set(df["away_team"])))
    tidx = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    hi = df["home_team"].map(tidx).to_numpy()
    ai = df["away_team"].map(tidx).to_numpy()
    hs = df["home_score"].to_numpy().astype(float)
    as_ = df["away_score"].to_numpy().astype(float)
    nn = (~df["neutral"].to_numpy())                       # True si NO neutral

    # numeradores (constantes): goles a favor / en contra ponderados por equipo
    num_att = np.bincount(hi, w * hs, T) + np.bincount(ai, w * as_, T)
    num_def = np.bincount(hi, w * as_, T) + np.bincount(ai, w * hs, T)
    wsum = np.bincount(hi, w, T) + np.bincount(ai, w, T)
    ngames = np.bincount(hi, minlength=T) + np.bincount(ai, minlength=T)
    active = wsum > (0.02 * wsum.max())                    # equipos con juego real
    eps = 1e-9

    alpha = np.ones(T)
    beta = np.ones(T)
    gamma = 1.35
    mu = (w * (hs + as_)).sum() / (2.0 * w.sum())

    for _ in range(n_iter):
        ghome = np.where(nn, gamma, 1.0)
        # ataque: esperado de goles a favor = mu * beta_rival * (gamma si local-nn)
        denom_att = (np.bincount(hi, w * mu * beta[ai] * ghome, T)
                     + np.bincount(ai, w * mu * beta[hi], T))
        alpha = num_att / np.maximum(denom_att, eps)
        alpha /= np.average(alpha[active], weights=wsum[active])
        # defensa: esperado de goles en contra = mu * alpha_rival * (gamma si rival local-nn)
        denom_def = (np.bincount(hi, w * mu * alpha[ai], T)
                     + np.bincount(ai, w * mu * alpha[hi] * ghome, T))
        beta = num_def / np.maximum(denom_def, eps)
        beta /= np.average(beta[active], weights=wsum[active])
        # localia (solo partidos no neutrales)
        m = nn
        gamma = (w[m] * hs[m]).sum() / max(
            (w[m] * mu * alpha[hi[m]] * beta[ai[m]]).sum(), eps)
        # nivel global de goles
        exp_no_mu = (w * (alpha[hi] * beta[ai] * ghome + alpha[ai] * beta[hi])).sum()
        mu = (w * (hs + as_)).sum() / max(exp_no_mu, eps)

    return dict(teams=teams, tidx=tidx, alpha=alpha, beta=beta, gamma=gamma,
                mu=mu, ngames=ngames)


def dc_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
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
    th, ta = p["tidx"][home], p["tidx"][away]
    g = 1.0 if neutral else p["gamma"]
    lh = p["mu"] * p["alpha"][th] * p["beta"][ta] * g
    la = p["mu"] * p["alpha"][ta] * p["beta"][th]
    M = score_matrix(lh, la)
    ev, p_home, p_draw, p_away = scoring.ev_matrix(M)
    bi, bj = scoring.best_ev_score(M)
    return dict(lh=lh, la=la, M=M, p_home=p_home, p_draw=p_draw, p_away=p_away,
                ev=ev, best=(bi, bj), best_ev=float(ev[bi, bj]))


# re-export por compatibilidad: v3 y los CLI importan `modal` desde aca
modal = scoring.modal


def main() -> None:
    ap = argparse.ArgumentParser(description="Marcador a cargar (v2, ajuste por rival)")
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--neutral", action="store_true")
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of) if args.as_of else None
    df = load_results(as_of=as_of)
    if as_of is None:
        as_of = df["date"].max() + pd.Timedelta(days=1)
    p = fit_iterative(df, as_of)

    for t in (args.home, args.away):
        if t not in p["tidx"]:
            near = [x for x in p["teams"] if t.lower() in x.lower() or x.lower() in t.lower()]
            print(f"ERROR: '{t}' no esta. Quisiste decir: {near[:6]}")
            raise SystemExit(1)

    r = predict(args.home, args.away, args.neutral, p)
    th, ta = p["tidx"][args.home], p["tidx"][args.away]
    venue = "cancha neutral" if args.neutral else f"{args.home} de local"
    bi, bj = r["best"]

    print(f"\n=== [v2] {args.home} vs {args.away}  ({venue}) ===")
    print(f"datos hasta: {as_of.date()}  |  ajuste por fuerza de rival, "
          f"localia gamma={p['gamma']:.2f}, mu={p['mu']:.2f}\n")
    print(f"{args.home}: ataque {p['alpha'][th]:.2f}  defensa {p['beta'][th]:.2f}  "
          f"({p['ngames'][th]} PJ)")
    print(f"{args.away}: ataque {p['alpha'][ta]:.2f}  defensa {p['beta'][ta]:.2f}  "
          f"({p['ngames'][ta]} PJ)")
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
