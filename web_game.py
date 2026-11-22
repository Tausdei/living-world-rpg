"""Local browser entry point for Living World, using the existing RPG rules."""
import json
import os
import re
import secrets
import time
from contextlib import closing
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from activities import QUESTS, stats
from adventures import ROUTES, current_scene
from art_catalog import QUEST_ART, event_illustration, illustration_path
from fieldwork import ENEMIES, HUNT_ACTIONS, active_hunt
from game import PROFESSIONS, connect, play
from practice_games import active_practice, practice_view
from loot import ITEMS
from world import advance_hero, current_job
from world_events import JOBS


STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
ROOT = Path(__file__).resolve().parent
COOKIE = "living_world"
SESSION = re.compile(r"[a-f0-9]{40}")


def connect_web(path):
    db = connect(path)
    db.execute("""
        CREATE TABLE IF NOT EXISTS browser_players (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE
        )
    """)
    return db


def player(db, token):
    if token and SESSION.fullmatch(token):
        row = db.execute("SELECT user_id FROM browser_players WHERE token = ?", (token,)).fetchone()
        if row:
            return row["user_id"], None
    token = secrets.token_hex(20)
    user_id = db.execute("INSERT INTO browser_players (token) VALUES (?)", (token,)).lastrowid
    return user_id, token


def state(db, user_id):
    hero = db.execute("SELECT * FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
    if not hero:
        return {"hero": None}
    hp, attack = stats(db, hero)
    inventory = db.execute("""
        SELECT loot.*, equipped.item IS NOT NULL AS worn FROM loot
        LEFT JOIN equipped USING (hero_id, item) WHERE hero_id = ? ORDER BY loot.item
    """, (user_id,)).fetchall()
    hunt = active_hunt(db, user_id)
    practice = active_practice(db, user_id)
    battle = None
    if hunt:
        key = hunt["enemy"]
        battle = {
            **dict(hunt), "name": ENEMIES[key][0], "foeMax": ENEMIES[key][2],
            "art": "ash-keeper" if key == "keeper" else key,
            "actions": [{"key": key, "label": label} for key, label in HUNT_ACTIONS.items()
                        if key != "heal" or not hunt["used_heal"]],
        }
        battle.pop("token")
    route = hero["route"]
    encounter = None
    if route:
        area = ROUTES[route]
        index, scene, prepared = current_scene(db, user_id, route)
        encounter = {
            "title": area.title, "art": area.art, "description": scene.description,
            "choices": [option.title for option in scene.options],
            "stage": index + 1, "total": len(area.scenes),
            "required": max(0, area.difficulty - prepared) if index else None,
        }
    return {
        "hero": {**dict(hero), "level": 1 + hero["xp"] // 30, "hp": hp, "attack": attack},
        "bag": [{"key": row["item"], "quantity": row["quantity"], "worn": row["worn"],
                 "name": ITEMS[row["item"]][0], "slot": ITEMS[row["item"]][1],
                 "bonus": ITEMS[row["item"]][2]} for row in inventory],
        "battle": battle, "practice": practice_view(practice) if practice else None,
        "job": current_job(db, user_id), "encounter": encounter,
        "routes": [{"key": key, "name": area.title, "art": area.art,
                    "level": area.level, "scenes": len(area.scenes)} for key, area in ROUTES.items()],
        "jobs": [{"key": key, "name": name, "description": description, "art": art}
                 for key, (name, description, art) in JOBS.items()],
        "enemies": [{"key": key, "name": data[0], "level": data[1], "art": "ash-keeper" if key == "keeper" else key}
                    for key, data in ENEMIES.items()],
        "professions": PROFESSIONS,
        "quests": [{"key": key, "npc": npc, "description": text, "art": QUEST_ART[key],
                    "title": ROUTES[key].title if key in ROUTES else "Пепельный смотритель"}
                   for key, (npc, text, *_) in QUESTS.items()],
        "journal": [{**dict(row), "art": event_illustration(row["summary"])} for row in db.execute("""
            SELECT occurred_at, summary FROM world_journal WHERE user_id = ?
            ORDER BY occurred_at DESC LIMIT 8
        """, (user_id,))],
    }


class GameHandler(BaseHTTPRequestHandler):
    def respond(self, payload, content_type, cookie=None, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "no-cache")
        if cookie:
            self.send_header("Set-Cookie", f"{COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
        self.end_headers()
        self.wfile.write(payload)

    def game_response(self, command=None):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except CookieError:
            jar.clear()
        token = jar[COOKIE].value if COOKIE in jar else None
        with closing(connect_web(self.server.database)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            user_id, new_cookie = player(db, token)
            message = None
            if command:
                message = play(db, user_id, command)
            else:
                advance_hero(db, user_id, int(time.time()))
            result = {"state": state(db, user_id), "message": message}
        self.respond(json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8", new_cookie)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            self.game_response()
        elif path in STATIC:
            filename, mime = STATIC[path]
            self.respond((ROOT / "web" / filename).read_bytes(), mime)
        elif path.startswith("/art/"):
            asset = illustration_path(path.removeprefix("/art/"))
            if asset and asset.is_file():
                self.respond(asset.read_bytes(), "image/jpeg")
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/action":
            self.send_error(404)
            return
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            self.send_error(403)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError
            body = json.loads(self.rfile.read(size))
            command = body["command"]
            if not isinstance(command, str) or not re.fullmatch(r"/[a-z0-9_]+(?: [^\r\n]{1,160})?", command):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            self.send_error(400)
            return
        self.game_response(command)


def main():
    port = int(os.environ.get("WEB_PORT", "8080"))
    database = os.environ.get("WEB_GAME_DB", "living-world-web.sqlite3")
    with closing(connect_web(database)):
        pass
    with ThreadingHTTPServer(("127.0.0.1", port), GameHandler) as server:
        server.database = database
        print(f"Живой мир · http://localhost:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
