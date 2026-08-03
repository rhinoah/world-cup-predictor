#!/usr/bin/env python3
"""
run.py
======
El pipeline del proyecto, escrito una sola vez.

Antes vivia en tres lugares que se desincronizaban solos: la secuencia de la
tarea programada (`update_dataset.bat`), la lista de comandos del README y lo
que uno se acordaba. Aca esta el orden real, con lo que produce cada paso.

    python run.py setup     # clon recien bajado: dataset, fixture, banderas, icono
    python run.py update    # el ciclo diario: dataset -> liquidar -> jornada -> detalle
    python run.py analisis  # backtests (segundos) + real-vs-esperado (varios minutos)
    python run.py --list    # muestra los pasos sin correr nada

Cada paso corre con el MISMO interprete que ejecuto este archivo (`sys.executable`)
y como modulo (`-m scripts.X`), asi la raiz del repo queda en sys.path y los
scripts pueden importar `prode...` sin importar desde donde se llame a run.py.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

BASE = Path(__file__).resolve().parent


class Paso(NamedTuple):
    script: str
    que_hace: str
    produce: str
    stdout_a: str | None = None   # si el script escribe el resultado por pantalla
    opcional: bool = False        # si falla, se sigue con los que siguen


# --------------------------------------------------------------------------
# Los tres flujos
# --------------------------------------------------------------------------
SETUP = [
    Paso("build_features", "baja el dataset de martj42 y arma las features",
         "data/*.csv + output/team_matches.csv, team_features.csv"),
    Paso("build_horarios", "cruza el fixture con los horarios en hora argentina",
         "fixture_horarios.csv"),
    Paso("parse_thirds", "baja la tabla FIFA de mejores terceros (495 combinaciones)",
         "thirds_table.json", opcional=True),
    Paso("build_flags", "baja las banderas de las 48 selecciones",
         "flags/*.png", opcional=True),
    Paso("make_icon", "dibuja el icono de la app",
         "prode.ico + prode.png", opcional=True),
]

UPDATE = [
    Paso("build_features", "actualiza el dataset con los partidos nuevos",
         "data/*.csv + output/*.csv"),
    Paso("liquidar", "puntua los pronosticos de los partidos ya jugados",
         "pronosticos.csv (columnas actual_* y points)"),
    Paso("predict_matchday", "predice la proxima jornada pendiente",
         "predicciones_jornada.txt", stdout_a="predicciones_jornada.txt"),
    Paso("build_pronosticos", "recalcula los sugeridos y su explicacion para la app",
         "pronosticos_detalle.json"),
]

ANALISIS = [
    Paso("backtest", "valida el modelo de fuerzas sobre 9 torneos (2016-2024)",
         "por pantalla"),
    Paso("backtest_elo", "valida el blend con Elo",
         "por pantalla"),
    # El unico paso lento del proyecto: re-ajusta el modelo una vez por cada
    # fecha del torneo, asi que son ~100 ajustes. Los backtests tardan segundos.
    Paso("backfill_ev", "recalcula el EV as-of de cada pronostico (varios minutos)",
         "pronosticos.csv (columna ev_v3) + docs/ev_vs_real.png"),
]

FLUJOS = {"setup": SETUP, "update": UPDATE, "analisis": ANALISIS}


# --------------------------------------------------------------------------
def listar(nombre: str, pasos: list[Paso]) -> None:
    print(f"\n{nombre}:")
    for i, p in enumerate(pasos, 1):
        marca = "  (opcional)" if p.opcional else ""
        print(f"  {i}. {p.script + '.py':<22} {p.que_hace}{marca}")
        print(f"     -> {p.produce}")


def correr(pasos: list[Paso]) -> int:
    fallidos = []
    for i, p in enumerate(pasos, 1):
        print(f"\n[{i}/{len(pasos)}] {p.script} — {p.que_hace}", flush=True)
        t0 = time.perf_counter()
        salida = open(BASE / p.stdout_a, "w", encoding="utf-8") if p.stdout_a else None
        try:
            # -m y no la ruta del archivo: asi sys.path[0] es la raiz del repo
            # y los scripts pueden hacer `from prode... import ...`.
            r = subprocess.run([sys.executable, "-m", f"scripts.{p.script}"],
                               cwd=str(BASE), stdout=salida)
        finally:
            if salida:
                salida.close()
        seg = time.perf_counter() - t0
        if r.returncode == 0:
            print(f"      ok ({seg:.1f} s) -> {p.produce}", flush=True)
            continue
        fallidos.append(p.script)
        print(f"      FALLO (codigo {r.returncode}, {seg:.1f} s)", flush=True)
        if not p.opcional:
            print(f"\nSe corta acá: los pasos siguientes dependen de {p.script}.")
            return 1
        print("      es opcional, se sigue.", flush=True)

    if fallidos:
        print(f"\nListo, pero fallaron pasos opcionales: {', '.join(fallidos)}")
        return 0
    print("\nListo: todos los pasos terminaron bien.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Corre el pipeline del prode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="setup: clon nuevo  |  update: ciclo diario  |  analisis: backtests")
    ap.add_argument("flujo", nargs="?", choices=sorted(FLUJOS),
                    help="que secuencia correr")
    ap.add_argument("--list", action="store_true", help="mostrar los pasos sin correr nada")
    args = ap.parse_args()

    if args.list or not args.flujo:
        for nombre in ("setup", "update", "analisis"):
            listar(nombre, FLUJOS[nombre])
        if not args.flujo:
            print("\nElegí uno:  python run.py setup | update | analisis")
        return 0
    return correr(FLUJOS[args.flujo])


if __name__ == "__main__":
    sys.exit(main())
