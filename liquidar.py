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
    python liquidar.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import app_data
import scoring
from predict_match_v2 import apply_manual_overrides

PRON = "pronosticos.csv"
RESULTS = "data/results.csv"


def prode_points(ph, pa, rh, ra) -> int:
    """Puntaje del prode: 3 marcador exacto, 1 acertar direccion 1X2, 0 si no."""
    return scoring.points((ph, pa), (rh, ra))


def main():
    pron = pd.read_csv(PRON)
    pron["date"] = pd.to_datetime(pron["date"], errors="coerce")

    res = pd.read_csv(RESULTS)
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    res = apply_manual_overrides(res)
    # Cruzar por EQUIPOS dentro del Mundial 2026, no por fecha exacta: la fecha del pronostico de
    # eliminacion a veces difiere 1 dia de la del dataset (zona horaria) y dejaba partidos jugados
    # sin liquidar. Cada cruce local-visitante es unico dentro del torneo, asi que alcanza.
    wc = app_data.wc_matches(res)
    res_idx = wc.set_index(["home_team", "away_team"])[["home_score", "away_score"]].sort_index()

    newly, fixed = 0, 0
    for i, row in pron.iterrows():
        key = (row["home_team"], row["away_team"])
        if key not in res_idx.index:
            continue                                   # no esta en el dataset del Mundial
        rec = res_idx.loc[key]
        if isinstance(rec, pd.DataFrame):
            rec = rec.iloc[0]
        rh, ra = rec["home_score"], rec["away_score"]
        if pd.isna(rh) or pd.isna(ra):
            continue                                   # todavia no se jugo
        rh, ra = int(rh), int(ra)
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
        out = pron.copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        for c in ("actual_home", "actual_away", "points"):
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")
        out.to_csv(PRON, index=False)

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
