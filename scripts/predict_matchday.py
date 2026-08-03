#!/usr/bin/env python3
"""
predict_matchday.py
===================
Predice el marcador a cargar para TODOS los partidos de una fecha, leyendo el
fixture (que ya viene en data/results.csv con los scores vacios) y usando el
modelo de produccion v3. Marca la localia sola: solo USA/Mexico/Canada juegan
de local en su Mundial; el resto es cancha neutral.

Uso:
    python -m scripts.predict_matchday                 # proxima fecha con partidos sin jugar
    python -m scripts.predict_matchday --date 2026-06-12
"""
from __future__ import annotations

import argparse

import pandas as pd

from prode import paths
from prode.data import csv_io
from prode.model.predict_match_v2 import fit_iterative, load_results, apply_manual_overrides
from prode.model.elo import compute_elo
from prode.model.predict_match_v3 import predict

from prode.data.app_data import HOSTS
RAW = paths.RESULTS_CSV


def load_fixture() -> pd.DataFrame:
    df = csv_io.read(RAW, csv_io.RESULTS)
    # Un override ya jugado deja de ser "pendiente". La sede no se toca aca: la
    # decide `h not in HOSTS` mas abajo, porque en el Mundial solo los anfitriones
    # juegan de local.
    return apply_manual_overrides(df)


def main():
    ap = argparse.ArgumentParser(description="Predice toda una jornada del Mundial")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: proxima fecha pendiente)")
    args = ap.parse_args()

    fixture = load_fixture()
    pending = fixture[fixture["home_score"].isna() & fixture["away_score"].isna()]
    if args.date:
        day = pd.Timestamp(args.date)
    else:
        future = pending[pending["date"] >= pd.Timestamp.now().normalize()]
        if future.empty:
            print("No hay partidos pendientes en el fixture.")
            return
        day = future["date"].min()

    games = pending[pending["date"] == day].sort_values("home_team")
    if games.empty:
        print(f"No hay partidos pendientes el {day.date()}.")
        return

    # entrenar UNA sola vez con todo lo jugado hasta esa fecha (sin leakage)
    train = load_results(as_of=day)
    _, elo = compute_elo(train)
    p = fit_iterative(train, day)

    print(f"\n===== Jornada {day.date()}  ({len(games)} partidos) =====")
    print(f"{'partido':<36}{'cargar':>7}   {'L / E / V (%)':<14}")
    print("-" * 62)
    for _, m in games.iterrows():
        h, a = m["home_team"], m["away_team"]
        if h not in p["tidx"] or a not in p["tidx"]:
            print(f"{h + ' vs ' + a:<36}{'?':>7}   (falta data de algun equipo)")
            continue
        neutral = h not in HOSTS
        r = predict(h, a, neutral, p, elo)
        bi, bj = r["best"]
        loc = "" if neutral else "  (local)"
        print(f"{h + ' vs ' + a:<36}{f'{bi}-{bj}':>7}   "
              f"{r['p_home']*100:3.0f}/{r['p_draw']*100:2.0f}/{r['p_away']*100:2.0f}{loc}")
    print()


if __name__ == "__main__":
    main()
