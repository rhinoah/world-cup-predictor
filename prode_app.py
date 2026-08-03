#!/usr/bin/env python3
"""
prode_app.py
============
Atajo para abrir la app desde la raiz del repo:

    python prode_app.py

La app vive en `prode/ui/app.py`. Este archivo existe para que el doble clic en
`Prode.bat` y el acceso directo del Inicio sigan apuntando a la raiz, sin que
haya que saber la estructura de paquetes para arrancarla.
"""
from prode.ui.app import main

if __name__ == "__main__":
    main()
