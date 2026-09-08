@echo off
REM Codex Control Bridge - dauerhaftes Ueberwachungsfenster (BRIDGE-018).
REM Kann an jedem Ort liegen (z. B. Downloads, Desktop) - der Pfad zum
REM Repo ist unten fest eingetragen, unabhaengig davon, wo diese Datei
REM selbst gespeichert ist.
REM
REM Passt zur registry.yaml: HAM11 und DES11 haben aktuell beide dieselbe
REM Basis E:\_DEV. Bei einer neuen Maschine mit anderer Basis: die Zeile
REM REPO_PATH unten UND registry.yaml im Repo anpassen.

setlocal

set "REPO_PATH=E:\_DEV\Codex-Control-Bridge"
set "INTERVAL=15"

echo === Codex Control Bridge - Board-Ueberwachung ===
echo Repo: %REPO_PATH%
echo.

if not exist "%REPO_PATH%" (
    echo FEHLER: Repo-Verzeichnis nicht gefunden: %REPO_PATH%
    echo Pruefe, ob diese Maschine die Basis E:\_DEV verwendet
    echo ^(siehe registry.yaml im Repo^), und passe REPO_PATH oben ggf. an.
    goto :ende
)

cd /d "%REPO_PATH%"

if not exist ".venv\Scripts\python.exe" (
    echo Kein .venv gefunden - lege es jetzt an ^(einmalig^)...
    python -m venv .venv
    if errorlevel 1 (
        echo FEHLER: venv-Erstellung fehlgeschlagen. Ist Python installiert und im PATH?
        goto :ende
    )
    echo Installiere Abhaengigkeiten aus requirements.txt...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo FEHLER: pip install fehlgeschlagen.
        goto :ende
    )
    echo .venv fertig eingerichtet.
    echo.
)

echo Starte bridge board --watch --interval %INTERVAL%
echo ^(Fenster einfach offen lassen. Beenden mit Strg+C.^)
echo.

".venv\Scripts\python.exe" src\bridge\cli.py --root . board --watch --interval %INTERVAL%

:ende
echo.
pause
endlocal
