#!/usr/bin/env python3
"""
single_instance.py
==================
Una sola ventana abierta a la vez. La app arranca sola con Windows y ademas se
la abre a mano, asi que sin esto terminaban dos instancias peleandose por el
mismo CSV.

El lock es un puerto local: el primero que lo toma es el duenio. Si ya esta
tomado, se le manda "show" al que escucha y este proceso se va.
"""
from __future__ import annotations

import socket

SINGLE_PORT = 50607   # puerto local para detectar instancia unica


def check_single_instance():
    """Devuelve:
      - un socket servidor  -> es la primera instancia (mantenerlo vivo).
      - None                -> ya hay una instancia VIVA (le pedimos mostrarse, salir).
      - False               -> el puerto esta ocupado pero nadie responde (proceso
                               colgado / otra app): abrir igual, sin lock."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", SINGLE_PORT))
    except OSError:
        try:
            c = socket.create_connection(("127.0.0.1", SINGLE_PORT), timeout=1.5)
            c.sendall(b"show")
            c.close()
            return None            # instancia viva -> esa se muestra, esta sale
        except Exception:
            return False           # puerto tomado sin instancia viva -> abrir igual
    srv.listen(1)
    return srv
