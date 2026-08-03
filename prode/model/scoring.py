#!/usr/bin/env python3
"""
scoring.py
==========
Reglas de puntaje del prode y decision de que marcador cargar. Fuente UNICA de
verdad: antes esta logica estaba duplicada en app_data, liquidar y los dos
backtests, y un cambio de reglas obligaba a editar cinco lugares.

Un prode puntua:
  - `exact` puntos si se acierta el marcador exacto,
  - `direction` puntos si se acierta solo la direccion (local / empate / visita),
  - 0 si se falla.

De ahi sale la regla de decision: no se carga el marcador MAS PROBABLE sino el
que maximiza el puntaje esperado

    EV(i,j) = ratio * P(marcador i-j) + P(direccion de i-j)

donde `ratio = exact/direction - 1` es el premio EXTRA por clavar el marcador,
en unidades de "aciertos de direccion".

OJO: el ratio NO es el mismo para todos los prodes. Con 3/1 vale 2.0 (el valor
que estaba hardcodeado en el modelo), pero con 6/3 vale 1.0: el prode 3/1
premia relativamente mas el marcador exacto, asi que en teoria cada prode
puede tener un marcador optimo distinto. Hoy la app sugiere UNO solo, calculado
con el puntaje por defecto (3/1); ver `best_ev_score(M, exact, direction)` si
alguna vez se quiere una sugerencia por prode.
"""
from __future__ import annotations

import numpy as np

# Puntaje por defecto (Prode "clasico"): 3 exacto / 1 direccion / 0 fallado.
DEFAULT_EXACT = 3
DEFAULT_DIR = 1


def ev_ratio(exact: int = DEFAULT_EXACT, direction: int = DEFAULT_DIR) -> float:
    """Premio extra por acertar el marcador exacto, en unidades de direccion."""
    return exact / direction - 1.0


def outcome(pred, real) -> str | None:
    """'exact' / 'dir' / 'miss'. None si falta el pronostico o el resultado."""
    if pred is None or real is None:
        return None
    (ph, pa), (rh, ra) = pred, real
    if ph == rh and pa == ra:
        return "exact"
    if np.sign(ph - pa) == np.sign(rh - ra):
        return "dir"
    return "miss"


def points(pred, real, exact: int = DEFAULT_EXACT, direction: int = DEFAULT_DIR) -> int:
    """Puntos que da `pred` contra `real` bajo el puntaje (exact, direction)."""
    return {"exact": exact, "dir": direction, "miss": 0}.get(outcome(pred, real), 0)


def outcome_probs(M: np.ndarray):
    """(p_local, p_empate, p_visita) a partir de la matriz de marcadores."""
    k = M.shape[0] - 1
    I, J = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
    return float(M[I > J].sum()), float(M[I == J].sum()), float(M[I < J].sum())


def ev_matrix(M: np.ndarray, exact: int = DEFAULT_EXACT, direction: int = DEFAULT_DIR):
    """Matriz de puntaje esperado (en unidades de `direction`) por cada marcador.

    Devuelve (ev, p_home, p_draw, p_away)."""
    k = M.shape[0] - 1
    I, J = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
    p_home, p_draw, p_away = outcome_probs(M)
    pdir = np.where(I > J, p_home, np.where(I == J, p_draw, p_away))
    return ev_ratio(exact, direction) * M + pdir, p_home, p_draw, p_away


def best_ev_score(M: np.ndarray, exact: int = DEFAULT_EXACT, direction: int = DEFAULT_DIR):
    """Marcador (i, j) que maximiza el puntaje esperado del prode."""
    ev, *_ = ev_matrix(M, exact, direction)
    bi, bj = np.unravel_index(int(np.argmax(ev)), ev.shape)
    return int(bi), int(bj)


def most_likely_score(M: np.ndarray):
    """Marcador mas probable (baseline contra el que se compara la regla EV)."""
    bi, bj = np.unravel_index(int(np.argmax(M)), M.shape)
    return int(bi), int(bj)


def modal(M: np.ndarray, ev: np.ndarray, rel):
    """Mejor marcador dentro de una direccion: (i, j, P, EV).

    `rel(i, j)` selecciona la direccion (p.ej. `lambda i, j: i > j` para local)."""
    k = M.shape[0] - 1
    cells = [(M[i, j], ev[i, j], i, j)
             for i in range(k + 1) for j in range(k + 1) if rel(i, j)]
    pm, evm, i, j = max(cells)
    return i, j, pm, evm
