#!/usr/bin/env python3
"""
build_pronosticos.py
====================
Corre el modelo v3 sobre los partidos PENDIENTES de la fase de grupos y guarda
pronosticos_detalle.json con el marcador sugerido y el "por que" de cada uno:
probabilidades 1X2, goles esperados (lambda), Elo y los marcadores mas probables.
La app lo lee para mostrar el recuadro de cada jornada con su explicacion.
"""
from __future__ import annotations

import json
import sys
import traceback

import pandas as pd

import csv_io
from predict_match_v2 import load_results, fit_iterative
from elo import compute_elo
from predict_match_v3 import predict

from app_data import HOSTS, TOURNAMENT, WC_START


def top_scores(M, n=5):
    k = M.shape[0] - 1
    flat = sorted(((M[i, j], i, j) for i in range(k + 1) for j in range(k + 1)), reverse=True)
    return [[i, j, round(p * 100, 1)] for p, i, j in flat[:n]]


def main():
    df = load_results()
    as_of = df["date"].max() + pd.Timedelta(days=1)
    _, elo = compute_elo(df)
    p = fit_iterative(df, as_of)

    wc = df[(df["tournament"] == TOURNAMENT) & (df["date"] >= WC_START)]
    played = set(zip(wc["home_team"], wc["away_team"]))

    hor = csv_io.read("fixture_horarios.csv", csv_io.HORARIOS)

    out = []
    for _, h in hor.sort_values("kickoff_arg").iterrows():
        ht, at = h["home_team"], h["away_team"]
        if (ht, at) in played or ht not in p["tidx"] or at not in p["tidx"]:
            continue
        r = predict(ht, at, ht not in HOSTS, p, elo)
        out.append({
            "home": ht, "away": at,
            "kickoff_arg": h["kickoff_arg"].strftime(csv_io.TIMESTAMP_FMT),
            "host": ht in HOSTS,
            "best": list(r["best"]), "ev": round(r["best_ev"], 3),
            "lh": round(r["lh"], 2), "la": round(r["la"], 2),
            "elo_home": round(r["eh"]), "elo_away": round(r["ea"]),
            "p_home": round(r["p_home"] * 100, 1),
            "p_draw": round(r["p_draw"] * 100, 1),
            "p_away": round(r["p_away"] * 100, 1),
            "top": top_scores(r["M"]),
        })

    # --- eliminacion: TODOS los cruces con ambos equipos definidos (16avos + octavos en
    #     adelante, a medida que se resuelven los ganadores de cada ronda) ---
    n_ko = 0
    try:
        import bracket, app_data
        for m in app_data.knockout_fixture():
            ht, at = m.get("home"), m.get("away")
            if not ht or not at or ht not in p["tidx"] or at not in p["tidx"]:
                continue
            if (ht, at) in played or (at, ht) in played:
                continue
            r = predict(ht, at, True, p, elo)        # eliminacion = cancha neutral
            out.append({
                "home": ht, "away": at,
                "kickoff_arg": bracket.MATCH_DT.get(m["match"], ""),
                "host": False, "stage": "ko", "match": m["match"],
                "best": list(r["best"]), "ev": round(r["best_ev"], 3),
                "lh": round(r["lh"], 2), "la": round(r["la"], 2),
                "elo_home": round(r["eh"]), "elo_away": round(r["ea"]),
                "p_home": round(r["p_home"] * 100, 1),
                "p_draw": round(r["p_draw"] * 100, 1),
                "p_away": round(r["p_away"] * 100, 1),
                "top": top_scores(r["M"]),
            })
            n_ko += 1
    except Exception:
        # Se sigue igual: los pronosticos de grupos ya calculados valen aunque el
        # bracket falle. Pero va el traceback entero y no solo el mensaje: esto
        # corre desatendido en la tarea programada, y "eliminacion: 'Spain'" no
        # alcanza para saber que lo rompio cuando se lee el log dias despues.
        print("eliminacion (sugeridos): FALLO, se sigue con los grupos",
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    with open("pronosticos_detalle.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"pronosticos_detalle.json -> {len(out)} partidos pendientes con explicacion ({n_ko} de eliminacion)")
    for o in out[:4]:
        print(f"  {o['kickoff_arg']}  {o['home']} {o['best'][0]}-{o['best'][1]} {o['away']}"
              f"   L/E/V {o['p_home']:.0f}/{o['p_draw']:.0f}/{o['p_away']:.0f}"
              f"   top {o['top'][0][0]}-{o['top'][0][1]} {o['top'][0][2]:.0f}%")


if __name__ == "__main__":
    main()
