@echo off
REM ============================================================
REM Actualiza el dataset del prode y regenera todo lo que depende de el.
REM Lo dispara una tarea programada cada manana; tambien se puede
REM correr a mano con doble clic.
REM
REM La SECUENCIA no vive aca: esta en run.py (flujo "update"), asi que
REM el .bat, el README y la tarea programada no pueden quedar diciendo
REM cosas distintas. Para ver los pasos:  python run.py --list
REM
REM Python: por defecto el launcher "py -3" del PATH. Si la variable
REM de entorno PRODE_PY apunta a un python.exe puntual, se usa esa
REM (util cuando el launcher resuelve a una instalacion no deseada).
REM ============================================================
cd /d "%~dp0"
if defined PRODE_PY (set PY="%PRODE_PY%") else (set PY=py -3)
echo ===================================================== >> update_log.txt
echo [%date% %time%] actualizando... >> update_log.txt
%PY% run.py update >> update_log.txt 2>&1
echo [%date% %time%] listo (exit %errorlevel%) >> update_log.txt
