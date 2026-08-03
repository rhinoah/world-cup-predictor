@echo off
REM Lanza el Centro de Comando del prode (sin ventana de consola).
REM Doble clic para abrir. Para SALIR de verdad: click derecho en el icono
REM de la bandeja (al lado del reloj) -> Salir.
REM
REM Los argumentos se le pasan a la app: setup_windows.bat usa "--minimized"
REM para que el arranque con Windows abra directo en la bandeja.
cd /d "%~dp0"
start "" pythonw prode_app.py %*
