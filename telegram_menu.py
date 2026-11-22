"""Inline navigation and encounter buttons for Telegram."""
import re

from game import ROUTE_MENU, ROUTES, encounter


MENU = (
    (("Герой", "hero"), ("Походы", "adventure")),
    (("Сумка", "bag"), ("Квесты", "npc"), ("Журнал", "journal")),
)
ACTIONS = {action for row in MENU for _, action in row} | {"adventure_forest", "adventure_ruins", "start"}
CHOICE = re.compile(r"world:choose:([0-9]{1,19}):([12])")


def controls(rows):
    return {"inline_keyboard": [
        [{"text": label, "callback_data": f"world:{action}"} for label, action in row]
        for row in rows
    ]}


def callback_command(db, sender_id, data):
    action = data.removeprefix("world:")
    if data.startswith("world:") and action in ACTIONS:
        return f"/{action}", None
    choice = CHOICE.fullmatch(data)
    if choice:
        active = db.execute("""
            SELECT update_id FROM encounter_controls JOIN heroes USING (user_id)
            WHERE user_id = ? AND route IS NOT NULL
        """, (sender_id,)).fetchone()
        if active and str(active["update_id"]) == choice[1]:
            return f"/choose_{choice[2]}", None
        return "", "Эта кнопка относится к другому или уже завершённому походу."
    return "", "Эта кнопка больше недоступна."


def present(db, user_id, update_id, reply):
    hero = db.execute("SELECT route FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
    route = hero["route"] if hero else None
    if route and reply == encounter(route):
        _, *choices = ROUTES[route]
        db.execute("""
            INSERT INTO encounter_controls VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET update_id = excluded.update_id
        """, (user_id, update_id))
        rows = [
            ((label, f"choose:{update_id}:{number}"),)
            for number, (_, label, _) in enumerate(choices, 1)
        ]
        return reply, controls(rows), route == "forest"
    if reply == ROUTE_MENU:
        rows = (
            (("Туманный лес", "adventure_forest"),),
            (("Старая башня · ур. 2", "adventure_ruins"),),
            (("Главное меню", "start"),),
        )
        return reply, controls(rows), False
    return reply, controls(MENU), False
