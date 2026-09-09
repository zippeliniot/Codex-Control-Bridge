"""Lokale Web-UI ueber dem Board (BRIDGE-020).

Reine stdlib (``http.server``, ``json``, ``urllib``) - kein neues
Laufzeit-Requirement, konsistent mit dem Rest des Projekts.

SICHERHEIT (siehe auch docs/security/SECURITY-MODEL.md, Abschnitt
"Web-UI (BRIDGE-020)"):

* Der Server bindet **ausschliesslich an 127.0.0.1**. Es gibt bewusst keine
  ``--host``-Option und keinen ``0.0.0.0``-Pfad - ``HOST`` unten ist hart
  verdrahtet. Das ist die technische Umsetzung von "keine externe
  Erreichbarkeit", nicht nur eine Empfehlung.
* Es gibt **keinen Auth-Layer**. Das ist zulaessig, weil der Server nur lokal
  erreichbar ist (Single-User-Maschine). Wer hier je die Bindung aufweicht,
  oeffnet die ungeschuetzte Bridge-Steuerung fuer jeden im Netz - deshalb ist
  diese Luecke hier ausdruecklich dokumentiert.
* Schreibende POST-Endpunkte (RUN-02) sind zusaetzlich abgesichert:
  - Same-Origin-Pflicht: ``Origin`` (ersatzweise ``Referer``) muss
    ``http://127.0.0.1:<port>`` sein, sonst HTTP 403. Schuetzt gegen einen
    boesartigen Tab in einem anderen Browserfenster, der im Hintergrund
    gegen localhost postet.
  - Serverseitige Bestaetigungspflicht: ohne ``confirm: true`` und ohne
    nicht-leeren ``actor`` -> HTTP 400 (der Browser-Dialog ist nur UX).
  - ``run finish`` zusaetzlich: ohne nicht-leere ``summary`` -> HTTP 400
    (setzt die ``--summary``-Pflicht aus CLAUDE.md / BRIDGE-021 durch).

Lesend: ``GET /`` und ``GET /api/board``. Schreibend (RUN-02):
``POST /api/task/<id>/copied``, ``POST /api/task/<id>/archive``,
``POST /api/run/<id>/finish`` - jeder ruft **dieselbe** Store-/Runner-Logik
wie das entsprechende CLI-Kommando auf (kein Parallel-Code, Audit-Eintrag
entsteht automatisch in ``store.set_status`` / ``runner.finish``).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import importer, runner, state_machine
# Dieselben Funktionen wie `bridge board` / `bridge task copied` /
# `bridge task archive` - garantiert keine zweite, abweichende Implementierung.
from bridge.cli import (
    _BOARD_STATES, _board_rows, _fmt_wait, _list_task_docs,
    task_archive, task_copied,
)
from bridge.store import StoreError

HOST = "127.0.0.1"          # HART. Nicht konfigurierbar. Siehe Modulkopf.
DEFAULT_PORT = 8420
REFRESH_SECONDS = 15         # gleicher Standard wie `bridge board --watch --interval`

# Ziele, die `runner.finish` aus RUNNING laut state-model.yaml zulaesst.
_FINISH_TARGETS = ("COMPLETED", "FAILED", "BLOCKED", "REVIEW_REQUIRED",
                   "APPROVAL_REQUIRED")

_BOARD_FIELDS = ("bridge_task_id", "projekt", "fuehrung", "richtung",
                 "wartet_seit", "hinweis")

# Fehlerklassen der Engine, die als "im aktuellen Zustand nicht erlaubt" gelten.
_ENGINE_ERRORS = (StoreError, state_machine.TransitionError,
                  state_machine.ModelError, runner.RunnerError,
                  importer.ImporterError)


# --------------------------------------------------------------------------- #
# Datenermittlung
# --------------------------------------------------------------------------- #

def _wait_since(store, task_id, status, now) -> str:
    ts = store.last_transition_at(task_id, status)
    if not ts:
        return "?"
    try:
        when = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "?"
    return _fmt_wait((now - when).total_seconds())


def _row_actions(status) -> list[str]:
    """Welche Aktions-Buttons fuer diesen Status laut state-model.yaml zulaessig
    sind. Einzige Quelle: ``state_machine`` bzw. die Vorbedingungen der
    CLI-Kommandos - das Frontend zeigt nur, was hier gelistet ist."""
    actions = []
    if status == "WAITING_FOR_COPY_TO_CONTROL":
        actions.append("copied")          # wie `bridge task copied`
    if status == "RUNNING":
        actions.append("finish")          # wie `bridge run finish`
    if status and state_machine.is_allowed(status, "ARCHIVED"):
        actions.append("archive")         # wie `bridge task archive`
    return actions


def board_payload(store) -> dict:
    """``{"board": [...], "other": [...]}``.

    ``board`` ist 1:1 die Datenquelle von ``_board_rows(store)`` (dieselbe
    Funktion wie ``bridge board``), pro Zeile zusaetzlich um ``status`` (roh)
    und ``actions`` (zulaessige Buttons) ergaenzt. ``other`` ist die schlanke
    Zusatzliste aller nicht archivierten Auftraege, die nicht bereits im
    Board stehen.
    """
    now = datetime.now(timezone.utc)

    board = []
    for row in _board_rows(store):
        entry = dict(zip(_BOARD_FIELDS, row))
        try:
            entry["status"] = store.load_task(entry["bridge_task_id"]).get("status")
        except StoreError:
            entry["status"] = None
        entry["actions"] = _row_actions(entry["status"])
        board.append(entry)
    on_board = {e["bridge_task_id"] for e in board}

    other = []
    for task in _list_task_docs(store):
        status = task.get("status")
        task_id = task.get("bridge_task_id", "?")
        if status in _BOARD_STATES or status == "ARCHIVED" or task_id in on_board:
            continue
        other.append({
            "bridge_task_id": task_id,
            "projekt": task.get("project_id", "?"),
            "status": status,
            "wartet_seit": _wait_since(store, task_id, status, now),
            "actions": _row_actions(status),
        })
    other.sort(key=lambda r: r["bridge_task_id"])

    return {"board": board, "other": other, "finish_targets": list(_FINISH_TARGETS)}


# --------------------------------------------------------------------------- #
# Aktionen (RUN-02) - rufen die gemeinsame Store-/Runner-Logik auf
# --------------------------------------------------------------------------- #

class _BadRequest(Exception):
    """Ungueltiger Request-Body (fehlt confirm/actor/summary/...). -> HTTP 400."""


def _require(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _BadRequest(f"Feld '{key}' fehlt oder ist leer.")
    return value.strip()


def _apply_action(store, kind: str, task_id: str, body: dict) -> dict:
    """Fuehrt eine der drei Aktionen aus. Prueft serverseitig die
    Bestaetigungspflicht (der Browser-Dialog allein reicht nicht) und ruft
    dann exakt die Funktion, die auch das CLI nutzt.
    """
    if body.get("confirm") is not True:
        raise _BadRequest("Bestaetigung fehlt (confirm: true erforderlich).")
    actor = _require(body, "actor")

    if kind == "copied":
        event = task_copied(store, task_id, actor)
        return {"ok": True, "task": task_id, "old_state": event["old_state"],
                "new_state": event["new_state"], "event_type": event["event_type"]}

    if kind == "archive":
        reason = body.get("reason") or None
        event = task_archive(store, task_id, actor, reason)
        return {"ok": True, "task": task_id, "old_state": event["old_state"],
                "new_state": event["new_state"], "event_type": event["event_type"]}

    if kind == "finish":
        status = _require(body, "status")
        summary = _require(body, "summary")   # BRIDGE-021: --summary ist Pflicht
        result, event = runner.finish(
            store, task_id, status,
            draft={}, base_head=None, actor=actor, machine=None, summary=summary)
        return {"ok": True, "task": task_id, "run_id": result["run_id"],
                "old_state": event["old_state"], "new_state": event["new_state"],
                "event_type": event["event_type"]}

    raise _BadRequest(f"Unbekannte Aktion: {kind}")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

_PAGE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codex Control Bridge - Board</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 1.5rem; }
  h1 { font-size: 1.2rem; margin: 0 0 .25rem; }
  h2 { font-size: 1rem; margin: 1.75rem 0 .5rem; }
  .meta { color: #888; font-size: .85rem; margin-bottom: 1rem; }
  .bar { margin: .5rem 0 1rem; }
  .bar label { color: #888; }
  input { font: inherit; padding: .2rem .4rem; }
  table { border-collapse: collapse; width: 100%; max-width: 78rem; }
  th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #8884; vertical-align: top; }
  th { font-weight: 600; }
  td.id { font-family: ui-monospace, monospace; white-space: nowrap; }
  button { font: inherit; margin: 0 .25rem .25rem 0; padding: .15rem .5rem; cursor: pointer; }
  .empty { color: #888; font-style: italic; }
  .err { color: #c00; }
  .ok { color: #0a0; }
  .note { color: #888; font-size: .85rem; margin-top: .25rem; }
</style>
</head>
<body>
<h1>Codex Control Bridge &ndash; Board</h1>
<div class="meta" id="meta">Lade &hellip;</div>
<div class="bar">
  <label for="actor">Akteur (actor):</label>
  <input id="actor" value="" size="24">
</div>
<div id="flash"></div>

<h2>Board &ndash; wartet auf Weitergabe / Kopie</h2>
<table id="board"><thead><tr>
  <th>#</th><th>Projekt</th><th>F&uuml;hrung/Pr&uuml;fung</th>
  <th>Richtung</th><th>Auftrag</th><th>Wartet seit</th><th>Hinweis</th><th>Aktionen</th>
</tr></thead><tbody></tbody></table>

<h2>Offene Auftr&auml;ge au&szlig;erhalb des Boards</h2>
<table id="other"><thead><tr>
  <th>#</th><th>Auftrag</th><th>Projekt</th><th>Status</th><th>Wartet seit</th><th>Aktionen</th>
</tr></thead><tbody></tbody></table>

<p class="note">
  Hinweis: F&uuml;r regul&auml;re Auftragsabschl&uuml;sse nutzt Claude Code
  weiterhin <code>bridge run finish --from draft.yaml</code> direkt im Terminal
  (liefert <code>acceptance_results</code> mit). Der Button &bdquo;Lauf
  abschlie&szlig;en&ldquo; hier ist f&uuml;r manuelle / Ausnahme-Abschl&uuml;sse
  (z.&nbsp;B. h&auml;ngengebliebene L&auml;ufe).
</p>

<script>
const REFRESH_MS = %REFRESH_MS%;
let FINISH_TARGETS = ["COMPLETED", "FAILED", "BLOCKED", "REVIEW_REQUIRED", "APPROVAL_REQUIRED"];
const ACTION_LABEL = {copied: "Kopiert → Review", archive: "Archivieren", finish: "Lauf abschließen"};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
}
function row(cells) {
  return "<tr>" + cells.map(c => "<td>" + c + "</td>").join("") + "</tr>";
}
function actionButtons(id) {
  return function (acts) {
    return (acts || []).map(a =>
      "<button data-act='" + a + "' data-id='" + esc(id) + "'>" + ACTION_LABEL[a] + "</button>"
    ).join("");
  };
}
function flash(msg, cls) {
  const f = document.getElementById("flash");
  f.textContent = msg;
  f.className = cls;
  if (cls === "ok") setTimeout(() => { if (f.textContent === msg) { f.textContent = ""; f.className = ""; } }, 6000);
}

async function post(kind, id) {
  const actor = document.getElementById("actor").value.trim();
  if (!actor) { flash("Bitte zuerst einen Akteur (actor) eintragen.", "err"); return; }

  let url, payload = {actor: actor, confirm: true};
  if (kind === "copied") {
    url = "/api/task/" + encodeURIComponent(id) + "/copied";
    if (!confirm("Auftrag " + id + ": Ergebnis als in den Steuerchat kopiert markieren (→ REVIEW_REQUIRED)?")) return;
  } else if (kind === "archive") {
    url = "/api/task/" + encodeURIComponent(id) + "/archive";
    const reason = prompt("Auftrag " + id + " archivieren (→ ARCHIVED).\nOptionaler Grund:", "");
    if (reason === null) return;
    if (reason.trim()) payload.reason = reason.trim();
  } else if (kind === "finish") {
    url = "/api/run/" + encodeURIComponent(id) + "/finish";
    const status = prompt("Lauf " + id + " abschließen.\nZielstatus (" + FINISH_TARGETS.join(" / ") + "):", "COMPLETED");
    if (status === null) return;
    if (FINISH_TARGETS.indexOf(status.trim()) < 0) { flash("Ungültiger Zielstatus.", "err"); return; }
    const summary = prompt("Zusammenfassung (Pflicht - was hat der Lauf getan?):", "");
    if (summary === null) return;
    if (!summary.trim()) { flash("Zusammenfassung darf nicht leer sein.", "err"); return; }
    payload.status = status.trim();
    payload.summary = summary.trim();
  } else {
    return;
  }

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      flash("Fehler (" + res.status + "): " + (data.error || "unbekannt"), "err");
    } else {
      flash("OK: " + id + " " + data.old_state + " → " + data.new_state, "ok");
    }
  } catch (e) {
    flash("Netzwerkfehler: " + e.message, "err");
  }
  refresh();   // sofort neu laden, nicht auf den 15s-Tick warten
}

async function refresh() {
  const meta = document.getElementById("meta");
  try {
    const res = await fetch("/api/board", {headers: {"Accept": "application/json"}});
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || ("HTTP " + res.status));

    if (Array.isArray(data.finish_targets)) FINISH_TARGETS = data.finish_targets;
    const actorInput = document.getElementById("actor");
    if (!actorInput.value && data.actor) actorInput.value = data.actor;

    const b = document.querySelector("#board tbody");
    b.innerHTML = data.board.length
      ? data.board.map((r, i) => row([
          i + 1, esc(r.projekt), esc(r.fuehrung), esc(r.richtung),
          "<span class='id'>" + esc(r.bridge_task_id) + "</span>",
          esc(r.wartet_seit), esc(r.hinweis), actionButtons(r.bridge_task_id)(r.actions)])).join("")
      : row(["<span class='empty'>keine Auftr&auml;ge warten auf Kopie</span>"]);

    const o = document.querySelector("#other tbody");
    o.innerHTML = data.other.length
      ? data.other.map((r, i) => row([
          i + 1, "<span class='id'>" + esc(r.bridge_task_id) + "</span>",
          esc(r.projekt), esc(r.status), esc(r.wartet_seit),
          actionButtons(r.bridge_task_id)(r.actions)])).join("")
      : row(["<span class='empty'>nichts offen</span>"]);

    meta.textContent = "Aktualisiert: " + new Date().toISOString()
      + "  ·  Auto-Refresh alle " + (REFRESH_MS / 1000) + "s  ·  nur lokal (127.0.0.1)";
    meta.classList.remove("err");
  } catch (e) {
    meta.textContent = "Fehler beim Laden: " + e.message;
    meta.classList.add("err");
  }
}

document.addEventListener("click", ev => {
  const btn = ev.target.closest("button[data-act]");
  if (btn) post(btn.dataset.act, btn.dataset.id);
});
refresh();
setInterval(refresh, REFRESH_MS);
</script>
</body>
</html>
""".replace("%REFRESH_MS%", str(REFRESH_SECONDS * 1000))


class _Handler(BaseHTTPRequestHandler):
    server_version = "BridgeWebUI/1"
    # HTTP/1.0: Verbindung schliesst nach jeder Antwort - simpel, ausreichend
    # fuer eine lokale Ein-Nutzer-UI, keine Keep-alive-Zustandshaltung noetig.

    # kein Zugriffslog auf stderr - der Server laeuft im Vordergrund des Nutzers
    def log_message(self, *args):  # noqa: D401
        pass

    # -- Antwort-Helfer -------------------------------------------------

    def _send(self, code, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    # -- GET ----------------------------------------------------------

    def do_GET(self) -> None:
        route = self._route()
        if route == "/":
            self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if route == "/api/board":
            try:
                payload = board_payload(self.server.store)
            except Exception as exc:  # noqa: BLE001 - ein kaputter Request darf
                # den ThreadingHTTPServer nie beenden; Store/Profil-Fehler
                # werden als JSON-Fehlerobjekt zurueckgegeben, kein Stacktrace.
                self._json(500, {"error": str(exc)})
                return
            payload["actor"] = getattr(self.server, "actor", None)
            self._json(200, payload)
            return
        self._json(404, {"error": f"nicht gefunden: {route}"})

    do_HEAD = do_GET

    # -- POST (RUN-02) ----------------------------------------------

    def _same_origin_ok(self) -> bool:
        expected = f"http://{HOST}:{self.server.server_address[1]}"
        origin = self.headers.get("Origin")
        if origin is not None:
            return origin == expected
        referer = self.headers.get("Referer")
        if referer is not None:
            return referer == expected or referer.startswith(expected + "/")
        return False  # weder Origin noch Referer -> fail-closed

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise _BadRequest(f"Body ist kein gueltiges JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise _BadRequest("Body muss ein JSON-Objekt sein.")
        return data

    _POST_ROUTES = {
        "task": {"copied": "copied", "archive": "archive"},
        "run": {"finish": "finish"},
    }

    def _match_post(self):
        parts = self._route().strip("/").split("/")
        # ['api', 'task'|'run', '<id>', '<verb>']
        if len(parts) == 4 and parts[0] == "api" and parts[1] in self._POST_ROUTES:
            kind = self._POST_ROUTES[parts[1]].get(parts[3])
            if kind:
                return kind, parts[2]
        return None, None

    def do_POST(self) -> None:
        kind, task_id = self._match_post()
        if kind is None:
            self._json(404, {"error": f"nicht gefunden: {self._route()}"})
            return
        if not self._same_origin_ok():
            self._json(403, {"error": "Same-Origin-Pruefung fehlgeschlagen "
                                      "(Origin/Referer muss die lokale UI sein)."})
            return
        try:
            body = self._read_json_body()
            result = _apply_action(self.server.store, kind, task_id, body)
        except _BadRequest as exc:
            self._json(400, {"error": str(exc)})
            return
        except _ENGINE_ERRORS as exc:
            # Aktion im aktuellen Zustand nicht erlaubt - dieselbe Ablehnung
            # wie beim CLI, nur als HTTP 409 statt Exit-Code 1.
            self._json(409, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - Server darf nicht sterben
            self._json(500, {"error": str(exc)})
            return
        self._json(200, result)

    def do_PUT(self) -> None:
        self._json(405, {"error": "Methode nicht erlaubt."})

    do_DELETE = do_PATCH = do_PUT


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #

def serve(store, *, port, actor, host=HOST):
    """Bindet einen ``ThreadingHTTPServer`` an ``host``/``port`` und gibt ihn
    zurueck (noch ohne ``serve_forever``). ``host`` ist nur fuer Tests
    parametrisiert - der CLI-Aufruf bindet **immer** an ``127.0.0.1`` (kein
    ``--host``-Flag). ``actor`` ist die Vorbelegung fuer das actor-Feld der
    Aktions-Buttons (im Frontend editierbar).
    """
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.store = store
    httpd.actor = actor
    return httpd
