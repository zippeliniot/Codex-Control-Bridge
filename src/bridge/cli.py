"""Einheitliche Kommandozeile über der Bridge-Engine (BRIDGE-006).

Reine stdlib. Wiederverwendung von src/bridge/store.py und
src/bridge/state_machine.py - die Engine wird genutzt, nicht dupliziert.
Exit-Codes: 0 = OK, 1 = Fachfehler/fail-closed, 2 = Nutzungsfehler.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# src-Layout: direkter Skriptaufruf (python src/bridge/cli.py ...) braucht das
# Paketverzeichnis auf dem Importpfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import state_machine
from bridge.store import Store, StoreError

_ENGINE_ERRORS = (StoreError, state_machine.TransitionError, state_machine.ModelError)


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
    tsub.add_parser("create", help="Auftrag anlegen").add_argument("path")
    tsub.add_parser("show", help="Status + Kernfelder").add_argument("task_id")
    tsub.add_parser("list", help="alle Aufträge mit Status")
    tset = tsub.add_parser("set-status", help="Zustandswechsel")
    tset.add_argument("task_id")
    tset.add_argument("new_state")
    tset.add_argument("--actor", required=True)
    tset.add_argument("--machine")
    tset.add_argument("--reason")

    result = sub.add_parser("result", help="Ergebnisse verwalten")
    rsub = result.add_subparsers(dest="result_cmd", required=True)
    rsub.add_parser("write", help="Ergebnis ablegen").add_argument("path")

    sub.add_parser("next-run", help="nächste Lauf-ID").add_argument("task_id")

    audit = sub.add_parser("audit", help="Auditspur")
    asub = audit.add_subparsers(dest="audit_cmd", required=True)
    asub.add_parser("show", help="Auditspur ausgeben").add_argument("task_id", nargs="?")

    sub.add_parser("resume", help="Wiederaufsetz-Hilfe (rein lesend)").add_argument("task_id")
    return parser


# --------------------------------------------------------------------------- #
# Kommandos
# --------------------------------------------------------------------------- #

def _cmd_validate(args, store) -> int:
    doc = store.validate(args.path)
    print(f"OK: {doc.get('kind')} gültig ({args.path})")
    return 0


def _cmd_task(args, store) -> int:
    if args.task_cmd == "create":
        doc = store.create_task(args.path)
        print(f"OK: {doc['bridge_task_id']} angelegt (status={doc['status']})")
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
    if args.task_cmd == "set-status":
        event = store.set_status(args.task_id, args.new_state, actor=args.actor,
                                 machine=args.machine, reason=args.reason)
        print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']} "
              f"({event['event_type']})")
        return 0
    return 2  # vom Parser ausgeschlossen


def _cmd_result(args, store) -> int:
    doc = store.write_result(args.path)  # result_cmd == "write"
    print(f"OK: Ergebnis {doc['bridge_task_id']} {doc['run_id']} abgelegt")
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


# --------------------------------------------------------------------------- #
# Helfer
# --------------------------------------------------------------------------- #

def _list_tasks(store):
    rows = []
    if not store.tasks_dir.exists():
        return rows
    for entry in sorted(store.tasks_dir.iterdir()):
        if not (entry / "task.yaml").is_file():
            continue
        try:
            task = store.load_task(entry.name)
        except StoreError:
            continue
        rows.append((task.get("bridge_task_id", entry.name), task.get("status", "?")))
    return rows


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


_DISPATCH = {
    "validate": _cmd_validate,
    "task": _cmd_task,
    "result": _cmd_result,
    "next-run": _cmd_next_run,
    "audit": _cmd_audit,
    "resume": _cmd_resume,
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
