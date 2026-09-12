# BRIDGE-029 — Git-Push-Retry (pull --rebase) für den geteilten Store

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0029 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| review_roles | lead: anthropic, support: openai (aus Projektprofil übernommen) |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM — begrenzte, klar abgegrenzte Erweiterung eines bereits bestehenden, gut getesteten Moduls (`gitops.py`), kein neues Sicherheitsmodell. |

> **Verbindlich für diesen und jeden CCB-Auftrag:**
> - Jede Zustandsänderung läuft über die Bridge-CLI, kein direktes Bearbeiten
>   von Store-Dateien.
> - `GIT_PUSH` steht im Profil — nach `run finish` **muss** gepusht werden,
>   idealerweise über `--commit` (BRIDGE-025), und **sofort**, nicht gesammelt.

## Kontext

Umsetzt die in `docs/CCB-ORCHESTRATOR-KONZEPT.md` (Frage 3, BRIDGE-0027
dokumentiert) beschriebene Folgeentscheidung: Der CCB-Store
(`audit/audit.jsonl` u. a.) ist projektübergreifend gemeinsam in **einem**
Repo. Bei gleichzeitigen Commits aus mehreren Projekten/Maschinen kann
`git push` an Non-Fast-Forward scheitern. Lösung: automatisches
`git pull --rebase` + Retry bei Push-Fehlschlag — nie `--force`.

**Vor der Spezifikation gegen den echten Code geprüft**
(`src/bridge/gitops.py`, Verifikationspflicht Nr. 3):

1. `git_commit()` macht aktuell genau **einen** `git push`-Versuch
   (Schritt 6). Schlägt er fehl, bleibt der Commit lokal, Fehlertext geht
   unverändert in die Antwort (`{"committed": True, "pushed": False,
   "error": "..."}`)  — **kein** automatischer Ausgleichsversuch,
   unabhängig von der Fehlerursache.
2. Zwei verschiedene Fehlerursachen müssen unterschieden werden, sonst
   wird sinnlos wiederholt: **Non-Fast-Forward** (jemand anderes hat
   zwischenzeitlich gepusht — genau der Fall, den BRIDGE-0029 lösen soll)
   vs. **alle anderen Fehler** (kein Remote erreichbar, Auth-Problem,
   falscher Branch — dort hilft `pull --rebase` nichts, ein Retry wäre
   sinnlose Verzögerung). Git meldet Non-Fast-Forward über `stderr`
   typischerweise mit `rejected` und `non-fast-forward` bzw.
   `fetch first` — das ist die einzige verlässliche Unterscheidung ohne
   Rätselraten (kein separates Git-Kommando dafür vorhanden).
3. Es gibt bereits eine Testinfrastruktur für **echte** Non-Fast-Forward-
   Situationen: `tests/test_webui.py`, `WebUiGitActionTests`, nutzt ein
   temporäres lokales *bare*-Repo als `origin` (`_setup_git_repo` +
   `bare_tmp`) und einen bestehenden Test
   (`test_push_failure_commit_stays_local`) mit einem divergierten
   bare-Repo. Diese Infrastruktur **wiederverwenden**, nicht neu bauen.
4. `git_commit()` wird von genau zwei Stellen aufgerufen: `cli.py`
   (`push=False`, CLI pusht nie automatisch) und `webui.py` (`push=True`,
   immer). Die Retry-Logik betrifft ausschließlich den `push=True`-Pfad
   — beim CLI-Pfad (`push=False`) gibt es gar keinen Push-Versuch, also
   auch nichts zu wiederholen.
5. Kein Antwort-Schema für das Rückgabe-`dict` von `git_commit()`
   vorhanden (nur zwei interne Aufrufer, keine JSON-Schema-Validierung
   der Antwort) — ein zusätzliches Feld (z. B. `retried: bool`) in der
   Rückgabe ist gefahrlos additiv möglich, bricht nichts Bestehendes.

**Bewusst zu begrenzende Annahme (bitte vor Umsetzung kurz bestätigen oder
korrigieren):** genau **ein** Retry-Versuch (zwei Push-Versuche insgesamt),
kein Backoff, keine Schleife — passend zum Konzept-Text „Retry" (Singular),
und weil ein Single-User-Setup mit zwei Maschinen keine Dauerkollisionen
erwarten lässt. Bei einem zweiten Fehlschlag: Fehler wie bisher zurückgeben,
Commit bleibt lokal, kein drittes/viertes Mal versuchen.

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0029.yaml
   bridge run start BRIDGE-0029 --actor claude-code
   ```

2. **`src/bridge/gitops.py` erweitern**, Schritt 6 (`git push`) in
   `git_commit()`:
   - Push-Versuch wie bisher.
   - Bei Fehlschlag: `stderr`/`stdout` auf Non-Fast-Forward-Muster prüfen
     (`rejected`, `non-fast-forward`, `fetch first` — als Konstante/Liste
     definieren, nicht magisch im Fließtext verstecken).
   - **Kein** Muster erkannt (anderer Fehlertyp) → wie bisher sofort
     zurückgeben, kein Retry.
   - Muster erkannt → `git fetch origin` + `git rebase origin/<branch>`
     (Branch ist zu diesem Zeitpunkt bereits als `main` verifiziert,
     Schritt 1 der Funktion).
     - Rebase erfolgreich → **einen** weiteren `git push`-Versuch.
       Erfolgreich → `{"committed": True, "commit": ..., "pushed": True,
       "error": None, "retried": True}`. Erneut fehlgeschlagen → Fehler
       zurückgeben wie bisher, zusätzlich `"retried": True`, Commit bleibt
       lokal (kein zweiter Retry).
     - Rebase schlägt fehl (Konflikt) → **sofort** `git rebase --abort`,
       fail-closed, Fehler zurückgeben (`"retried": True`, `"pushed":
       False`), Repository-Zustand muss danach sauber/unrebased sein wie
       vor dem Versuch — kein hängender Rebase-Zustand.
   - `--force`/`--force-with-lease` bleiben weiterhin an keiner Stelle
     im Modul vorhanden (bestehender Test `NoForcePushTests` muss grün
     bleiben, keine neue Ausnahme einführen).
   - Rückwärtskompatibel: bestehende Rückgabefelder (`committed`,
     `commit`, `pushed`, `error`) unverändert, `retried` ist neu und
     optional für Aufrufer (Default-Verhalten ohne Retry-Fall:
     `retried: False`).

3. Tests (`tests/test_gitops.py`, neue Fälle, echtes bare-Repo statt
   Mocks — Muster aus `WebUiGitActionTests`/`test_webui.py`
   wiederverwenden, nicht duplizieren, ggf. gemeinsamen Test-Helfer
   extrahieren, wenn das ohne großen Umbau möglich ist):
   - Divergiertes bare-Repo (ein anderer Klon hat zwischenzeitlich
     gepusht) → `git_commit(push=True)` erkennt Non-Fast-Forward, macht
     `pull --rebase`, zweiter Push-Versuch **erfolgreich**, Ergebnis
     `pushed: True, retried: True`, fremder Commit UND eigener Commit
     beide im Remote-Verlauf vorhanden (nichts überschrieben).
   - Rebase-Konflikt (divergierte, **inhaltlich widersprüchliche**
     Änderung an derselben Datei) → fail-closed: `pushed: False`, Commit
     bleibt lokal, kein Force-Push, Repo danach nicht in einem
     hängenden Rebase-Zustand (`git status` zeigt „nichts zu
     committen"/sauberen Zustand nach `rebase --abort`, nicht
     „rebase in progress").
   - Anderer Fehlertyp (nicht erreichbarer Remote, wie im bestehenden
     `test_push_failure_commit_stays_local`) → **kein** Retry-Versuch,
     Verhalten unverändert zum bisherigen Test.
   - Zweiter Push-Versuch scheitert ebenfalls (z. B. erneute
     Zwischenkollision) → kein dritter Versuch, Fehler wie gehabt,
     `retried: True`.
   - `NoForcePushTests` (bestehend) bleibt unverändert grün.
   - Bestehende Tests aus `test_gitops.py` und `test_webui.py`
     (`WebUiGitActionTests`) weiterhin grün.

4. `docs/security/SECURITY-MODEL.md` Abschnitt 5c (CLI: `--commit`-Flag
   und `base_head`-Fail-closed, BRIDGE-025) um einen neuen Absatz zum
   Retry-Verhalten ergänzen — dort ist `gitops.py` bereits dokumentiert,
   diese Erweiterung gehört an dieselbe Stelle, nicht in einen neuen
   Abschnitt. Explizit festhalten: Retry gilt nur für Non-Fast-Forward,
   maximal ein Versuch, kein Force-Push, Rebase-Konflikt ist fail-closed.

5. `docs/CCB-STEUERCHAT-REFERENZ.md` Teil 4 (Web-UI-Referenz, Abschnitt
   zu Git-Commit/Push nach Aktionen) um einen kurzen Hinweis auf das
   Retry-Verhalten ergänzen.

6. Pflicht-Footer + Abschluss, `--commit` nutzen, **sofort pushen**:
   ```
   bridge run finish BRIDGE-0029 --status COMPLETED --actor claude-code \
     --commit \
     --summary "git_commit() in gitops.py erkennt Non-Fast-Forward-Push-Fehler (rejected/non-fast-forward/fetch first in stderr) und macht genau einen Ausgleichsversuch (git fetch + git rebase origin/main, dann erneuter Push). Rebase-Konflikt ist fail-closed (rebase --abort, Commit bleibt lokal, kein Force-Push). Andere Fehlertypen (kein Remote, Auth) loesen weiterhin keinen Retry aus. Neues optionales Rueckgabefeld 'retried' in git_commit(), rueckwaertskompatibel. Betrifft nur den push=True-Pfad (Web-UI); CLI-Pfad (push=False) unveraendert."
   git push
   ```
   `Auftrag: BRIDGE-0029 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [ ] `git_commit()` erkennt Non-Fast-Forward-Push-Fehler anhand von
      `stderr`/`stdout`-Mustern (`rejected`, `non-fast-forward`,
      `fetch first`), andere Fehlertypen lösen **keinen** Retry aus.
- [ ] Bei erkanntem Non-Fast-Forward: `git fetch` + `git rebase
      origin/<branch>`, danach genau **ein** weiterer Push-Versuch.
- [ ] Rebase-Konflikt: `git rebase --abort`, fail-closed, Commit bleibt
      lokal, Repo danach in sauberem (nicht hängendem) Zustand.
- [ ] Kein Force-Push an keiner Stelle (bestehender `NoForcePushTests`
      bleibt grün).
- [ ] Maximal ein Retry-Versuch — scheitert der zweite Push ebenfalls,
      kein dritter Versuch.
- [ ] Neues Rückgabefeld `retried` (bool), rückwärtskompatibel, bestehende
      Felder unverändert.
- [ ] Test mit echtem divergiertem bare-Repo: Retry erfolgreich, beide
      Commits (fremd + eigen) im Remote-Verlauf.
- [ ] Test mit echtem Rebase-Konflikt: fail-closed, sauberer Zustand
      danach.
- [ ] Bestehender Non-Retry-Fehlerfall (`test_push_failure_commit_stays_local`)
      weiterhin unverändert grün.
- [ ] `SECURITY-MODEL.md` Abschnitt 5c und `CCB-STEUERCHAT-REFERENZ.md`
      Teil 4 aktualisiert.
- [ ] Bestehende Tests weiterhin grün, neue Tests grün, frischer Klon
      verifiziert.
- [ ] Jeder Commit sofort gepusht, nicht gesammelt.
