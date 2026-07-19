#!/usr/bin/env python3
"""
build_horarios.py
=================
Genera fixture_horarios.csv: la hora de cada partido de fase de grupos del
Mundial 2026 en HORA DE ARGENTINA (UTC-3).

Las horas oficiales de FIFA son en US Eastern Time (EDT = UTC-4), asi que
Argentina = ET + 1 hora. Se cruza con el fixture de martj42 por par de equipos
(normalizando nombres) para no depender de la convencion de fecha de cada
fuente. Correr de nuevo si cambia algun horario.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

# fecha_ET | home | away | kickoff_ET (24h). Fuente: worldcuppass.com
RAW = """\
2026-06-11|Mexico|South Africa|15:00
2026-06-11|South Korea|Czechia|22:00
2026-06-12|Canada|Bosnia and Herzegovina|15:00
2026-06-12|USA|Paraguay|21:00
2026-06-13|Qatar|Switzerland|15:00
2026-06-13|Brazil|Morocco|18:00
2026-06-13|Haiti|Scotland|21:00
2026-06-14|Australia|Türkiye|00:00
2026-06-14|Germany|Curaçao|13:00
2026-06-14|Netherlands|Japan|16:00
2026-06-14|Ivory Coast|Ecuador|19:00
2026-06-14|Sweden|Tunisia|22:00
2026-06-15|Spain|Cabo Verde|12:00
2026-06-15|Belgium|Egypt|15:00
2026-06-15|Saudi Arabia|Uruguay|18:00
2026-06-15|Iran|New Zealand|21:00
2026-06-16|France|Senegal|15:00
2026-06-16|Iraq|Norway|18:00
2026-06-16|Argentina|Algeria|21:00
2026-06-17|Austria|Jordan|00:00
2026-06-17|Portugal|DR Congo|13:00
2026-06-17|England|Croatia|16:00
2026-06-17|Ghana|Panama|19:00
2026-06-17|Uzbekistan|Colombia|22:00
2026-06-18|Czechia|South Africa|12:00
2026-06-18|Switzerland|Bosnia and Herzegovina|15:00
2026-06-18|Canada|Qatar|18:00
2026-06-18|Mexico|South Korea|21:00
2026-06-20|Türkiye|Paraguay|00:00
2026-06-19|USA|Australia|15:00
2026-06-19|Scotland|Morocco|18:00
2026-06-19|Brazil|Haiti|20:30
2026-06-20|Netherlands|Sweden|13:00
2026-06-20|Germany|Ivory Coast|16:00
2026-06-20|Ecuador|Curaçao|20:00
2026-06-21|Tunisia|Japan|00:00
2026-06-21|Spain|Saudi Arabia|12:00
2026-06-21|Belgium|Iran|15:00
2026-06-21|Uruguay|Cabo Verde|18:00
2026-06-21|New Zealand|Egypt|21:00
2026-06-22|Argentina|Austria|13:00
2026-06-22|France|Iraq|17:00
2026-06-22|Norway|Senegal|20:00
2026-06-22|Jordan|Algeria|23:00
2026-06-23|Portugal|Uzbekistan|13:00
2026-06-23|England|Ghana|16:00
2026-06-23|Panama|Croatia|19:00
2026-06-23|Colombia|DR Congo|22:00
2026-06-24|Switzerland|Canada|15:00
2026-06-24|Bosnia and Herzegovina|Qatar|15:00
2026-06-24|Scotland|Brazil|18:00
2026-06-24|Morocco|Haiti|18:00
2026-06-24|Czechia|Mexico|21:00
2026-06-24|South Africa|South Korea|21:00
2026-06-25|Curaçao|Ivory Coast|16:00
2026-06-25|Ecuador|Germany|16:00
2026-06-25|Japan|Sweden|19:00
2026-06-25|Tunisia|Netherlands|19:00
2026-06-25|Türkiye|USA|22:00
2026-06-25|Paraguay|Australia|22:00
2026-06-26|Norway|France|15:00
2026-06-26|Senegal|Iraq|15:00
2026-06-26|Cabo Verde|Saudi Arabia|20:00
2026-06-26|Uruguay|Spain|20:00
2026-06-26|Egypt|Iran|23:00
2026-06-26|New Zealand|Belgium|23:00
2026-06-27|Panama|England|17:00
2026-06-27|Croatia|Ghana|17:00
2026-06-27|Colombia|Portugal|19:30
2026-06-27|DR Congo|Uzbekistan|19:30
2026-06-27|Algeria|Austria|22:00
2026-06-27|Jordan|Argentina|22:00
"""

# nombres de worldcuppass -> nombres de martj42
ALIAS = {
    "USA": "United States",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
}


def norm(n: str) -> str:
    n = n.strip()
    return ALIAS.get(n, n)


def main():
    horarios = {}
    for line in RAW.strip().splitlines():
        d, h, a, t = [x.strip() for x in line.split("|")]
        dt_arg = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M") + timedelta(hours=1)
        H, A = norm(h), norm(a)
        horarios[(H, A)] = dt_arg
        horarios[(A, H)] = dt_arg                      # por si el orden difiere

    res = pd.read_csv("data/results.csv")
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    fx = res[(res["tournament"] == "FIFA World Cup")
             & (res["date"] >= "2026-06-11") & (res["date"] <= "2026-06-27")]

    rows, missing = [], []
    for _, m in fx.iterrows():
        h, a = m["home_team"], m["away_team"]
        dt = horarios.get((h, a))
        if dt is None:
            missing.append(f"{h} vs {a}")
            continue
        rows.append({"home_team": h, "away_team": a,
                     "kickoff_arg": dt.strftime("%Y-%m-%d %H:%M")})

    out = pd.DataFrame(rows).sort_values("kickoff_arg").reset_index(drop=True)
    out.to_csv("fixture_horarios.csv", index=False)
    print(f"fixture_horarios.csv -> {len(out)} partidos con horario (hora Argentina)")
    if missing:
        print(f"\nSIN HORARIO ({len(missing)}) -- revisar nombres/alias:")
        for x in missing:
            print("  -", x)
    else:
        print("OK: todos los partidos del fixture quedaron con horario.")
    print("\nprimeros:")
    print(out.head(6).to_string(index=False))


if __name__ == "__main__":
    main()
