# BRIDGE-021 — CLAUDE.md: `run finish --summary` verbindlich machen

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0021 |
| project_id | codex-control-bridge |
| task_class | DOCS |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe LOW (reine Dokumentänderung, keine Codeänderung) |

## Kontext

Beim Review von BRIDGE-019 (siehe `results/BRIDGE-0019/RUN-01/result.yaml`)
hat sich gezeigt: Claude Code hatte `bridge run finish` ohne `--summary` und
ohne `--from draft.yaml` aufgerufen. Das Ergebnisdokument war dadurch formal
gültig, aber inhaltlich fast leer — kein `summary`, keine
`acceptance_results`, unvollständige `changed_files`. Der Steuerprozess
musste die eigentlichen Änderungen manuell per `git diff` nachvollziehen,
statt sich auf den Bridge-eigenen Ergebnisbericht verlassen zu können.

`CLAUDE.md` muss deshalb `--summary` beim `run finish`-Aufruf verbindlich
vorschreiben, nicht nur als Empfehlung.

## Von Claude Code umzusetzen

In `CLAUDE.md`, Abschnitt "Auftragsabschluss — Pflicht-Footer" (direkt nach
dem bestehenden Abschnitt, vor "Python-Umgebung"), einen neuen Unterabschnitt
ergänzen:

```markdown
## `run finish` — Zusammenfassung verbindlich

`bridge run finish` wird **niemals** ohne `--summary` aufgerufen — ein
nackter Aufruf (`run finish --status COMPLETED --actor claude-code`) lässt
`result.yaml` ohne aussagekräftigen Inhalt zurück (leeres `summary`, leere
`acceptance_results`, unvollständige `changed_files`) und zwingt den
Steuerprozess, Änderungen manuell per `git diff` zu rekonstruieren.

- `--summary "..."`: kurze, konkrete Zusammenfassung, was der Lauf getan hat
  (nicht nur "Auftrag abgeschlossen").
- Wo `acceptance_results` sinnvoll dokumentiert werden soll (Abgleich gegen
  die Akzeptanzkriterien aus `work-packages/BRIDGE-xxx.md`): `--from
  draft.yaml` mit den entsprechenden Feldern nutzen, statt sie wegzulassen.
- Ziel: `result.yaml` muss für sich allein lesbar sein, ohne dass jemand den
  Commit-Verlauf durchsuchen muss.
```

Sonst keine inhaltliche Änderung an `CLAUDE.md` — nur diese Ergänzung.

## Akzeptanzkriterien

- Neuer Unterabschnitt in `CLAUDE.md` an der genannten Stelle, wortgleich
  oder sinngemäß wie oben.
- Kein bestehender Abschnitt in `CLAUDE.md` inhaltlich verändert.
- Alle Tests bleiben grün (reine Dokumentänderung, keine Coderegression
  erwartet — Testlauf trotzdem zur Bestätigung).
- `run finish` für diesen Auftrag selbst wird **mit `--summary`** aufgerufen
  (Eigenanwendung der neuen Regel als Beleg, dass sie verstanden wurde).
