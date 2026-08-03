#!/usr/bin/env python3
"""
ui_tray.py
==========
Todo lo que la app hace FUERA de su ventana: el icono en la bandeja del sistema,
los bips de aviso y el canal por el que una segunda instancia le pide a la
primera que se muestre.

Va aparte porque no comparte nada con el resto de la pantalla -- ninguno de
estos metodos llama a otro de `App` -- y porque es la parte que mas depende de
que el sistema tenga cosas instaladas: sin `pystray` la app se cierra en vez de
minimizarse, y sin `winsound` (o fuera de Windows) simplemente no suena.
"""
from __future__ import annotations

import threading
import time

from prode import paths
from prode.ui.theme import ACCENT, BG

BASE = paths.ROOT

BEEP_MS = 1500

try:
    import winsound
except ImportError:                      # no es Windows: la app anda, muda
    winsound = None

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:                        # sin bandeja: cerrar en vez de ocultar
    pystray = None

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


def make_icon_image():
    img = Image.new("RGB", (64, 64), BG)
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=ACCENT)
    d.ellipse((24, 24, 40, 40), fill=BG)
    return img


class TrayMixin:
    """Se mezcla en `App`, que aporta la ventana (`self.after`, `self.deiconify`)
    y el socket de instancia unica en `self._single_srv`."""

    # ---------------- sonido ----------------
    def beep_long(self):
        if winsound:
            threading.Thread(target=lambda: winsound.Beep(880, BEEP_MS), daemon=True).start()

    def beep_reminder(self):
        if not winsound:
            return
        def seq():
            for f in (1047, 1319, 1047):
                winsound.Beep(f, 220); time.sleep(0.05)
        threading.Thread(target=seq, daemon=True).start()

    # ---------------- tray ----------------
    def _tray_image(self):
        try:
            p = paths.PNG
            if p.exists() and PILImage is not None:
                return PILImage.open(p).resize((64, 64))
        except Exception:
            pass
        return make_icon_image()

    def _single_listen(self):
        while True:
            try:
                conn, _ = self._single_srv.accept()
                conn.recv(16)
                conn.close()
                self.after(0, self._show_from_anywhere)
            except Exception:
                break

    def _show_from_anywhere(self):
        try:
            self.deiconify(); self.state("normal"); self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass

    def _setup_tray(self):
        if pystray is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar", self._tray_show, default=True),
            pystray.MenuItem("Salir", self._tray_quit))
        self.tray = pystray.Icon("prode_mundial", self._tray_image(), "Prode Mundial 2026", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def hide_to_tray(self):
        if pystray is not None:
            self.withdraw()
        else:
            self.destroy()

    def _tray_show(self, icon=None, item=None):
        self.after(0, self.deiconify); self.after(0, self.lift)

    def _tray_quit(self, icon=None, item=None):
        try:
            self.tray.stop()
        except Exception:
            pass
        self.after(0, self.destroy)
