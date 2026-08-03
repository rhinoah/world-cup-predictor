#!/usr/bin/env python3
"""
theme.py
========
La paleta y la tipografia de la app, en un solo lugar. Estaban sueltas arriba de
prode_app.py, asi que cualquier modulo de pantalla que se separara de ahi se
llevaba los colores hardcodeados o tenia que importar la app entera.

Los tres colores de estado (GOOD/MID/BAD) son el semaforo del prode: verde si se
acerto el marcador exacto, amarillo si solo la direccion, rojo si se fallo. Se
usan igual en las fichas de la pantalla principal y en el cuadro de eliminacion.
"""
from __future__ import annotations

F = "Segoe UI"

BG = "#15151b"        # fondo de la ventana
CARD = "#1f1f29"      # fichas y paneles
CARD2 = "#262633"     # hover y filas alternadas

ACCENT = "#2ee6a6"    # verde de la marca (botones principales)
ACCENT2 = "#5b8cff"   # azul secundario (acciones informativas)
WARN = "#ffb02e"      # avisos: recordatorios, cruces sin penales cargados

TXT = "#f5f5fa"       # texto principal
SUB = "#a6a6bd"       # texto secundario

GOOD = "#2ee6a6"      # marcador exacto
MID = "#ffd23e"       # acerto la direccion
BAD = "#ff5a5a"       # fallado
