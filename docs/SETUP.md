# Einrichtung einer Arbeitsmaschine (HAM11 / DES11)

Diese Anleitung richtet eine Windows-Maschine für die Arbeit an der Codex
Control Bridge ein. Alles kommt über GitHub; lokale Zustände werden nicht
übertragen.

## Grundregeln

- **Ubuntu/WSL nicht anfassen.** Es wird von Codex für Dorfschaft genutzt.
  Claude Code läuft als native Windows-App, nicht in WSL.
- **GitHub ist die einzige Quelle (SSOT).** Kein Austausch über Chat, Clipboard
  oder lokale Kopien.
- **Das `.venv` reist nicht mit** (steht in `.gitignore`) und wird auf jeder
  Maschine neu erzeugt.
- **Pfad überall gleich:** `E:\_DEV\Codex-Control-Bridge` (auf jeder Maschine
  physisch getrennt, nur namensgleich).

---

## A. Erststart (Maschine noch nicht eingerichtet)

### 1. Git
```powershell
git --version
```
Fehlt Git:
```powershell
winget install --id Git.Git -e --source winget
```
(PowerShell danach neu öffnen.) Identität setzen:
```powershell
git config --global user.name  "zippeliniot"
git config --global user.email "zippelin.iot@gmail.com"
```

### 2. Python 3
```powershell
python --version
```
Fehlt Python:
```powershell
winget install --id Python.Python.3.12 -e
```
(PowerShell danach neu öffnen.)

### 3. Claude Code (native Windows-App)
```powershell
claude --version
```
Fehlt Claude Code:
```powershell
irm https://claude.ai/install.ps1 | iex
```
Danach PATH ergänzen (falls der Installer es anmahnt) und Terminal neu öffnen:
```powershell
$binPath = "$HOME\.local\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path","User")
if ($userPath -notlike "*$binPath*") {
  [Environment]::SetEnvironmentVariable("Path","$userPath;$binPath","User")
}
```

### 4. Repository klonen
```powershell
New-Item -ItemType Directory -Force -Path E:\_DEV | Out-Null
cd E:\_DEV
git clone https://github.com/zippeliniot/Codex-Control-Bridge.git Codex-Control-Bridge
cd E:\_DEV\Codex-Control-Bridge
```

### 5. Claude Code anmelden und Ordner vertrauen
```powershell
claude
```
- Login über das Claude-Konto (Abo), Browser bestätigen.
- „Do you trust the files in this folder?" → **Yes** (Pfad
  `E:\_DEV\Codex-Control-Bridge`). Damit liest Claude Code `CLAUDE.md` und
  `.claude/settings.json`.
- Chrome-Extension-Frage: **No, keep browser tools off**.
- Mit `/exit` zurück zu PowerShell.

### 6. Repo-lokales `.venv` anlegen
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### 7. Verifizieren
```powershell
.venv\Scripts\python -m unittest discover -s tests
.\scripts\handover-check.ps1
```
Erwartung: alle Tests grün, Gate `ERGEBNIS: PASS`. Dann ist die Maschine
arbeitsbereit.

---

## B. Schnellstart (Maschine bereits eingerichtet)

```powershell
cd E:\_DEV\Codex-Control-Bridge
git pull origin main
.venv\Scripts\python -m pip install -r requirements.txt   # falls neue Abhängigkeiten
.venv\Scripts\python -m unittest discover -s tests
.\scripts\handover-check.ps1
```

---

## Hinweise

- **Windows Terminal** statt klassischer Konsole nutzen — dort funktioniert
  Einfügen mit `Strg+V`.
- Meldet `handover-check.ps1` „Ausführung von Skripts deaktiviert":
  `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` (einmalig).
- Vor jedem Maschinenwechsel: alles committen und pushen, `handover-check.ps1`
  muss `PASS` zeigen.
