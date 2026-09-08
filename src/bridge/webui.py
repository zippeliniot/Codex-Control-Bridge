"""Lokale Lese-Web-UI ueber dem Board (BRIDGE-020, RUN-01).

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

RUN-01 ist **rein lesend**: nur ``GET /`` und ``GET /api/board``. Jede andere
Methode/Route antwortet mit 404/405. Aktions-Endpunkte folgen in RUN-02.
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

# Dieselbe Board-Datenquelle wie `bridge board` - garantiert keine zweite,
# potenziell abweichende Implementierung (Akzeptanzkriterium BRIDGE-020).
from bridge.cli import _BOARD_STATES, _board_rows, _fmt_wait, _list_task_docs
from bridge.store import StoreError

HOST = "127.0.0.1"          # HART. Nicht konfigurierbar. Siehe Modulkopf.
DEFAULT_PORT = 8420
REFRESH_SECONDS = 15         # gleicher Standard wie `bridge board --watch --interval`

_BOARD_FIELDS = ("bridge_task_id", "projekt", "fuehrung", "richtung",
                 "wartet_seit", "hinweis")


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


def board_payload(store) -> dict:
    """``{"board": [...], "other": [...]}``.

    ``board`` ist 1:1 die Datenquelle von ``_board_rows(store)`` (dieselbe
    Funktion wie ``bridge board``), pro Zeile zusaetzlich um das rohe
    ``status``-Feld ergaenzt (fuer die Buttons in RUN-02, in RUN-01 nur
    mitgeliefert). ``other`` ist die schlanke Zusatzliste aller nicht
    archivierten Auftraege, die nicht bereits im Board stehen.
    """
    now = datetime.now(timezone.utc)

    board = []
    for row in _board_rows(store):
        entry = dict(zip(_BOARD_FIELDS, row))
        try:
            entry["status"] = store.load_task(entry["bridge_task_id"]).get("status")
        except StoreError:
            entry["status"] = None
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
        })
    other.sort(key=lambda r: r["bridge_task_id"])

    return {"board": board, "other": other}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

_PAGE = """<!doctype html>
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
  table { border-collapse: collapse; width: 100%; max-width: 70rem; }
  th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #8884; }
  th { font-weight: 600; }
  td.id { font-family: ui-monospace, monospace; white-space: nowrap; }
  .empty { color: #888; font-style: italic; }
  .err { color: #c00; }
</style>
</head>
<body>
<h1>Codex Control Bridge &ndash; Board</h1>
<div class="meta" id="meta">Lade &hellip;</div>

<h2>Board &ndash; wartet auf Weitergabe / Kopie</h2>
<table id="board"><thead><tr>
  <th>#</th><th>Projekt</th><th>F&uuml;hrung/Pr&uuml;fung</th>
  <th>Richtung</th><th>Auftrag</th><th>Wartet seit</th><th>Hinweis</th>
</tr></thead><tbody></tbody></table>

<h2>Offene Auftr&auml;ge au&szlig;erhalb des Boards</h2>
<table id="other"><thead><tr>
  <th>#</th><th>Auftrag</th><th>Projekt</th><th>Status</th><th>Wartet seit</th>
</tr></thead><tbody></tbody></table>

<script>
const REFRESH_MS = %REFRESH_MS%;
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c]));
}
function row(cells) {
  return "<tr>" + cells.map(c => "<td>" + c + "</td>").join("") + "</tr>";
}
async function refresh() {
  const meta = document.getElementById("meta");
  try {
    const res = await fetch("/api/board", {headers: {"Accept": "application/json"}});
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || ("HTTP " + res.status));

    const b = document.querySelector("#board tbody");
    b.innerHTML = data.board.length
      ? data.board.map((r, i) => row([
          i + 1, esc(r.projekt), esc(r.fuehrung), esc(r.richtung),
          "<span class='id'>" + esc(r.bridge_task_id) + "</span>",
          esc(r.wartet_seit), esc(r.hinweis)])).join("")
      : row(["<span class='empty'>keine Auftr&auml;ge warten auf Kopie</span>"]);

    const o = document.querySelector("#other tbody");
    o.innerHTML = data.other.length
      ? data.other.map((r, i) => row([
          i + 1, "<span class='id'>" + esc(r.bridge_task_id) + "</span>",
          esc(r.projekt), esc(r.status), esc(r.wartet_seit)])).join("")
      : row(["<span class='empty'>nichts offen</span>"]);

    meta.textContent = "Aktualisiert: " + new Date().toISOString()
      + "  \\u00b7  Auto-Refresh alle " + (REFRESH_MS / 1000) + "s  \\u00b7  nur lokal (127.0.0.1)";
    meta.classList.remove("err");
  } catch (e) {
    meta.textContent = "Fehler beim Laden: " + e.message;
    meta.classList.add("err");
  }
}
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
            self._json(200, payload)
            return
        self._json(404, {"error": f"nicht gefunden: {route}"})

    do_HEAD = do_GET

    def _read_only(self) -> None:
        self._json(405, {"error": "RUN-01 ist rein lesend (nur GET / und GET /api/board)"})

    do_POST = do_PUT = do_DELETE = do_PATCH = _read_only


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #

def serve(store, *, port, actor, host=HOST):
    """Bindet einen ``ThreadingHTTPServer`` an ``host``/``port`` und gibt ihn
    zurueck (noch ohne ``serve_forever``). ``host`` ist nur fuer Tests
    parametrisiert - der CLI-Aufruf bindet **immer** an ``127.0.0.1`` (kein
    ``--host``-Flag). ``actor`` wird fuer RUN-02 (Aktions-Endpunkte) am Server
    hinterlegt; RUN-01 nutzt es noch nicht.
    """
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.store = store
    httpd.actor = actor
    return httpd
