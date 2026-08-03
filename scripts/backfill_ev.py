#!/usr/bin/env python3
"""
backfill_ev.py
==============
Repara la columna ev_v3 de pronosticos.csv: recalcula, para CADA pronostico
cargado, el puntaje esperado (EV) segun el modelo v3 ajustado SOLO con datos
anteriores a ese partido (as_of = fecha del partido -> sin data leakage).

EV(marcador) = 2*P(marcador exacto) + P(direccion 1X2), en unidades del prode
3/1/0 (un exacto vale 3 = 1 punto de direccion + 2 extra). Es la misma regla
con la que el modelo elige que marcador sugerir.

Con la columna reparada, el analisis "real vs esperado" (que tambien imprime
liquidar.py) pasa a tener sentido: compara los puntos que SACASTE contra los
que el propio modelo esperaba sacar. Si matplotlib esta instalado, guarda
docs/ev_vs_real.png con las curvas acumuladas.

Uso:
    python -m scripts.backfill_ev
"""
from __future__ import annotations

import pandas as pd

from prode import paths
from prode.data import csv_io
from prode.model.predict_match_v2 import load_results, fit_iterative
from prode.model.elo import compute_elo
from prode.model.predict_match_v3 import predict

# Antes esto hacia sys.path.insert + os.chdir(BASE) para que anduvieran las rutas
# relativas de los otros modulos. Con las rutas absolutas de paths.py no hace falta.
BASE = paths.ROOT

GROUPS_END = pd.Timestamp("2026-06-27")   # ultimo dia de la fase de grupos


def main():
    pron = csv_io.read(BASE / "pronosticos.csv", csv_io.PRONOSTICOS)
    if pron["date"].isna().any():
        bad = pron[pron["date"].isna()][["home_team", "away_team"]].values.tolist()
        raise SystemExit(f"Hay filas sin fecha; completalas antes de correr: {bad}")

    neutral = pron["neutral"].fillna(False)
    rows = []
    dates = sorted(pron["date"].unique())
    print(f"backfill de EV: {len(pron)} pronosticos en {len(dates)} fechas "
          f"(re-ajusta el modelo por fecha, puede tardar varios minutos)\n", flush=True)

    for n, d in enumerate(dates, 1):
        as_of = pd.Timestamp(d)
        df = load_results(as_of=as_of)          # SOLO partidos anteriores a la fecha
        _, elo = compute_elo(df)
        p = fit_iterative(df, as_of)
        day = pron[pron["date"] == d]
        for i, row in day.iterrows():
            ht, at = row["home_team"], row["away_team"]
            if ht not in p["tidx"] or at not in p["tidx"]:
                print(f"  !! {ht} vs {at}: equipo fuera del modelo, salteo", flush=True)
                continue
            r = predict(ht, at, bool(neutral.loc[i]), p, elo)
            ph, pa = int(row["pred_home"]), int(row["pred_away"])
            k = r["ev"].shape[0] - 1
            ev_loaded = float(r["ev"][ph, pa]) if ph <= k and pa <= k else 0.0
            pron.at[i, "ev_v3"] = round(ev_loaded, 3)
            rows.append({"date": as_of, "home": ht, "away": at,
                         "pred": (ph, pa), "best": tuple(r["best"]),
                         "ev": ev_loaded, "ev_opt": float(r["best_ev"]),
                         "points": row["points"] if pd.notna(row["points"]) else None,
                         "phase": "elim" if as_of > GROUPS_END else "grupos"})
        print(f"[{n:>2}/{len(dates)}] {as_of.date()}  ok ({len(day)} partidos)", flush=True)

    # persistir ev_v3 (el esquema se encarga de no degradar el formato)
    csv_io.write(pron, BASE / "pronosticos.csv", csv_io.PRONOSTICOS)
    print(f"\npronosticos.csv actualizado ({len(rows)} filas con ev_v3)", flush=True)

    # ---------------- reporte real vs esperado ----------------
    res = pd.DataFrame(rows)
    done = res[res["points"].notna()].copy()
    done["points"] = done["points"].astype(int)
    tot, exp = int(done["points"].sum()), float(done["ev"].sum())
    print("\n=== REAL vs ESPERADO (modelo v3, sin leakage, prode 3/1/0) ===")
    print(f"partidos: {len(done)}   puntos reales: {tot}   esperados (suma EV): {exp:.1f}")
    print(f"por partido:  real {tot/len(done):.3f}   esperado {exp/len(done):.3f}")
    for phase in ("grupos", "elim"):
        s = done[done["phase"] == phase]
        if len(s):
            print(f"  {phase:>7}: real {int(s['points'].sum()):>3}  "
                  f"esperado {s['ev'].sum():6.1f}   ({len(s)} partidos)")

    followed = done[[p == b for p, b in zip(done["pred"], done["best"])]]
    dev = done[[p != b for p, b in zip(done["pred"], done["best"])]]
    print(f"\nsugerido optimo del modelo seguido en {len(followed)}/{len(done)} partidos")
    if len(dev):
        print(f"  en los {len(dev)} que difieren: real {int(dev['points'].sum())} pts  "
              f"vs EV de lo cargado {dev['ev'].sum():.1f}  vs EV del optimo {dev['ev_opt'].sum():.1f}")

    gap = done.assign(g=done["points"] - done["ev"]).sort_values("g")
    print("\npeores 5 (real - esperado):")
    for _, r in gap.head(5).iterrows():
        print(f"  {r['date'].date()}  {r['home']} {r['pred'][0]}-{r['pred'][1]} {r['away']}"
              f"   -> {r['points']} pts vs {r['ev']:.2f} esperado")
    print("mejores 5:")
    for _, r in gap.tail(5).iloc[::-1].iterrows():
        print(f"  {r['date'].date()}  {r['home']} {r['pred'][0]}-{r['pred'][1]} {r['away']}"
              f"   -> {r['points']} pts vs {r['ev']:.2f} esperado")

    # ---------------- grafico ----------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        d2 = done.sort_values("date").reset_index(drop=True)
        (BASE / "docs").mkdir(exist_ok=True)
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(d2.index + 1, d2["points"].cumsum(), lw=2,
                label=f"puntos reales ({tot})")
        ax.plot(d2.index + 1, d2["ev"].cumsum(), lw=2, ls="--",
                label=f"esperado por el modelo ({exp:.1f})")
        ax.set_xlabel("partido")
        ax.set_ylabel("puntos acumulados (3 exacto / 1 direccion)")
        ax.set_title("Mundial 2026 — puntaje real vs esperado (EV del modelo v3)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(BASE / "docs" / "ev_vs_real.png", dpi=150)
        print("\ngrafico -> docs/ev_vs_real.png")
    except ImportError:
        print("\n(matplotlib no instalado: salteo el grafico)")


if __name__ == "__main__":
    main()
