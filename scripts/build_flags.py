#!/usr/bin/env python3
"""
build_flags.py
==============
Descarga las banderas (PNG) de las 48 selecciones del Mundial desde flagcdn.com
a la carpeta flags/. La app las muestra al lado del nombre de cada equipo.
Correr una sola vez (idempotente: no re-baja las que ya estan).
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from prode import paths
from prode.tournament.teams import FLAG_ISO   # padron unico (no pasa por app_data: evita cargar pandas)

DEST = paths.FLAGS
WIDTH = "w40"   # ancho 40px (liviano y nitido a tamano chico)


def main():
    DEST.mkdir(exist_ok=True)
    ok, faltan = 0, []
    for team, iso in FLAG_ISO.items():
        dest = DEST / f"{iso}.png"
        if dest.exists():
            ok += 1
            continue
        try:
            urllib.request.urlretrieve(f"https://flagcdn.com/{WIDTH}/{iso}.png", dest)
            ok += 1
        except Exception as e:  # noqa: BLE001
            faltan.append(f"{team} ({iso}): {e}")
    print(f"banderas: {ok}/{len(FLAG_ISO)} en {DEST}/")
    for f in faltan:
        print("  ERROR", f)


if __name__ == "__main__":
    main()
