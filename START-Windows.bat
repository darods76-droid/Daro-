@echo off
title DARO-CAD - Technische Zeichnungen
cd /d "%~dp0"

echo.
echo   ============================================
echo      DARO-CAD  -  Technische Zeichnungen
echo   ============================================
echo.

rem --- Liegt die App neben dieser Datei? ---------------------------------
if not exist "daro_cad\__main__.py" goto FALSCHERORDNER

rem --- Python 3.9 oder neuer suchen -------------------------------------
rem Jede Pruefung einzeln: "if ... && set" wertet Batch anders aus als
rem erwartet, deshalb hier Schritt fuer Schritt mit Sprungmarken.
set "PYCMD="

py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto GEFUNDEN

python -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto GEFUNDEN

python3 -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=python3"
if defined PYCMD goto GEFUNDEN

goto KEINPYTHON

:GEFUNDEN
echo   Python gefunden: %PYCMD%
echo.
echo   Der Browser oeffnet sich gleich von selbst.
echo   Falls nicht, im Browser diese Adresse eingeben:
echo.
echo        http://127.0.0.1:8765
echo.
echo   Zum Beenden: dieses Fenster schliessen.
echo.

%PYCMD% -m daro_cad

echo.
echo   DARO-CAD wurde beendet.
pause
exit /b 0

:KEINPYTHON
echo   Python 3 wurde auf diesem Rechner nicht gefunden.
echo.
echo   So geht es weiter:
echo     1. Die Seite python.org oeffnet sich gleich von selbst.
echo     2. Den grossen Knopf "Download Python" anklicken.
echo     3. WICHTIG beim Installieren: ganz unten im ersten Fenster
echo        "Add python.exe to PATH" ankreuzen!
echo     4. Danach diese Datei hier erneut doppelklicken.
echo.
start https://www.python.org/downloads/
pause
exit /b 1

:FALSCHERORDNER
echo   Der Ordner "daro_cad" liegt nicht neben dieser Datei.
echo.
echo   Vermutlich wurde das ZIP nicht vollstaendig entpackt.
echo   In Windows: Rechtsklick auf das ZIP, "Alle extrahieren...",
echo   dann diese Datei aus dem entpackten Ordner starten.
echo.
pause
exit /b 1
