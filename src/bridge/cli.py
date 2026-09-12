"""Einheitliche Kommandozeile über der Bridge-Engine (BRIDGE-006).

Reine stdlib. Wiederverwendung von src/bridge/store.py und
src/bridge/state_machine.py - die Engine wird genutzt, nicht dupliziert.
Exit-Codes: 0 = OK, 1 = Fachfehler/fail-closed, 2 = Nutzungsfehler,
            3 = Git-Whitelist- oder Branch-Fehler bei --commit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# src-Layout: direkter Skriptaufruf (python src/bridge/cli.py ...) braucht das
# Paketverzeichnis auf dem Importpfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import gitops, heartbeat, importer, profiles, registry, runner, state_machine, watcher
from bridge.store import Store, StoreError

_ENGINE_ERRORS = (StoreError, state_machine.TransitionError, state_machine.ModelError,
                  importer.ImporterError)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridge", description="Codex Control Bridge CLI")
    parser.add_argument("--root", default=".",
                        help="Basis für tasks/results/audit (Standard: aktuelles Verzeichnis)")
    parser.add_argument("--schema-dir", default=None,
                        help="Schema-Verzeichnis (Standard: <root>/schemas)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("validate", help="Task/Result gegen Schema prüfen")
    sp.add_argument("path")

    task = sub.add_parser("task", help="Aufträge verwalten")
    tsub = task.add_subparsers(dest="task_cmd", required=True)
    tcreate = tsub.add_parser("create", help="Auftrag anlegen")
    tcreate.add_argument("path")
    tcreate.add_argument("--commit", action="store_true",
                         help="nach erfolgreichem Anlegen lokal committen (kein Push, Exit 3 bei Fehler)")
    tsub.add_parser("show", help="Status + Kernfelder").add_argument("task_id")
    tsub.add_parser("list", help="alle Aufträge mit Status")
    tcopied = tsub.add_parser(
        "copied", help="Ergebnis wurde in den Steuerchat kopiert (-> REVIEW_REQUIRED)")
    tcopied.add_argument("task_id")
    tcopied.add_argument("--actor", required=True)
    tcopied.add_argument("--commit", action="store_true",
                         help="nach erfolgreichem Uebergang lokal committen (kein Push, Exit 3 bei Fehler)")
    tarchive = tsub.add_parser(
        "archive", help="Auftrag abschliessen (-> ARCHIVED)")
    tarchive.add_argument("task_id")
    tarchive.add_argument("--actor", required=True)
    tarchive.add_argument("--reason", default=None)
    tarchive.add_argument("--commit", action="store_true",
                          help="nach erfolgreichem Uebergang lokal committen (kein Push, Exit 3 bei Fehler)")
    tset = tsub.add_parser("set-status", help="Zustandswechsel")
    tset.add_argument("task_id")
    tset.add_argument("new_state")
    tset.add_argument("--actor", required=True)
    tset.add_argument("--machine")
    tset.add_argument("--reason")
    tprio = tsub.add_parser("set-priority",
                            help="Prioritaet setzen (LOW/MEDIUM/HIGH, BRIDGE-028)")
    tprio.add_argument("task_id")
    tprio.add_argument("priority", choices=["LOW", "MEDIUM", "HIGH"])
    tprio.add_argument("--actor", required=True)
    tprio.add_argument("--machine")

    result = sub.add_parser("result", help="Ergebnisse verwalten")
    rsub = result.add_subparsers(dest="result_cmd", required=True)
    rsub.add_parser("write", help="Ergebnis ablegen").add_argument("path")

    imp = rsub.add_parser("import",
                          help="Ergebnis aus dem Executor-Kontext übernehmen")
    imp.add_argument("task_id")
    imp.add_argument("--status", help="Ausgang des Laufs (oder aus dem Entwurf)")
    imp.add_argument("--from", dest="draft_path", help="Entwurf (draft.yaml)")
    imp.add_argument("--base-head", help="HEAD-SHA zu Laufbeginn")
    imp.add_argument("--run-id", help="RUN-YY (Standard: next_run_id)")
    imp.add_argument("--executor", default="claude-code")
    imp.add_argument("--machine")
    imp.add_argument("--environment")
    imp.add_argument("--runtime")
    imp.add_argument("--summary")
    imp.add_argument("--started-at")

    sub.add_parser("next-run", help="nächste Lauf-ID").add_argument("task_id")

    audit = sub.add_parser("audit", help="Auditspur")
    asub = audit.add_subparsers(dest="audit_cmd", required=True)
    asub.add_parser("show", help="Auditspur ausgeben").add_argument("task_id", nargs="?")

    sub.add_parser("resume", help="Wiederaufsetz-Hilfe (rein lesend)").add_argument("task_id")

    soverview = sub.add_parser(
        "overview",
        help="Gesamtuebersicht: alle Auftraege, alle Zustaende, mit letzter Maschine (rein lesend)")
    soverview.add_argument("--project", default=None,
                           help="Nur Auftraege dieses Projekts anzeigen (project_id)")

    sboard = sub.add_parser(
        "board", help="Copy-Paste-Board: welcher Auftrag wartet auf Kopie (rein lesend)")
    sboard.add_argument("--machine", help="Maschinenname ueberschreiben (Standard: COMPUTERNAME)")
    sboard.add_argument("--watch", action="store_true",
                        help="dauerhaft laufen und sich selbst aktualisieren (bis Ctrl+C)")
    sboard.add_argument("--interval", type=float, default=15.0,
                        help="Sekunden zwischen den Aktualisierungen (nur mit --watch, Standard: 15.0)")
    sboard.add_argument("--max-iterations", type=int, default=None,
                        help=argparse.SUPPRESS)

    scmd = sub.add_parser(
        "commands", help="Befehlsreferenz mit aufgeloestem lokalem Pfad (rein lesend)")
    scmd.add_argument("--machine", help="Maschinenname ueberschreiben (Standard: COMPUTERNAME)")
    scmd.add_argument("--project", default="codex-control-bridge",
                      help="Projekt-ID fuer den aufgeloesten Pfad (Standard: codex-control-bridge)")

    webui = sub.add_parser(
        "webui", help="lokale Lese-Web-UI ueber dem Board (nur 127.0.0.1, rein lesend)")
    websub = webui.add_subparsers(dest="webui_cmd", required=True)
    wserve = websub.add_parser(
        "serve", help="Web-UI starten (bindet hart an 127.0.0.1, kein --host)")
    wserve.add_argument("--actor", required=True,
                        help="Akteur fuer spaetere Aktions-Buttons (RUN-02); jetzt nur hinterlegt")
    wserve.add_argument("--port", type=int, default=8420,
                        help="Port (Standard: 8420; belegt -> klare Fehlermeldung, kein Ausweichen)")

    watch = sub.add_parser(
        "watch", help="Watcher: Ergebnisse/Heartbeats erkennen und weiterführen")
    wsub = watch.add_subparsers(dest="watch_cmd", required=True)

    wscan = wsub.add_parser("scan", help="einmalig prüfen (Trockenlauf ohne --apply)")
    wscan.add_argument("--apply", action="store_true",
                       help="erlaubte Übergänge über die Engine setzen")
    wscan.add_argument("--actor", help="verantwortlich für den Wechsel (Pflicht bei --apply)")
    wscan.add_argument("--machine")
    wscan.add_argument("--task", help="nur diesen Auftrag prüfen")

    wloop = wsub.add_parser("loop", help="wiederholt prüfen (bis Ctrl+C)")
    wloop.add_argument("--interval", type=float, required=True,
                       help="Sekunden zwischen den Durchläufen")
    wloop.add_argument("--apply", action="store_true")
    wloop.add_argument("--actor")
    wloop.add_argument("--machine")
    wloop.add_argument("--max-iterations", type=int, default=None,
                       help=argparse.SUPPRESS)

    whb = wsub.add_parser("heartbeat",
                          help="Heartbeat eines Laufs schreiben/aktualisieren")
    whb.add_argument("task_id")
    whb.add_argument("run_id")
    whb.add_argument("--actor")
    whb.add_argument("--machine")

    run = sub.add_parser("run", help="Lauf-Lebenszyklus: start/beat/finish/resume")
    runsub = run.add_subparsers(dest="run_cmd", required=True)

    rstart = runsub.add_parser("start", help="Lauf starten (-> RUNNING, initialer Heartbeat)")
    rstart.add_argument("task_id")
    rstart.add_argument("--actor", required=True)
    rstart.add_argument("--machine")
    rstart.add_argument("--commit", action="store_true",
                        help="nach erfolgreichem Start lokal committen (kein Push, Exit 3 bei Fehler)")

    rbeat = runsub.add_parser("beat", help="Heartbeat des aktuellen Laufs aktualisieren")
    rbeat.add_argument("task_id")
    rbeat.add_argument("--actor", required=True)
    rbeat.add_argument("--machine")

    rfin = runsub.add_parser("finish",
                             help="Lauf abschließen (Ergebnis-Import + Zustandswechsel)")
    rfin.add_argument("task_id")
    rfin.add_argument("--status", required=True)
    rfin.add_argument("--from", dest="draft_path", help="Entwurf (draft.yaml)")
    rfin.add_argument("--base-head",
                      help="HEAD-SHA zu Laufbeginn; fehlt er, wird git.expected_head "
                           "aus task.yaml abgeleitet (fail-closed wenn auch das fehlt)")
    rfin.add_argument("--actor", required=True)
    rfin.add_argument("--machine")
    rfin.add_argument("--summary")
    rfin.add_argument("--commit", action="store_true",
                      help="nach erfolgreichem Abschluss lokal committen (kein Push, Exit 3 bei Fehler)")

    rres = runsub.add_parser("resume", help="Lauf wiederaufnehmen (-> RUNNING, neuer RUN)")
    rres.add_argument("task_id")
    rres.add_argument("--actor", required=True)
    rres.add_argument("--machine")

    project = sub.add_parser("project", help="Projektprofile (Adapter)")
    psub = project.add_subparsers(dest="project_cmd", required=True)
    psub.add_parser("list", help="bekannte Projekte (project_id + read_only + task_prefix)")
    psub.add_parser("show", help="Kernfelder eines Profils").add_argument("project_id")
    psub.add_parser("validate", help="Profil gegen Schema prüfen").add_argument("path")
    return parser


# --------------------------------------------------------------------------- #
# Helfer fuer --commit (BRIDGE-025)
# --------------------------------------------------------------------------- #

def _do_commit(args, store, kind: str, task_id: str, actor: str,
               run_id: str | None = None) -> int:
    """Fuehrt nach einer erfolgreichen Store-Aktion einen lokalen Commit aus.

    Rueckgabe: 0 bei Erfolg, 3 bei Git-Whitelist- oder Branch-Fehler.
    Kein Push (push=False) - Push bleibt Mensch-/GIT_PUSH-Sache.
    """
    git = gitops.git_commit(store.root, kind, task_id, actor,
                            run_id=run_id, push=False, source="CLI")
    if git["error"]:
        print(f"Git-Fehler (--commit): {git['error']}", file=sys.stderr)
        print("Store-Aktion war erfolgreich; nur der Commit schlug fehl.", file=sys.stderr)
        return 3
    sha = git.get("commit") or "(unbekannt)"
    print(f"  -> Commit {sha} (lokal, kein Push)")
    return 0


# --------------------------------------------------------------------------- #
# Kommandos
# --------------------------------------------------------------------------- #

def _cmd_validate(args, store) -> int:
    doc = store.validate(args.path)
    print(f"OK: {doc.get('kind')} gültig ({args.path})")
    return 0


def task_copied(store, task_id, actor):
    """'Ergebnis wurde in den Steuerchat kopiert' -> REVIEW_REQUIRED.

    Gemeinsame Logik fuer ``bridge task copied`` und den Web-Endpunkt - kein
    Parallel-Code. Fail-closed: nur aus WAITING_FOR_COPY_TO_CONTROL zulaessig
    (die allgemeine Uebergangstabelle allein wuerde auch RUNNING durchlassen).
    """
    current = store.load_task(task_id).get("status")
    if current != "WAITING_FOR_COPY_TO_CONTROL":
        raise StoreError(
            f"{task_id}: 'copied' nur aus WAITING_FOR_COPY_TO_CONTROL "
            f"zulässig (aktueller Zustand: {current}).")
    return store.set_status(task_id, "REVIEW_REQUIRED", actor, None,
                            reason="Ergebnis in Steuerchat kopiert")


def task_set_priority(store, task_id, priority, actor, machine=None):
    """Setzt die Prioritaet eines Auftrags. Gemeinsame Logik fuer
    ``bridge task set-priority`` und den Web-Endpunkt.

    Ruft ``store.set_priority`` auf (BRIDGE-028). Fail-closed bei ungueltiger
    Prioritaet (StoreError) — kein stilles Ignorieren.
    """
    return store.set_priority(task_id, priority, actor, machine)


def task_archive(store, task_id, actor, reason=None):
    """'Dieser Auftrag ist erledigt' -> ARCHIVED. Gemeinsame Logik fuer
    ``bridge task archive`` und den Web-Endpunkt.

    Bewusst OHNE Ausgangszustands-Check: aus welchen Zustaenden ARCHIVED
    erreichbar ist, regelt schemas/state-model.yaml bereits fail-closed
    (z. B. nicht direkt aus RUNNING).
    """
    return store.set_status(task_id, "ARCHIVED", actor, None,
                            reason=reason or "Auftrag abgeschlossen")


def _cmd_task(args, store) -> int:
    if args.task_cmd == "create":
        doc = store.create_task(args.path)
        task_id = doc["bridge_task_id"]
        actor = doc.get("created_by", "unknown")
        # Auto-Chain: frisch angelegter Auftrag wird sofort board-sichtbar,
        # ohne dass der Nutzer zusätzliche Befehle tippen muss (BRIDGE-014).
        store.set_status(task_id, "READY", actor, None,
                         reason="auto: Auftrag angelegt")
        event = store.set_status(task_id, "WAITING_FOR_HANDOFF_TO_EXECUTOR",
                                 actor, None,
                                 reason="auto: wartet auf Weitergabe an Executor")
        print(f"OK: {task_id} angelegt (status={event['new_state']})")
        if getattr(args, "commit", False):
            rc = _do_commit(args, store, "task_create", task_id, actor)
            if rc != 0:
                return rc
        return 0
    if args.task_cmd == "show":
        task = store.load_task(args.task_id)
        for key in ("bridge_task_id", "title", "task_class", "status",
                    "branch", "created_by", "depends_on"):
            if key in task:
                print(f"{key}: {task[key]}")
        return 0
    if args.task_cmd == "list":
        rows = _list_tasks(store)
        if not rows:
            print("(keine Aufträge)")
        for task_id, status in rows:
            print(f"{task_id}\t{status}")
        return 0
    if args.task_cmd == "copied":
        event = task_copied(store, args.task_id, args.actor)
        print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']} "
              f"({event['event_type']})")
        if getattr(args, "commit", False):
            rc = _do_commit(args, store, "task_copied", args.task_id, args.actor)
            if rc != 0:
                return rc
        return 0
    if args.task_cmd == "archive":
        event = task_archive(store, args.task_id, args.actor, args.reason)
        print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']} "
              f"({event['event_type']})")
        if getattr(args, "commit", False):
            rc = _do_commit(args, store, "task_archive", args.task_id, args.actor)
            if rc != 0:
                return rc
        return 0
    if args.task_cmd == "set-status":
        event = store.set_status(args.task_id, args.new_state, actor=args.actor,
                                 machine=args.machine, reason=args.reason)
        print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']} "
              f"({event['event_type']})")
        return 0
    if args.task_cmd == "set-priority":
        event = task_set_priority(store, args.task_id, args.priority,
                                  args.actor, getattr(args, "machine", None))
        print(f"OK: {args.task_id} Prioritaet gesetzt: {event['reason']} "
              f"({event['event_type']})")
        return 0
    return 2  # vom Parser ausgeschlossen


def _cmd_result(args, store) -> int:
    if args.result_cmd == "import":
        return _cmd_result_import(args, store)
    doc = store.write_result(args.path)  # result_cmd == "write"
    print(f"OK: Ergebnis {doc['bridge_task_id']} {doc['run_id']} abgelegt")
    return 0


def _cmd_result_import(args, store) -> int:
    draft = importer.load_draft(args.draft_path) if args.draft_path else {}
    status = args.status or draft.get("status")
    if not status:
        print("Nutzungsfehler: --status fehlt (weder Flag noch Entwurf).",
              file=sys.stderr)
        return 2
    # base_head-Fallback: gleiche Logik wie run finish (BRIDGE-025).
    base_head = args.base_head
    if base_head is None:
        task = store.load_task(args.task_id)
        base_head = (task.get("git") or {}).get("expected_head")
        if base_head is None:
            print(
                f"Fehler: --base-head fehlt und git.expected_head ist nicht in "
                f"task.yaml von {args.task_id} gesetzt. "
                f"Bitte --base-head <SHA> explizit angeben (fail-closed).",
                file=sys.stderr,
            )
            return 1
    result = importer.import_result(
        store, args.task_id, status,
        run_id=args.run_id, draft=draft, base_head=base_head,
        executor=args.executor, machine=args.machine,
        environment=args.environment, runtime=args.runtime,
        summary=args.summary, started_at=args.started_at,
    )
    path = (store.results_dir / result["bridge_task_id"]
            / result["run_id"] / "result.yaml")
    print(str(path))
    return 0


def _cmd_next_run(args, store) -> int:
    print(store.next_run_id(args.task_id))
    return 0


def _cmd_audit(args, store) -> int:
    path = store.audit_file
    if not path.exists():
        print("(keine Auditspur)")
        return 0
    wanted = args.task_id
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if wanted and event.get("bridge_task_id") != wanted:
            continue
        print(line)
    return 0


def _cmd_resume(args, store) -> int:
    task_id = args.task_id
    task = store.load_task(task_id)
    print(f"Auftrag:         {task_id}")
    print(f"Status:          {task.get('status')}")
    print(f"Naechste Lauf-ID: {store.next_run_id(task_id)}")

    wp_path = store.root / "work-packages" / f"{task_id}.md"
    if not wp_path.is_file():
        print(f"Arbeitspaket:    nicht gefunden ({wp_path})")
    else:
        open_items, done = [], 0
        for raw in wp_path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if stripped.startswith("- [ ]"):
                open_items.append(stripped[5:].strip())
            elif stripped[:5].lower() == "- [x]":
                done += 1
        print(f"Akzeptanzkriterien: {done} erledigt, {len(open_items)} offen")
        for item in open_items:
            print(f"  - [ ] {item}")

    commits = _recent_commits(store.root)
    if commits:
        print("Letzte Commits:")
        for commit in commits:
            print(f"  {commit}")
    return 0


_BOARD_STATES = ("WAITING_FOR_HANDOFF_TO_EXECUTOR", "WAITING_FOR_COPY_TO_CONTROL")
_BOARD_DIRECTION = {
    "WAITING_FOR_HANDOFF_TO_EXECUTOR": "Steuerchat -> Executor",
    "WAITING_FOR_COPY_TO_CONTROL": "Executor -> Steuerchat",
}

# --------------------------------------------------------------------------- #
# Prioritaets-Hilfsfunktionen (BRIDGE-028)
# --------------------------------------------------------------------------- #

# Rang fuer Sortierung: hoechste Prioritaet = niedrigster Rang (sortiert oben).
_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_PRIORITY_DEFAULT = "MEDIUM"


def _task_priority(task: dict) -> str:
    """Prioritaet eines Auftrags; Default MEDIUM wenn Feld fehlt (Altbestand)."""
    return task.get("priority") or _PRIORITY_DEFAULT


def _priority_rank(task: dict) -> int:
    """Sortierschluessel fuer Prioritaet (0=HIGH, 1=MEDIUM, 2=LOW)."""
    return _PRIORITY_RANK.get(_task_priority(task), 1)

# --------------------------------------------------------------------------- #
# Gemeinsame Konstanten fuer bridge overview (BRIDGE-026)
# --------------------------------------------------------------------------- #

# Schwelle fuer "inaktiver RUNNING-Auftrag": kein Heartbeat seit 30 Minuten.
# Begruendung: CLAUDE.md schreibt vor, dass der Runner an jedem Commit-Checkpoint
# einen Heartbeat schlaegt (Abschnitt "Heartbeat an Checkpoints"). Typische
# Claude-Code-Laeufe committen alle paar Minuten. 30 Minuten sind konservativ genug,
# echte Denkpausen nicht als Inaktivitaet zu werten, aber sensitiv genug,
# haengengebliebene Laeufe (Usage-Limit, Absturz) erkennbar zu machen.
_OVERVIEW_INACTIVE_THRESHOLD_MINUTES = 30

# Zustaende, die unabhaengig vom Heartbeat als "inaktiv/unterbrochen" gelten.
_OVERVIEW_INACTIVE_STATUSES = frozenset(("WAITING_FOR_RESUME", "INTERRUPTED"))


def _fmt_wait(delta_seconds) -> str:
    """Kurzformat der Wartezeit: "12m", "2h 14m", "1d 3h"."""
    minutes = max(0, int(delta_seconds // 60))
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def _board_project(store, task) -> str:
    """Projekt-Spalte: task_prefix aus dem Profil, Fail-soft auf project_id roh."""
    project_id = task.get("project_id", "")
    try:
        profile = profiles.load_profile(store.root, project_id,
                                        schema_dir=store.schema_dir)
    except (profiles.ProfileError, StoreError):
        return project_id or "?"
    return profile.get("task_prefix") or project_id or "?"


_ROLE_NAMES = {"anthropic": "Anthropic", "openai": "OpenAI", "human": "Human"}


def _fmt_review_roles(roles) -> str:
    """Board-Text der Fuehrungs-/Pruefrolle. ``None``/leer klar als solches erkennbar."""
    if not roles:
        return "(keine Rollentrennung)"
    lead, support = roles.get("lead"), roles.get("support")
    if lead is None and support is None:
        return "(keine Rollentrennung)"
    lead_txt = _ROLE_NAMES.get(lead, lead) if lead else "-"
    if support is None:
        return f"Lead: {lead_txt} (kein Support)"
    return f"Lead: {lead_txt} · Support: {_ROLE_NAMES.get(support, support)}"


def _board_review_roles(store, task) -> str:
    """Fuehrung/Pruefung-Spalte: aufgeloeste review_roles, Fail-soft auf "?"
    bei fehlendem/ungueltigem Profil (gleiches Muster wie ``_board_project``)."""
    project_id = task.get("project_id", "")
    try:
        profile = profiles.load_profile(store.root, project_id,
                                        schema_dir=store.schema_dir)
    except (profiles.ProfileError, StoreError):
        if task.get("review_roles") is not None:
            return _fmt_review_roles(profiles.resolve_review_roles({}, task))
        return "?"
    return _fmt_review_roles(profiles.resolve_review_roles(profile, task))


def _board_depends_note(store, task) -> str:
    notes = []
    for dep in task.get("depends_on", []) or []:
        try:
            dep_task = store.load_task(dep)
        except StoreError:
            continue  # Abhaengigkeit ausserhalb dieses Stores -> Fail-soft
        dep_status = dep_task.get("status")
        if dep_status != "ARCHIVED":
            notes.append(f"(depends_on {dep}, Status: {dep_status})")
    return "  ".join(notes)


def _board_rows(store, *, now=None):
    """Ermittelt die Board-Zeilen (reine Daten, keine Ausgabe).

    Rueckgabe: sortierte Liste von Tupeln
    ``(task_id, projekt, fuehrung, richtung, wartezeit, hinweis, prioritaet)``.
    Sortierung: (Prioritaets_Rang, bridge_task_id) — Prioritaet vor ID (BRIDGE-028).
    """
    now = now or datetime.now(timezone.utc)
    rows = []
    for task in _list_task_docs(store):
        status = task.get("status")
        if status not in _BOARD_STATES:
            continue
        task_id = task.get("bridge_task_id", "?")
        ts = store.last_transition_at(task_id, status)
        wait = "?"
        if ts:
            try:
                when = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc)
                wait = _fmt_wait((now - when).total_seconds())
            except ValueError:
                wait = "?"
        rows.append((
            task_id,
            _board_project(store, task),
            _board_review_roles(store, task),
            _BOARD_DIRECTION[status],
            wait,
            _board_depends_note(store, task),
            _task_priority(task),    # Prioritaet (BRIDGE-028)
            _priority_rank(task),    # Hilfsspalte fuer Sortierung
        ))
    rows.sort(key=lambda r: (r[7], r[0]))   # (Prioritaets_Rang, task_id)
    return [r[:7] for r in rows]             # Hilfsspalte entfernen


def _board_text(rows) -> str:
    """Baut aus den Board-Zeilen den Tabellentext (Einmal- und Watch-Modus)."""
    if not rows:
        return "(keine Auftraege warten auf Kopie)"
    lines = [f"{'#':<3}{'Prio':<7}{'Projekt':<13}{'Führung/Prüfung':<34}"
             f"{'Auftrag':<13}{'Richtung':<24}Wartet seit"]
    for i, (task_id, projekt, fuehrung, richtung, wait, note, prio) in enumerate(rows, start=1):
        line = f"{i:<3}{prio:<7}{projekt:<13}{fuehrung:<34}{task_id:<13}{richtung:<24}{wait}"
        if note:
            line = f"{line}  {note}"
        lines.append(line)
    return "\n".join(lines)


def _board_loop(store, *, interval, max_iterations=None, sleep=time.sleep, now=None):
    """Zeigt das Board wiederholt an - Muster wie ``watcher.loop()``.

    ``max_iterations`` und ``sleep`` sind nur fuer Tests gedacht (kein echtes
    Warten); ohne ``max_iterations`` laeuft die Schleife bis ``KeyboardInterrupt``.
    Kein Bildschirm-Loeschen: vor jeder Aktualisierung eine Trennzeile mit
    Zeitstempel.
    """
    count = 0
    while max_iterations is None or count < max_iterations:
        stamp = (now() if callable(now) else now) or datetime.now(timezone.utc)
        print(f"=== bridge board (Aktualisiert: "
              f"{stamp.strftime('%Y-%m-%dT%H:%M:%SZ')}) ===")
        print(_board_text(_board_rows(store, now=stamp)))
        count += 1
        if max_iterations is not None and count >= max_iterations:
            break
        sleep(interval)


def _cmd_board(args, store) -> int:
    if not getattr(args, "watch", False):
        print(_board_text(_board_rows(store)))
        return 0
    try:
        _board_loop(store, interval=args.interval,
                    max_iterations=getattr(args, "max_iterations", None),
                    sleep=time.sleep)
    except KeyboardInterrupt:
        print()  # sauberer Zeilenumbruch, kein Traceback
    return 0


# --------------------------------------------------------------------------- #
# bridge overview — Gesamtuebersicht aller Auftraege (BRIDGE-026)
# --------------------------------------------------------------------------- #

def _overview_audit_scan(store) -> dict:
    """Einmaliger Scan der Auditspur: pro task_id letzte machine + letzter timestamp.

    Gibt ``{task_id: {"machine": str|None, "timestamp": str|None}}`` zurueck.
    Einmal aufrufen und das Ergebnis weitergeben — nicht pro Auftrag einzeln.
    """
    result: dict = {}
    if not store.audit_file.exists():
        return result
    for line in store.audit_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = event.get("bridge_task_id")
        if not tid:
            continue
        entry = result.setdefault(tid, {"machine": None, "timestamp": None})
        if event.get("machine"):
            entry["machine"] = event["machine"]
        if event.get("timestamp"):
            entry["timestamp"] = event["timestamp"]
    return result


def _overview_task_info(store, task: dict, audit_info: dict,
                        now: datetime) -> "tuple[str, datetime | None, bool]":
    """Ermittelt (machine, last_activity, is_active) fuer einen Auftrag.

    Prioritaet Maschine:    Heartbeat des letzten Laufs > letzter Audit-Eintrag > '?'.
    Prioritaet Aktivitaet:  Heartbeat last_seen > letzter Audit-Timestamp > None.
    is_active:              True nur wenn RUNNING/CLAIMED und Heartbeat juenger als
                            _OVERVIEW_INACTIVE_THRESHOLD_MINUTES (oder kein HB = frisch).
    """
    task_id = task.get("bridge_task_id", "?")
    status = task.get("status")
    run_id = runner.current_run_id(store, task_id)

    hb: "dict | None" = None
    if run_id:
        try:
            hb = heartbeat.read_heartbeat(store.root, task_id, run_id)
        except heartbeat.HeartbeatError:
            hb = None

    # Maschine
    if hb and hb.get("machine"):
        machine = hb["machine"]
    elif audit_info.get("machine"):
        machine = audit_info["machine"]
    else:
        machine = "?"

    # Letzte Aktivitaet
    last_act: "datetime | None" = None
    if hb and hb.get("last_seen"):
        try:
            last_act = heartbeat.parse_rfc3339(hb["last_seen"])
        except heartbeat.HeartbeatError:
            last_act = None
    if last_act is None and audit_info.get("timestamp"):
        try:
            last_act = heartbeat.parse_rfc3339(audit_info["timestamp"])
        except heartbeat.HeartbeatError:
            last_act = None

    # Aktiv?
    if status in _OVERVIEW_INACTIVE_STATUSES:
        is_active = False
    elif status in ("RUNNING", "CLAIMED"):
        if last_act is None:
            is_active = True   # frisch gestartet, noch kein Heartbeat vorhanden
        else:
            delta_min = (now - last_act).total_seconds() / 60
            is_active = delta_min <= _OVERVIEW_INACTIVE_THRESHOLD_MINUTES
    else:
        is_active = False

    return machine, last_act, is_active


def _overview_rows(store, project_filter: "str | None" = None, now=None) -> list:
    """Alle Auftraege als Uebersichtszeilen, aktive oben, inaktive unten.

    Rueckgabe: nach Aktivitaet + Prioritaet sortierte Liste von Tupeln
    ``(task_id, projekt, fuehrung, status, machine, letzter_hb_str, is_active,
       prioritaet)``.
    Rein lesend, kein Zustandsfilter — Gegensatz zu ``_board_rows`` (BRIDGE-026).

    Sortierung (BRIDGE-028: Prioritaet als zweites Kriterium eingefuegt):
    - Gruppe 0 (aktiv): RUNNING/CLAIMED mit Heartbeat juenger als Schwelle
    - Gruppe 1 (alle anderen): inaktive, wartende, abgeschlossene
    - Innerhalb jeder Gruppe: Prioritaet (HIGH > MEDIUM > LOW) zuerst,
      dann neueste Aktivitaet als Tie-Breaker.
    """
    now = now or datetime.now(timezone.utc)
    audit_data = _overview_audit_scan(store)
    rows_raw = []
    for task in _list_task_docs(store):
        task_id = task.get("bridge_task_id", "?")
        project_id = task.get("project_id", "")
        if project_filter and project_id != project_filter:
            continue
        status = task.get("status") or "?"
        task_audit = audit_data.get(task_id, {"machine": None, "timestamp": None})
        machine, last_act, is_active = _overview_task_info(store, task, task_audit, now)
        last_act_str = _fmt_wait((now - last_act).total_seconds()) if last_act else "?"
        # Sortier-Timestamp: None -> epoch (kommt ans Ende der jeweiligen Gruppe)
        sort_ts = last_act.timestamp() if last_act is not None else 0.0
        prio = _task_priority(task)
        prio_rank = _priority_rank(task)
        rows_raw.append((
            task_id,
            _board_project(store, task),
            _board_review_roles(store, task),
            status,
            machine,
            last_act_str,
            is_active,
            prio,
            sort_ts,        # Hilfsspalte fuer Sortierung, wird am Ende entfernt
            prio_rank,      # Hilfsspalte fuer Sortierung, wird am Ende entfernt
        ))

    # (Aktiv-Gruppe, Prioritaets-Rang, -Zeitstempel)
    rows_raw.sort(key=lambda r: (0 if r[6] else 1, r[9], -r[8]))
    return [r[:8] for r in rows_raw]


def _overview_text(rows) -> str:
    """Baut aus den Uebersichtszeilen den Tabellentext fuer die CLI."""
    if not rows:
        return "(keine Auftraege)"
    lines = [f"{'#':<3}{'Prio':<7}{'Projekt':<13}{'Auftrag':<13}{'Status':<30}"
             f"{'Maschine':<14}{'Aktiv vor':<12}Fuehrung/Pruefung"]
    prev_active = None
    for i, (task_id, projekt, fuehrung, status, machine, last_act_str, is_active, prio) in \
            enumerate(rows, start=1):
        if prev_active is True and not is_active:
            lines.append("--- inaktiv / unterbrochen ---")
        line = (f"{i:<3}{prio:<7}{projekt:<13}{task_id:<13}{status:<30}"
                f"{machine:<14}{last_act_str:<12}{fuehrung}")
        lines.append(line)
        prev_active = is_active
    return "\n".join(lines)


def _cmd_overview(args, store) -> int:
    """bridge overview: alle Auftraege ueber alle Zustaende mit letzter Maschine."""
    project_filter = getattr(args, "project", None)
    rows = _overview_rows(store, project_filter=project_filter)
    print(_overview_text(rows))
    return 0


def _cmd_commands(args, store) -> int:
    base = registry.resolve_base(store.root, store.schema_dir,
                                 explicit_machine=args.machine)
    try:
        profile = profiles.load_profile(store.root, args.project,
                                        schema_dir=store.schema_dir)
        repository = profile.get("repository", args.project)
        test_cmd = (profile.get("test_policy") or {}).get("command")
    except (profiles.ProfileError, StoreError):
        repository = args.project
        test_cmd = None
    local_path = os.path.join(base, repository)
    test_line = test_cmd or 'kein Testbefehl im Profil hinterlegt'

    print("Board neu anzeigen:")
    print("  bridge board")
    print()
    print("Bridge-Watcher starten (wiederholt pruefen, bis Ctrl+C; --apply nur nach")
    print("Bestaetigung, s. Guardrails):")
    print("  bridge watch loop --actor <dein-name>")
    print()
    print("Uebergabe an die andere Maschine vorbereiten (PowerShell):")
    print(f"  cd {local_path}")
    print("  .\\scripts\\handover-check.ps1")
    print()
    print("Uebergabe vorbereiten (Bash/WSL, falls zutreffend):")
    print(f"  cd {local_path}")
    print("  ./scripts/handover-check.sh")
    print()
    print("Tests dieses Projekts laufen lassen:")
    print(f"  {test_line}")
    return 0


# --------------------------------------------------------------------------- #
# Helfer
# --------------------------------------------------------------------------- #

def _list_task_docs(store):
    docs = []
    if not store.tasks_dir.exists():
        return docs
    for entry in sorted(store.tasks_dir.iterdir()):
        if not (entry / "task.yaml").is_file():
            continue
        try:
            docs.append(store.load_task(entry.name))
        except StoreError:
            continue
    return docs


def _list_tasks(store):
    return [(t.get("bridge_task_id", "?"), t.get("status", "?"))
            for t in _list_task_docs(store)]


def _recent_commits(root, count=3):
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline", f"-{count}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _cmd_watch(args, store) -> int:
    if args.watch_cmd == "heartbeat":
        doc = heartbeat.beat(store.root, args.task_id, args.run_id,
                             actor=args.actor, machine=args.machine,
                             schema_dir=store.schema_dir)
        print(f"OK: Heartbeat {doc['bridge_task_id']} {doc['run_id']} "
              f"last_seen={doc['last_seen']}")
        return 0

    if getattr(args, "apply", False) and not args.actor:
        print("Nutzungsfehler: --apply erfordert --actor.", file=sys.stderr)
        return 2

    policy = watcher.load_policy(store.schema_dir)

    if args.watch_cmd == "scan":
        findings = watcher.scan(store, policy)
        if args.task:
            findings = [f for f in findings if f.bridge_task_id == args.task]
        applied = (watcher.apply(store, findings, args.actor, args.machine)
                   if args.apply else [])
        _print_findings(findings, applied)
        return 0

    if args.watch_cmd == "loop":
        runs = watcher.loop(store, policy, interval=args.interval,
                            apply=args.apply, actor=args.actor,
                            machine=args.machine,
                            max_iterations=args.max_iterations)
        for findings, applied in runs:
            _print_findings(findings, applied)
        return 0
    return 2  # vom Parser ausgeschlossen


def _print_findings(findings, applied) -> None:
    if not findings:
        print("(keine Findings)")
        return
    if applied:  # apply liefert 1:1 zu findings, in Reihenfolge
        for entry in applied:
            f = entry.finding
            mark = "OK  " if entry.applied else "SKIP"
            print(f"{mark} {f.kind:6} {f.bridge_task_id} {f.run_id} "
                  f"{f.from_status} -> {f.target}  [{entry.detail}]")
    else:
        for f in findings:
            note = "" if f.allowed else "  [Übergang nicht erlaubt - fail-closed]"
            print(f"DRY  {f.kind:6} {f.bridge_task_id} {f.run_id} "
                  f"{f.from_status} -> {f.target}{note}")


def _cmd_run(args, store) -> int:
    if args.run_cmd == "start":
        run_id = runner.start(store, args.task_id, args.actor, args.machine)
        _print_run(store, args.task_id, run_id, "gestartet")
        if getattr(args, "commit", False):
            rc = _do_commit(args, store, "run_start", args.task_id, args.actor,
                            run_id=run_id)
            if rc != 0:
                return rc
        return 0
    if args.run_cmd == "beat":
        doc = runner.beat(store, args.task_id, actor=args.actor, machine=args.machine)
        print(f"OK: Heartbeat {args.task_id} {doc['run_id']} "
              f"last_seen={doc['last_seen']}")
        return 0
    if args.run_cmd == "finish":
        # base_head-Fallback: wenn --base-head fehlt, aus task.yaml.git.expected_head
        # ableiten (fail-closed wenn auch das fehlt — kein stiller Fallback auf
        # "nur letzter Commit", BRIDGE-025).
        base_head = args.base_head
        if base_head is None:
            task = store.load_task(args.task_id)
            base_head = (task.get("git") or {}).get("expected_head")
            if base_head is None:
                print(
                    f"Fehler: --base-head fehlt und git.expected_head ist nicht in "
                    f"task.yaml von {args.task_id} gesetzt. "
                    f"Bitte --base-head <SHA> explizit angeben (fail-closed).",
                    file=sys.stderr,
                )
                return 1
        draft = importer.load_draft(args.draft_path) if args.draft_path else {}
        result, event = runner.finish(
            store, args.task_id, args.status,
            draft=draft, base_head=base_head,
            actor=args.actor, machine=args.machine, summary=args.summary)
        print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']}; "
              f"Ergebnis {result['run_id']} abgelegt")
        if getattr(args, "commit", False):
            rc = _do_commit(args, store, "run_finish", args.task_id, args.actor,
                            run_id=result["run_id"])
            if rc != 0:
                return rc
        return 0
    if args.run_cmd == "resume":
        run_id = runner.resume(store, args.task_id, args.actor, args.machine)
        _print_run(store, args.task_id, run_id, "wiederaufgenommen")
        return 0
    return 2  # vom Parser ausgeschlossen


def _print_run(store, task_id, run_id, verb) -> None:
    task = store.load_task(task_id)
    print(f"OK: {task_id} {verb} (RUN={run_id}, status={task.get('status')})")
    for item in runner.open_acceptance_criteria(store, task_id):
        print(f"  - [ ] {item}")
    hint = runner.last_resume_hint(store, task_id)
    if hint:
        print(f"resume_hint: {hint}")


def _cmd_project(args, store) -> int:
    if args.project_cmd == "list":
        ids = profiles.list_profiles(store.root)
        if not ids:
            print("(keine Profile)")
        for pid in ids:
            doc = profiles.load_profile(store.root, pid, schema_dir=store.schema_dir)
            print(f"{doc['project_id']}\tread_only={doc['read_only']}\t"
                  f"task_prefix={doc['task_prefix']}")
        return 0
    if args.project_cmd == "show":
        doc = profiles.load_profile(store.root, args.project_id,
                                    schema_dir=store.schema_dir)
        for key in ("project_id", "description", "repository", "default_branch",
                    "task_prefix", "read_only", "executor", "controller", "allowed_machines"):
            if key in doc:
                print(f"{key}: {doc[key]}")
        return 0
    if args.project_cmd == "validate":
        doc = profiles.validate_profile(args.path, store.schema_dir)
        print(f"OK: Profil {doc.get('project_id')} gültig ({args.path})")
        return 0
    return 2  # vom Parser ausgeschlossen


def _cmd_webui(args, store) -> int:
    # Lazy-Import: webui.py importiert Board-Helfer aus cli.py - der Import hier
    # unten vermeidet einen Import-Zyklus beim Laden von cli.py.
    from bridge import webui

    try:
        httpd = webui.serve(store, port=args.port, actor=args.actor)
    except OSError as exc:
        print(f"Fehler: Port {args.port} nicht verfuegbar ({exc}). "
              f"Anderen Port mit --port waehlen.", file=sys.stderr)
        return 1
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"Web-UI: http://{host}:{port}/ (nur lokal erreichbar, Strg+C zum Beenden)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()  # sauberer Abschluss, kein Traceback (wie _board_loop)
    finally:
        httpd.server_close()
    return 0


_DISPATCH = {
    "validate": _cmd_validate,
    "task": _cmd_task,
    "result": _cmd_result,
    "next-run": _cmd_next_run,
    "audit": _cmd_audit,
    "resume": _cmd_resume,
    "overview": _cmd_overview,
    "board": _cmd_board,
    "commands": _cmd_commands,
    "webui": _cmd_webui,
    "watch": _cmd_watch,
    "run": _cmd_run,
    "project": _cmd_project,
}


# --------------------------------------------------------------------------- #
# Einstieg
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: Usage-Fehler / --help
        if exc.code is None:
            return 0
        return exc.code if isinstance(exc.code, int) else 2

    try:
        store = Store(root=args.root, schema_dir=args.schema_dir)
        return _DISPATCH[args.cmd](args, store)
    except _ENGINE_ERRORS as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
