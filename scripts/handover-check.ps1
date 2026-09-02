#!/usr/bin/env pwsh
#
# handover-check.ps1 - Uebergabe-Gate der Codex Control Bridge (Windows/PowerShell).
# Prueft fail-closed, ob der aktuelle Stand vollstaendig auf GitHub liegt.
# Vor JEDEM Maschinenwechsel ausfuehren (siehe docs/handover/HANDOVER.md).
#
# Exit 0 = PASS (Uebergabe zulaessig), Exit 1 = FAIL (Uebergabe NICHT zulaessig).
#
# Nutzung:
#   pwsh scripts\handover-check.ps1            # Uebergabebranch = main
#   pwsh scripts\handover-check.ps1 <branch>   # abweichender Uebergabebranch

param([string]$ExpectedBranch = "main")

$ErrorActionPreference = "Continue"
$script:Fail = $false
function Ok($m)   { Write-Host "[ OK ]   $m" }
function Bad($m)  { Write-Host "[ FAIL ] $m"; $script:Fail = $true }
function Warn($m) { Write-Host "[ WARN ] $m" }
function Indent($text) {
    foreach ($line in ($text -split "`r?`n")) {
        if ($line.Trim().Length -gt 0) { Write-Host "         $line" }
    }
}

Write-Host "=== Codex Control Bridge - Handover Check ==="

# 0) Git-Repository vorhanden?
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Bad "Kein Git-Repository. Abbruch."; exit 1 }

# 1) Aktueller Branch = Uebergabebranch?
$current = (git rev-parse --abbrev-ref HEAD | Out-String).Trim()
if ($current -eq $ExpectedBranch) { Ok "Branch = $ExpectedBranch" }
else { Bad "Branch ist '$current', erwartet '$ExpectedBranch'" }

# 2) Working Tree sauber (keine uncommitted Aenderungen)?
$dirty = (git status --porcelain --untracked-files=no | Out-String)
if ([string]::IsNullOrWhiteSpace($dirty)) { Ok "Working Tree sauber (keine offenen Aenderungen)" }
else { Bad "Uncommitted Aenderungen vorhanden:"; Indent $dirty }

# 3) Keine untracked Dateien?
$untracked = (git ls-files --others --exclude-standard | Out-String)
if ([string]::IsNullOrWhiteSpace($untracked)) { Ok "Keine untracked Dateien" }
else { Bad "Untracked Dateien vorhanden (nicht auf GitHub):"; Indent $untracked }

# 4) Keine offenen Stashes?
$stash = (git stash list | Out-String)
if ([string]::IsNullOrWhiteSpace($stash)) { Ok "Keine offenen Stashes" }
else { Bad "Offene Stashes vorhanden (nicht auf GitHub):"; Indent $stash }

# 5) Remote-Abgleich: lokal darf NICHT ahead von origin sein.
git remote get-url origin *> $null
if ($LASTEXITCODE -eq 0) {
    git fetch --quiet origin $ExpectedBranch 2>$null
    git rev-parse --verify --quiet "origin/$ExpectedBranch" *> $null
    if ($LASTEXITCODE -eq 0) {
        $ahead  = (git rev-list --count "origin/$ExpectedBranch..HEAD" | Out-String).Trim()
        $behind = (git rev-list --count "HEAD..origin/$ExpectedBranch" | Out-String).Trim()
        if ($ahead -eq "0") { Ok "Alles gepusht (lokal nicht ahead von origin/$ExpectedBranch)" }
        else { Bad "$ahead Commit(s) nicht gepusht -> 'git push origin $ExpectedBranch' noetig" }
        if ($behind -ne "0") { Warn "$behind Commit(s) auf origin, die lokal fehlen (ggf. erst pullen)" }
    } else { Bad "origin/$ExpectedBranch nicht gefunden - wurde der Branch je gepusht?" }
} else { Bad "Kein 'origin' konfiguriert - GitHub-Remote fehlt" }

# 6) Pflichtdokumente (fachliche Arbeitsgrundlage) vorhanden?
$required = @(
    "docs/PROJEKTKONZEPT.md",
    "docs/architecture/ARCHITECTURE.md",
    "docs/handover/HANDOVER.md",
    "docs/architecture/machines.md"
)
foreach ($d in $required) {
    git ls-files --error-unmatch $d *> $null
    if ((Test-Path $d) -and ($LASTEXITCODE -eq 0)) { Ok "Pflichtdokument versioniert: $d" }
    else { Bad "Pflichtdokument fehlt oder nicht versioniert: $d" }
}

Write-Host "============================================"
if (-not $script:Fail) {
    Write-Host "ERGEBNIS: PASS - Uebergabe zulaessig."
    exit 0
} else {
    Write-Host "ERGEBNIS: FAIL - Uebergabe NICHT zulaessig. Erst alles committen und pushen."
    exit 1
}
