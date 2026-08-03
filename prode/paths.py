#!/usr/bin/env python3
"""
prode/paths.py
==============
Donde esta cada cosa, calculado una sola vez.

Antes cada modulo hacia su propio `BASE = Path(__file__).resolve().parent` y le
funcionaba porque todos vivian en la raiz. Al repartirlos en paquetes eso deja de
ser cierto: `prode/data/app_data.py` tiene su parent en `prode/data/`, no en la
raiz del repo, y los CSV dejarian de aparecer. Aca queda el unico calculo, y el
resto importa de aca.

Los scripts ademas usaban rutas relativas ("data/results.csv"), o sea que
dependian de que se los corriera parado en la raiz -- `backfill_ev.py` incluso
hacia `os.chdir()` para forzarlo. Con las rutas absolutas eso no hace falta.
"""
from __future__ import annotations

from pathlib import Path

# paths.py esta en prode/, asi que la raiz del repo es su abuelo.
ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"                       # CSV crudos (no versionados)
OUTPUT = ROOT / "output"                   # features derivadas (no versionadas)
FLAGS = ROOT / "flags"                     # PNG de banderas (no versionados)
DOCS = ROOT / "docs"

RESULTS_CSV = DATA / "results.csv"         # el dataset de martj42
MANUAL_RESULTS_CSV = DATA / "manual_results.csv"
FINISHED_CSV = DATA / "finished.csv"

HORARIOS_CSV = ROOT / "fixture_horarios.csv"
THIRDS_JSON = ROOT / "thirds_table.json"

PRONOSTICOS_CSV = ROOT / "pronosticos.csv"          # datos personales, no versionados
PRONOSTICOS_JSON = ROOT / "pronosticos_detalle.json"
PRODES_JSON = ROOT / "prodes.json"
ERROR_LOG = ROOT / "prode_error.log"
