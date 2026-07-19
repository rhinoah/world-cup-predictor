@echo off
REM ============================================================
REM Actualiza el dataset del prode (martj42) y regenera features.
REM Lo dispara una tarea programada cada manana; tambien se puede
REM correr a mano con doble clic.
REM Python: por defecto el launcher "py -3" del PATH. Si la variable
REM de entorno PRODE_PY apunta a un python.exe puntual, se usa esa
REM (util cuando el launcher resuelve a una instalacion no deseada).
REM ============================================================
cd /d "%~dp0"
if defined PRODE_PY (set PY="%PRODE_PY%") else (set PY=py -3)
echo ===================================================== >> update_log.txt
echo [%date% %time%] actualizando dataset... >> update_log.txt
%PY% build_features.py >> update_log.txt 2>&1
echo [%date% %time%] liquidando pronosticos de partidos ya jugados... >> update_log.txt
%PY% liquidar.py >> update_log.txt 2>&1
echo [%date% %time%] generando predicciones de la proxima jornada... >> update_log.txt
%PY% predict_matchday.py > predicciones_jornada.txt 2>&1
echo [%date% %time%] regenerando detalle de pronosticos para la app... >> update_log.txt
%PY% build_pronosticos.py >> update_log.txt 2>&1
echo [%date% %time%] listo. dataset + predicciones + detalle actualizados (exit %errorlevel%) >> update_log.txt
