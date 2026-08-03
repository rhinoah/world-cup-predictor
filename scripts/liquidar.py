#!/usr/bin/env python3
"""
liquidar.py
===========
Cierra el circulo del registro: toma pronosticos.csv, busca el resultado real
de cada partido en el dataset (data/results.csv, que se actualiza solo con la
tarea diaria + overrides manuales), completa actual_home/actual_away y calcula
los puntos del prode (3/1/0). Reescribe el CSV solo si liquido algo nuevo, y
muestra el acumulado y como venimos contra el puntaje esperado (EV) del modelo.

Uso:
    python -m scripts.liquidar
"""
from __future__ import annotations

import pandas as pd

from prode import paths
from prode.data import app_data
from prode.data import csv_io
from prode.data import results
from prode.model import scoring

PRON = paths.PRONOSTICOS_CSV
RESULTS = paths.RESULTS_CSV


def prode_points(ph, pa, rh, ra) -> int:
    """Puntaje del prode: 3 marcador exacto, 1 acertar direccion 1X2, 0 si no."""
    return scoring.points((ph, pa), (rh, ra))


def main():
    # missing_ok: en un clon recien bajado todavia no hay pronosticos cargados, y
    # este script lo corre la tarea diaria. Sin esto fallaba todos los dias hasta
    # que el usuario cargara el primero a mano.
    pron = csv_io.read(PRON, csv_io.PRONOSTICOS, missing_ok=True)
    if pron.empty:
        print("Todavia no hay pronosticos cargados: nada que liquidar.")
        return

    # Cruzar por EQUIPOS dentro del Mundial 2026, no por fecha exacta: la fecha del pronostico de
    # eliminacion a veces difiere 1 dia de la del dataset (zona horaria) y dejaba partidos jugados
    # sin liquidar. Cada cruce local-visitante es unico dentro del torneo, asi que alcanza.
    res = results.load(RESULTS)
    res_idx = results.by_teams(app_data.wc_matches(res))

    newly, fixed = 0, 0
    for i, row in pron.iterrows():
        real = results.score_of(res_idx, row["home_team"], row["away_team"])
        if real is None:
            continue                                   # no jugado, o no esta en el dataset
        rh, ra = real
        had = pd.notna(row.get("actual_home")) and pd.notna(row.get("actual_away"))
        if had and int(row["actual_home"]) == rh and int(row["actual_away"]) == ra:
            continue                                   # ya liquidado y el resultado oficial coincide
        pts = prode_points(int(row["pred_home"]), int(row["pred_away"]), rh, ra)
        pron.at[i, "actual_home"] = rh
        pron.at[i, "actual_away"] = ra
        pron.at[i, "points"] = pts
        if had:
            fixed += 1                                 # ya estaba liquidado pero el resultado cambio -> se corrige
        else:
            newly += 1

    if newly or fixed:
        csv_io.write(pron, PRON, csv_io.PRONOSTICOS)

    done = pron[pron["points"].notna()].copy()
    pend = len(pron) - len(done)
    print(f"\nLiquidados ahora: {newly}   |   corregidos: {fixed}   |   total liquidados: {len(done)}   |   pendientes: {pend}")
    if len(done):
        done["points"] = done["points"].astype(int)
        total = int(done["points"].sum())
        exact = int((done["points"] == 3).sum())
        direc = int((done["points"] == 1).sum())
        fail = int((done["points"] == 0).sum())
        ev_exp = pd.to_numeric(done["ev_v3"], errors="coerce").sum()
        print(f"\nPUNTOS: {total}   ({len(done)} partidos = {total/len(done):.2f}/partido)")
        print(f"  exactos +3: {exact}    resultado +1: {direc}    fallados 0: {fail}")
        delta = "ARRIBA" if total >= ev_exp else "abajo"
        print(f"  esperado por el modelo (suma EV): {ev_exp:.2f}  ->  vas {delta} de lo esperado")
        print("\n  detalle:")
        for _, r in done.iterrows():
            d = f"{r['date']:%Y-%m-%d}" if pd.notna(r["date"]) else "(sin fecha)"
            print(f"   {d}  "
                  f"{r['home_team']} {int(r['pred_home'])}-{int(r['pred_away'])} {r['away_team']}"
                  f"   | real {int(r['actual_home'])}-{int(r['actual_away'])}  ->  {int(r['points'])} pts")
    print()


if __name__ == "__main__":
    main()
