#!/usr/bin/env python3
"""
capturas.py
===========
Genera las capturas de la app que muestra el README, en docs/.

    PRODE_NOW=2026-06-25T18:00 python -m scripts.capturas

Por que existe un script en vez de sacarlas a mano:

  * REPRODUCIBLE. El Mundial termino, asi que hace falta el modo demo
    (`prode/clock.py`) para que la app tenga algo que mostrar. Con la misma
    `PRODE_NOW` las capturas salen identicas cuando cambie la UI.
  * SIN DATOS PERSONALES. Los nombres reales de los prodes viven en
    `prodes.json`, que no se versiona. Aca se pisan EN MEMORIA por los genericos
    del codigo ("Prode A"/"Prode B"), asi que una captura no puede filtrar lo que
    el codigo ya cuida. `prodes.json` ni se abre.
  * SIN ESCRITORIO DE FONDO. `ImageGrab` saca de la pantalla de verdad, asi que
    cualquier cosa que asome fuera de la ventana (barra de tareas, otra ventana
    abierta) termina en la foto. Se dibuja un panel negro a pantalla completa
    detras de lo que se captura.

Las ventanas aparecen unos segundos: es la app de verdad, no hay forma de
fotografiar lo que no se dibuja.
"""
from __future__ import annotations

import time

from PIL import ImageGrab

from prode import clock, paths
from prode.data import app_data

# Los prodes genericos del codigo, no los del prodes.json local.
_GENERICOS = [
    {"name": "Prode A", "short": "A", "exact": 3, "dir": 1},
    {"name": "Prode B", "short": "B", "exact": 6, "dir": 3},
]
app_data.PRODE_CFG = _GENERICOS
app_data.PRODES = {p["name"]: (p["exact"], p["dir"]) for p in _GENERICOS}
app_data.PRODE_NAMES = [p["name"] for p in _GENERICOS]
app_data.PRODE_SHORT = [p["short"] for p in _GENERICOS]

from prode.ui import app as ui        # noqa: E402  (despues de pisar los nombres)

_app = None
_fondo = None


def _asentar(w, veces=25):
    """Deja que Tk dibuje de verdad antes de capturar."""
    for _ in range(veces):
        w.update_idletasks()
        w.update()
        time.sleep(0.04)


def _panel_de_fondo():
    """Panel negro a pantalla completa, para que atras no haya escritorio."""
    global _fondo
    if _fondo is None or not _fondo.winfo_exists():
        _fondo = ui.ctk.CTkToplevel(_app)
        _fondo.overrideredirect(True)
        _fondo.configure(fg_color="#0d0d12")
        _fondo.geometry(f"{_app.winfo_screenwidth()}x{_app.winfo_screenheight()}+0+0")
    _fondo.deiconify()
    _fondo.attributes("-topmost", True)
    _fondo.lift()
    return _fondo


def _capturar(w, nombre):
    f = _panel_de_fondo()
    _asentar(w, 6)
    # Que entre en la pantalla: Tk las abre en cascada y la de llaves (924 px de
    # alto) se salia por abajo, con lo que la foto agarraba la barra de tareas.
    sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
    an, al = w.winfo_width(), w.winfo_height()
    w.geometry(f"+{max(0, (sw - an) // 2)}+{max(0, min(40, sh - al - 10))}")
    # El lift de lo que se captura va DESPUES del fondo: los dos son topmost y
    # entre dos topmost gana el ultimo que se eleva. Al reves la foto sale negra.
    w.attributes("-topmost", True)
    w.lift(f)
    w.focus_force()
    _asentar(w, 25)

    x, y = w.winfo_rootx(), w.winfo_rooty()
    an, al = w.winfo_width(), w.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + an, y + al))
    w.attributes("-topmost", False)
    paths.DOCS.mkdir(exist_ok=True)
    img.save(paths.DOCS / nombre)
    print(f"  {nombre:<22} {img.size[0]}x{img.size[1]}")


def _ultimo_modal():
    hijas = [c for c in _app.winfo_children()
             if isinstance(c, ui.ctk.CTkToplevel) and c is not _fondo]
    return hijas[-1] if hijas else None


def _cerrar_modales():
    for c in list(_app.winfo_children()):
        if isinstance(c, ui.ctk.CTkToplevel) and c is not _fondo:
            c.destroy()
    _app._modal = None
    _asentar(_app, 6)


def main():
    global _app
    if not clock.simulado():
        raise SystemExit(
            "Corré esto con el reloj simulado, si no la app sale vacia:\n"
            "    PRODE_NOW=2026-06-25T18:00 python -m scripts.capturas")

    _app = ui.App(None)
    _app.geometry("1400x820+40+40")
    _app.deiconify()
    _app.lift()
    _asentar(_app, 40)
    try:
        _capturar(_app, "app-principal.png")
        for abrir, nombre in ((_app._show_groups, "app-grupos.png"),
                              (_app._show_bracket, "app-llaves.png"),
                              (_app._show_prev_day, "app-jornada.png")):
            abrir()
            _capturar(_ultimo_modal(), nombre)
            _cerrar_modales()

        # el popup de cargar resultado, sobre un partido del dia ya jugado
        hoy = app_data.logical_today()
        jugados = [m for m in _app.fx
                   if app_data.logical_date(m["kickoff"]) == hoy and m["real"] is not None]
        if jugados:
            _app._load_result(jugados[0])
            _capturar(_ultimo_modal(), "app-cargar.png")
            _cerrar_modales()
        else:
            print("  !! no hay partido con resultado hoy: falta app-cargar.png")
    finally:
        try:
            _app.destroy()
        except Exception:
            pass
    print(f"listo -> {paths.DOCS}")


if __name__ == "__main__":
    main()
