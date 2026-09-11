# CCB — Arbeitsanweisung: Einbindung eines beliebigen neuen Projekts

Beschreibt, was konkret zu tun ist, um die Codex Control Bridge für ein
**neues, beliebiges** Projekt nutzbar zu machen — nicht nur für sich
selbst. Vollständig gegen den echten Code geprüft (Schema, Loader,
Adapter, Registry), Stand HEAD `af27302`. An Stellen, wo der Mechanismus
laut Code selbst **noch nicht vollständig verdrahtet** ist, steht das
hier explizit — keine Schönfärberei.

---

## Grundprinzip (Konzept-Abschnitt 11, `PROJEKTKONZEPT.md`)

Die Bridge selbst enthält **keine** projektspezifische Fachlogik.
Projektbezogene Regeln leben ausschließlich in einem **Projektprofil**
unter `projects/<project_id>/project.yaml`. Zwei Projekte sind bisher in
diesem Sinn vorgesehen:
- `codex-control-bridge` — die Bridge selbst, **real aktiv**,
  schreibend (`projects/codex-control-bridge/project.yaml`).
- `dorfschaft` — **nur als Vorlage** unter `projects/examples/`, read-only
  konzipiert, noch nicht als echtes, aktives Profil unter `projects/`
  angelegt.

---

## Schritt 1 — `project_id` und `task_prefix` festlegen

- `project_id`: eindeutige Kennung, **muss** dem Verzeichnisnamen unter
  `projects/` entsprechen (Loader lehnt sonst mit `ProfileError` ab,
  fail-closed).
- `task_prefix`: 1–8 Großbuchstaben (`^[A-Z]{1,8}$`), z. B. `BESS`,
  `ENFAN`, `DORFPORTAL`. Muss zum Format `<PREFIX>-<4 Ziffern>` der
  `bridge_task_id` passen.

**Wichtige, unbequeme Wahrheit, nicht verschweigen:** Der Code selbst
(`src/bridge/profiles.py`, wörtlicher Kommentar) sagt, dass die
Kollisionsprüfung zwischen `task_prefix`-Werten verschiedener Profile
**"bewusst später" (BRIDGE-011) folgen sollte** — ein Blick in
`store.py` zeigt: **diese Verdrahtung existiert aktuell nicht.** Es gibt
keine automatische Prüfung, die verhindert, dass zwei Projekte denselben
Prefix nutzen. Das muss der Steuerchat/Mensch manuell sicherstellen —
vor dem Anlegen eines neuen Profils immer `bridge project list`
ausführen und die bereits vergebenen Prefixe gegenprüfen.

## Schritt 2 — Repository lokal erreichbar machen (`registry.yaml`)

Der lokale Pfad eines Projekt-Repos wird **nicht** frei im Profil
angegeben, sondern aus `registry.yaml` (Repo-Wurzel von CCB) **plus**
dem Profilfeld `repository` zusammengesetzt: `<Basis-aus-registry.yaml>
/<repository>`. Aktueller Inhalt von `registry.yaml`:
```yaml
machines:
  HAM11: "E:\\_DEV"
  DES11: "E:\\_DEV"
```
- Arbeitet eine Maschine, die dort noch nicht gelistet ist, am neuen
  Projekt → `registry.yaml` um den Maschinennamen + Basispfad ergänzen
  (`schemas/registry.schema.yaml` beachten), committen, pushen.
- Das Zielprojekt-Repository muss unter `<Basis>\<repository>` real
  ausgecheckt sein — die Bridge legt es nicht selbst an.

## Schritt 3 — `projects/<project_id>/project.yaml` anlegen

Pflichtfelder laut `schemas/project.schema.yaml`
(`additionalProperties: false` — fail-closed, unbekannte Felder werden
abgelehnt):

| Feld | Pflicht? | Bedeutung |
|---|---|---|
| `schema_version` | ja | z. B. `"1.0"` |
| `kind` | ja | fest `bridge_project_profile` |
| `project_id` | ja | siehe Schritt 1 |
| `repository` | ja | lokaler Verzeichnisname (siehe Schritt 2) |
| `default_branch` | ja | i. d. R. `main` |
| `task_prefix` | ja | siehe Schritt 1 |
| `read_only` | ja | **zentrale Entscheidung, siehe Schritt 4** |

Optionale Felder, mit Entscheidungshilfe:

| Feld | Wofür | Empfehlung |
|---|---|---|
| `description` | Klartext-Beschreibung | immer ausfüllen, hilft künftigen Sitzungen |
| `worktree_root` | abweichendes Arbeitsverzeichnis innerhalb des Repos | nur setzen, wenn das Repo nicht im Root gearbeitet werden soll |
| `allowed_machines` | welche physischen Maschinen (Registry-Namen) an diesem Projekt arbeiten dürfen | explizit setzen, nicht leer lassen — sonst keine Einschränkung |
| `model_policy.default_model` / `default_reasoning_level` | Standard-Modell/Denkstufe für Aufträge dieses Projekts | passend zur typischen Komplexität wählen |
| `git_policy.allow_push` / `allow_merge` / `allow_force_push` | grobe Git-Rechte auf Projektebene | `allow_force_push: false` **immer**, projektübergreifende Konvention dieses gesamten Systems |
| `git_policy.protected_branches` | Branches, die zusätzlich geschützt sind | mindestens `default_branch` eintragen |
| `test_policy.command` / `required` | wie Tests für dieses Projekt laufen | `required: true`, wenn Aufträge ohne grüne Tests nicht als `COMPLETED` gelten sollen |
| `handover_policy.branch` / `require_clean` | Übergabe-Gate-Vorgaben (analog `docs/handover/HANDOVER.md` für CCB selbst) | `require_clean: true` empfohlen |
| `executor` | `codex` / `claude-code` / `null` | `null`, wenn (noch) nicht automatisiert |
| `controller` | `anthropic` / `openai` / `human` / `null` | i. d. R. `human`, außer bei API-gesteuerten Steuerprozessen |
| `review_roles.lead` / `support` | fachliche Führungs-/Prüfrolle, getrennt von `executor`/`controller` | optional, nur setzen, wenn eine feste Cross-Check-Rolle gewünscht ist |
| `github_repo` | vollqualifizierter `Besitzer/Repo`-Slug | nötig für Steuerprozesse ohne lokalen Checkout (z. B. ChatGPT über GitHub-Connector) |
| `migration_policy.allow_production` | Produktionsmigrationen erlaubt? | `false`, außer ausdrücklich anders entschieden |

**Referenzbeispiel, schreibend** (`projects/codex-control-bridge/project.yaml`,
real aktiv):
```yaml
schema_version: "1.0"
kind: bridge_project_profile
project_id: codex-control-bridge
description: Die Bridge selbst (Entwicklungsprojekt).
repository: Codex-Control-Bridge
default_branch: main
task_prefix: BRIDGE
read_only: false
executor: claude-code
controller: human
github_repo: zippeliniot/Codex-Control-Bridge
allowed_machines: [HAM11, DES11]
git_policy:
  allow_push: true
  allow_merge: false
  allow_force_push: false
  protected_branches: [main]
test_policy:
  command: "python -m unittest discover -s tests"
  required: true
handover_policy:
  branch: main
  require_clean: true
migration_policy:
  allow_production: false
```

**Referenzbeispiel, nur lesend** (`projects/examples/dorfschaft.project.yaml`,
Vorlage, nicht aktiv):
```yaml
schema_version: "1.0"
kind: bridge_project_profile
project_id: dorfschaft
description: Referenzprojekt Dorfschaft - erste Integration ausschließlich lesend.
repository: Dorfschaft
default_branch: main
task_prefix: DORF
read_only: true
executor: null
controller: null
allowed_machines: [HAM11, DES11]
git_policy:
  allow_push: false
  allow_merge: false
  allow_force_push: false
  protected_branches: [main]
test_policy:
  command: null
  required: false
handover_policy:
  branch: main
  require_clean: true
migration_policy:
  allow_production: false
```

## Schritt 4 — Entscheidung: `read_only: true` oder `false`

Das ist die wichtigste Weichenstellung, weil sie **tatsächlich im Code
erzwungen wird** (anders als die `task_prefix`-Kollision):

- **`read_only: true`:** `src/bridge/adapter.py` → `ReadOnlyAdapter`
  lehnt bei Initialisierung hart ab, wenn `profile.get("read_only")
  is not True` — der Adapter funktioniert dann grundsätzlich nicht.
  Erlaubt sind ausschließlich Git-Lesebefehle aus der Allowlist
  `schemas/git-readonly-allowlist.yaml` (SSOT), alles andere wird
  fail-closed verweigert. Für ein Projekt, das die Bridge nur
  **beobachten**, nie verändern soll (wie ursprünglich für Dorfschaft
  gedacht — dort zusätzlich durch CLAUDE.md Regel 3 auf CCB-Seite
  verstärkt).
- **`read_only: false`:** Die Bridge darf für dieses Projekt Aufträge
  im vollen Lebenszyklus ausführen (analog zu sich selbst). Es gibt
  **keinen** eigenen, generischen "Schreib-Adapter" — die normalen
  Store-/Runner-/CLI-Mechanismen (Teil 3 der `CCB-STEUERCHAT-REFERENZ.md`)
  gelten direkt, mit den Grenzen aus `git_policy` des Profils.

## Schritt 5 — Profil validieren

**WO: PowerShell:**
```powershell
.venv\Scripts\python.exe src\bridge\cli.py --root . --schema-dir schemas project validate projects/<project_id>/project.yaml
.venv\Scripts\python.exe src\bridge\cli.py --root . --schema-dir schemas project list
.venv\Scripts\python.exe src\bridge\cli.py --root . --schema-dir schemas project show <project_id>
```
`project list` zeigt `project_id`, `read_only`, `task_prefix` aller
bekannten Profile — das ist der Schritt, an dem manuell auf
`task_prefix`-Kollisionen geprüft wird (siehe Schritt 1).

## Schritt 6 — Falls schreibend: eigenes `CLAUDE.md`-Äquivalent überlegen

Die harten Regeln, die Claude Code für CCB selbst einhält (`CLAUDE.md`,
u. a. „nur innerhalb des Repos arbeiten", „Fail-closed bei
Unsicherheit"), sind **spezifisch für das CCB-Repo geschrieben** — sie
gelten nicht automatisch für ein neu eingebundenes Projekt. Für ein
schreibendes, automatisiertes Projekt (`executor: claude-code` oder
`codex`) empfiehlt sich ein analoges Regelwerk **im Zielrepo selbst**
(eigenes `CLAUDE.md` oder Äquivalent dort), nicht nur das
Projektprofil in CCB — das Profil steuert nur, *ob* die Bridge das
Projekt anfassen darf, nicht *wie* der Executor sich im Zielrepo
verhält.

---

## Zusammenfassung — was die Bridge automatisch erzwingt vs. was manuell sichergestellt werden muss

| Aspekt | Automatisch erzwungen? | Wo im Code |
|---|---|---|
| `read_only: true` → nur Lese-Allowlist | **Ja**, hart | `adapter.py` `ReadOnlyAdapter` |
| Schema-Konformität des Profils (`additionalProperties: false`) | **Ja**, fail-closed | `profiles.py`/`project.schema.yaml` |
| `project_id` = Verzeichnisname | **Ja** | `profiles.py` (`ProfileError` sonst) |
| `task_prefix`-Eindeutigkeit über mehrere Projekte | **Nein** — Kommentar in `profiles.py` bestätigt es explizit | manuell via `project list` prüfen |
| `allowed_machines`-Durchsetzung zur Laufzeit | **Nein** — kein Treffer in `store.py`/`runner.py` | reines Dokumentationsfeld |
| `git_policy`/`migration_policy` als Laufzeitsperre | **Nein** — kein Treffer in `store.py`/`runner.py` | reines Dokumentationsfeld |

**Konkrete Konsequenz:** `allowed_machines`, `git_policy` und
`migration_policy` sind aktuell **reine Absichtserklärungen im Profil**,
keine technischen Schranken — anders als `read_only`, das hart im
`ReadOnlyAdapter` erzwungen wird. Wer ein schreibendes Projekt einbindet
und sich auf `allow_force_push: false` oder `allowed_machines` als
echten Schutz verlassen will, braucht dafür (Stand heute) zusätzlich
eine der beiden bereits bewährten Mechaniken aus BRIDGE-024/025
(`gitops.py`-Whitelist + Branch-Check) oder ein eigenes `CLAUDE.md`-
Äquivalent im Zielrepo (Schritt 6) — das Profilfeld allein schützt noch
nichts.
