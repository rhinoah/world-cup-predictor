@echo off
REM ============================================================
REM setup_windows.bat
REM ------------------------------------------------------------
REM Deja la app andando sola en Windows, OPCIONAL y reversible:
REM
REM   1) una tarea programada diaria que corre "run.py update"
REM      (baja los partidos nuevos, liquida y recalcula), y
REM   2) un acceso directo en el Inicio para que la app arranque
REM      con Windows, minimizada en la bandeja.
REM
REM Todo sale de %~dp0, asi que funciona desde donde este clonado
REM el repo y no guarda ninguna ruta fija.
REM
REM   setup_windows.bat install            (usa las 10:00)
REM   setup_windows.bat install 08:30
REM   setup_windows.bat status
REM   setup_windows.bat uninstall
REM
REM No hace falta ser administrador: la tarea se crea para el
REM usuario actual y solo corre con la sesion iniciada.
REM ============================================================
setlocal
cd /d "%~dp0"

set "TAREA=ProdeMundial_UpdateDataset"
set "INICIO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "ACCESO=%INICIO%\Prode Mundial.lnk"

if /i "%~1"=="install"   goto :install
if /i "%~1"=="uninstall" goto :uninstall
if /i "%~1"=="status"    goto :status
goto :ayuda

REM ------------------------------------------------------------
:install
set "HORA=%~2"
if "%HORA%"=="" set "HORA=10:00"

echo Creando la tarea diaria "%TAREA%" a las %HORA% ...
schtasks /create /tn "%TAREA%" /tr "\"%~dp0update_dataset.bat\"" /sc daily /st %HORA% /f
if errorlevel 1 (
    echo   FALLO al crear la tarea.
    goto :fin
)

echo Creando el acceso directo de arranque ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%ACCESO%');" ^
  "$s.TargetPath = '%~dp0Prode.bat';" ^
  "$s.Arguments = '--minimized';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "if (Test-Path '%~dp0prode.ico') { $s.IconLocation = '%~dp0prode.ico' };" ^
  "$s.WindowStyle = 7;" ^
  "$s.Save()"
if errorlevel 1 (
    echo   FALLO al crear el acceso directo.
    goto :fin
)

echo.
echo Listo:
echo   - la tarea "%TAREA%" corre todos los dias a las %HORA%
echo   - la app arranca con Windows, minimizada en la bandeja
echo.
echo Para deshacerlo:  setup_windows.bat uninstall
goto :fin

REM ------------------------------------------------------------
:uninstall
echo Borrando la tarea "%TAREA%" ...
schtasks /delete /tn "%TAREA%" /f 2>nul
if errorlevel 1 echo   (no existia)

echo Borrando el acceso directo de arranque ...
if exist "%ACCESO%" (del "%ACCESO%") else (echo   (no existia^))

echo.
echo Listo: no queda nada configurado. El repo sigue igual.
goto :fin

REM ------------------------------------------------------------
:status
echo Tarea programada:
schtasks /query /tn "%TAREA%" /fo list 2>nul | findstr /i "TaskName Next Status"
if errorlevel 1 echo   no esta creada
echo.
echo Arranque con Windows:
if exist "%ACCESO%" (echo   si: "%ACCESO%") else (echo   no)
goto :fin

REM ------------------------------------------------------------
:ayuda
echo Uso:
echo   setup_windows.bat install [HH:MM]   crea la tarea diaria + el arranque
echo   setup_windows.bat status            muestra que hay configurado
echo   setup_windows.bat uninstall         borra las dos cosas
echo.
echo La hora por defecto es 10:00. La tarea corre "run.py update":
echo   python run.py --list   muestra los pasos.

:fin
endlocal
