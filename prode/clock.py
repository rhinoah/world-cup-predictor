#!/usr/bin/env python3
"""
prode/clock.py
==============
El reloj del proyecto, en un solo lugar y simulable.

Existe por una razon muy concreta: el Mundial 2026 termino, asi que la app abre
en blanco. No hay proximo partido, ni pronosticos del dia, ni cuenta regresiva
-- justo lo que hace interesante a la pantalla principal. Cualquiera que clone
el repo ve eso, y sacarle capturas al proyecto es imposible.

Con `PRODE_NOW` la app cree que es otro momento:

    PRODE_NOW=2026-06-25T18:00 python prode_app.py

El reloj CORRE desde ahi (no queda congelado): se guarda la diferencia contra la
hora real al arrancar y se le suma al reloj de verdad. Asi la cuenta regresiva
baja de verdad y un GIF muestra algo vivo.

Ojo con lo que NO hace: no inventa datos. El dataset ya tiene los 104 partidos
jugados, asi que la capa de datos ademas oculta los resultados de los partidos
que, para el reloj simulado, todavia no se jugaron (ver `app_data.fixture`). Sin
eso la columna de MAÑANA mostraria resultados de partidos que no empezaron.

Fuera del modo demo esto es `datetime.now()` y nada mas.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

ENV = "PRODE_NOW"

_OFFSET: timedelta | None = None


def _leer_offset() -> timedelta | None:
    """La diferencia entre la hora simulada y la real, fijada al importar.

    Un valor ilegible avisa y se ignora: quedarse en la hora real sin decir nada
    haria pensar que el modo demo no existe."""
    crudo = os.environ.get(ENV, "").strip()
    if not crudo:
        return None
    try:
        return datetime.fromisoformat(crudo) - datetime.now()
    except ValueError:
        print(f"{ENV}={crudo!r} no es una fecha ISO (2026-06-25T18:00); "
              "se usa la hora real", file=sys.stderr)
        return None


_OFFSET = _leer_offset()


def now() -> datetime:
    """La hora actual, o la simulada si PRODE_NOW esta seteada."""
    real = datetime.now()
    return real if _OFFSET is None else real + _OFFSET


def simulado() -> bool:
    """True si el reloj esta corriendo en una fecha simulada."""
    return _OFFSET is not None


def descripcion() -> str:
    """Para mostrar en pantalla que esto no es la hora real."""
    return "" if _OFFSET is None else f"modo demo · {now():%d/%m/%Y %H:%M}"
