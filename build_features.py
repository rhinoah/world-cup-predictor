#!/usr/bin/env python3
"""
build_features.py
=================
Descarga el dataset de partidos internacionales de martj42 y calcula
features base por seleccion para alimentar un modelo de prediccion
(prode Mundial 2026).

Fuente de datos:
    https://github.com/martj42/international_results  (dominio publico-ish, ver repo)

Archivos que usa:
    results.csv       -> todos los partidos de selecciones
    goalscorers.csv   -> gol por gol (no se usa aca, pero se descarga)
    shootouts.csv     -> definiciones por penales
    former_names.csv  -> mapeo de nombres historicos de selecciones

Uso:
    python build_features.py                  # baja datos + genera features
    python build_features.py --since 2018     # ventana de relevancia distinta
    python build_features.py --no-download     # usa el cache local en ./data

Salida:
    data/*.csv                 -> CSV crudos descargados
    output/team_features.csv   -> una fila por seleccion con sus features
    output/team_matches.csv    -> tabla larga (una fila por equipo por partido)

Dependencias: pandas  (pip install pandas)
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

import csv_io

BASE_URL = "https://raw.githubusercontent.com/martj42/international_results/master"
FILES = ["results.csv", "goalscorers.csv", "shootouts.csv", "former_names.csv"]

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")

# Selecciones a destacar en el reporte final. Editar segun los clasificados
# al Mundial 2026. Los tres anfitriones ya estan dentro; el resto se va
# definiendo con las eliminatorias. Dejar vacia [] para incluir a todas.
FOCUS_TEAMS: list[str] = [
    "United States", "Mexico", "Canada",  # anfitriones (auto-clasificados)
    "Argentina", "Brazil", "France", "England", "Spain",  # ejemplos, editar
]


def download_data(force: bool = True) -> None:
    """Descarga los CSV de martj42 a ./data (con cache simple)."""
    DATA_DIR.mkdir(exist_ok=True)
    for fname in FILES:
        dest = DATA_DIR / fname
        if dest.exists() and not force:
            print(f"  cache: {fname} (ya existe, no se baja)")
            continue
        url = f"{BASE_URL}/{fname}"
        print(f"  bajando: {url}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR bajando {fname}: {exc}", file=sys.stderr)
            sys.exit(1)


def load_results() -> pd.DataFrame:
    """Carga results.csv y lo normaliza (fechas, neutral, scores)."""
    df = csv_io.read(DATA_DIR / "results.csv", csv_io.RESULTS)
    # tirar partidos sin marcador (suspendidos, futuros, etc.)
    df = df.dropna(subset=["home_score", "away_score", "date"])
    df["neutral"] = df["neutral"].fillna(False)     # sin dato = no neutral
    df = csv_io.to_plain(df, csv_io.RESULTS)        # numpy plano para el resto
    return df.sort_values("date").reset_index(drop=True)


def build_team_match_table(results: pd.DataFrame) -> pd.DataFrame:
    """Explota cada partido en dos filas (perspectiva de cada equipo)."""
    cols = ["date", "tournament", "neutral"]

    home = results[cols + ["home_team", "away_team", "home_score", "away_score"]].copy()
    home.columns = cols + ["team", "opponent", "gf", "ga"]
    home["venue"] = "home"

    away = results[cols + ["away_team", "home_team", "away_score", "home_score"]].copy()
    away.columns = cols + ["team", "opponent", "gf", "ga"]
    away["venue"] = "away"

    long = pd.concat([home, away], ignore_index=True)
    long.loc[long["neutral"], "venue"] = "neutral"

    long["gd"] = long["gf"] - long["ga"]
    long["result"] = pd.cut(
        long["gd"], bins=[-99, -1, 0, 99], labels=["L", "D", "W"]
    ).astype(str)
    long["points"] = long["result"].map({"W": 3, "D": 1, "L": 0})
    long["is_win"] = (long["result"] == "W").astype(int)
    long["is_competitive"] = ~long["tournament"].str.contains(
        "Friendly", case=False, na=False
    )
    return long.sort_values("date").reset_index(drop=True)


def recent_form(
    matches: pd.DataFrame, team: str, as_of: pd.Timestamp, n: int = 10
) -> dict:
    """Forma de un equipo en sus ultimos N partidos ANTES de as_of.

    Pensado para no filtrar informacion del futuro (sin data leakage):
    siempre se calcula con partidos estrictamente anteriores a as_of.
    """
    hist = matches[(matches["team"] == team) & (matches["date"] < as_of)]
    hist = hist.tail(n)
    if hist.empty:
        return {"form_matches": 0}
    return {
        "form_matches": len(hist),
        "form_ppg": round(hist["points"].mean(), 3),       # puntos por partido
        "form_gf_avg": round(hist["gf"].mean(), 3),
        "form_ga_avg": round(hist["ga"].mean(), 3),
        "form_win_rate": round(hist["is_win"].mean(), 3),
    }


def team_summary(matches: pd.DataFrame, since: int) -> pd.DataFrame:
    """Resumen agregado por seleccion en la ventana >= since (anio)."""
    window = matches[matches["date"].dt.year >= since].copy()
    grouped = window.groupby("team")

    summary = grouped.agg(
        matches=("result", "size"),
        wins=("is_win", "sum"),
        win_rate=("is_win", "mean"),
        ppg=("points", "mean"),
        gf_avg=("gf", "mean"),
        ga_avg=("ga", "mean"),
    ).round(3)

    # forma reciente "al dia de hoy" (ultimo partido registrado del dataset)
    as_of = matches["date"].max() + pd.Timedelta(days=1)
    form_rows = {t: recent_form(matches, t, as_of, n=10) for t in summary.index}
    form_df = pd.DataFrame(form_rows).T

    out = summary.join(form_df)
    return out.sort_values("ppg", ascending=False)


def head_to_head(matches: pd.DataFrame, team_a: str, team_b: str) -> dict:
    """Historial directo entre dos selecciones (todo el dataset)."""
    h2h = matches[(matches["team"] == team_a) & (matches["opponent"] == team_b)]
    if h2h.empty:
        return {"matches": 0}
    return {
        "matches": len(h2h),
        f"{team_a}_wins": int((h2h["result"] == "W").sum()),
        "draws": int((h2h["result"] == "D").sum()),
        f"{team_b}_wins": int((h2h["result"] == "L").sum()),
        f"{team_a}_gf_avg": round(h2h["gf"].mean(), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Features base para prode Mundial 2026")
    parser.add_argument("--since", type=int, default=2014,
                        help="Anio desde el cual computar el resumen (default: 2014)")
    parser.add_argument("--no-download", action="store_true",
                        help="No bajar datos, usar el cache local en ./data")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    print("1) Datos")
    download_data(force=not args.no_download)

    print("2) Cargando y procesando")
    results = load_results()
    matches = build_team_match_table(results)
    matches.to_csv(OUTPUT_DIR / "team_matches.csv", index=False)
    print(f"   {len(results):,} partidos -> {len(matches):,} filas equipo-partido")

    print(f"3) Resumen por seleccion (desde {args.since})")
    summary = team_summary(matches, since=args.since)
    summary.to_csv(OUTPUT_DIR / "team_features.csv")

    focus = [t for t in FOCUS_TEAMS if t in summary.index] or summary.index[:15]
    print("\n   Top selecciones del foco (ordenadas por puntos/partido):\n")
    print(summary.loc[focus].to_string())

    print("\nListo. Archivos en ./output/:")
    print("   - team_features.csv  (una fila por seleccion)")
    print("   - team_matches.csv   (tabla larga para entrenar el modelo)")


if __name__ == "__main__":
    main()
