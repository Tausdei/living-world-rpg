"""Inline navigation and illustrated responses for Telegram."""
import re

from activities import QUESTS
from loot import ITEMS
from art_catalog import (
    CHOICE_ART, GALLERY, QUEST_ART, ROUTE_ART, SCREEN_ART, TITLES, event_illustration,
)
from fieldwork_menu import ACTIONS as FIELDWORK_ACTIONS, fieldwork_view, step_command
from adventures import ROUTE_MENU, ROUTES, current_scene, detour_state, encounter
from campaign import CHAPTER_KEYS, story_state


MENU = (
    (("История", "story"), ("Герой", "hero"), ("Походы", "adventure")),
    (("Сумка", "bag"), ("Квесты", "npc"), ("Журнал", "journal")),
    (("В отсутствие", "offline"), ("Мини-игры", "practice"), ("Галерея", "gallery")),
)
ACTIONS = FIELDWORK_ACTIONS | {action for row in MENU for _, action in row} | {
    *(f"adventure_{key}" for key in ROUTES),
    *(f"region_{key}" for key in ROUTES),
    *(f"story_claim_{key}" for key in CHAPTER_KEYS),
    "start", "professions",
    *(f"quest_{key}" for key in QUESTS),
    "train_scout", "train_herbalist",
    "boss", "raid", "pvp",
    *{f"equip_{item}" for item in ITEMS},
}
CHOICE = re.compile(r"world:choose:([0-9]{1,19}):([12]|leave|aid|risk)")
BACK = (("Главное меню", "start"),)


def controls(rows):
    return {"inline_keyboard": [
        [{"text": label, "callback_data": f"world:{action}"} for label, action in row]
        for row in rows
    ]}


def callback_command(db, sender_id, data):
    if not data.startswith("world:"):
        return "", "Эта кнопка больше недоступна."
    action = data.removeprefix("world:")
    if action in ACTIONS:
        return f"/{action}", None
    kind, _, key = action.partition(":")
    if (kind == "gallery" and key in GALLERY) or (kind == "art" and key in TITLES):
        return f"/{kind} {key}", None
    step = step_command(db, sender_id, action)
    if step is not None:
        return step
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


def gallery_controls(section):
    if section in GALLERY:
        _, entries = GALLERY[section]
        rows = [((name, f"art:{key}"),) for key, name in entries.items()]
        return controls([*rows, (("Все разделы", "gallery"),), BACK])
    rows = [((name, f"gallery:{key}"),) for key, (name, _) in GALLERY.items()]
    return controls([*rows, BACK])


def journal_illustrations(db, user_id):
    entries = db.execute("""
        SELECT summary FROM world_journal WHERE user_id = ?
        ORDER BY occurred_at DESC LIMIT 8
    """, (user_id,))
    keys = {}
    for entry in entries:
        key = event_illustration(entry["summary"])
        if key:
            keys[key] = None
    return list(keys)


def present(db, user_id, update_id, reply, command, argument, route_before=None, subject_before=None):
    hero = db.execute("SELECT route FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
    route = hero["route"] if hero else None
    if route and command in {"/adventure", "/choose"} and reply.endswith(encounter(db, user_id, route)):
        index, scene, prepared = current_scene(db, user_id, route)
        _, _, detour = detour_state(db, user_id, route, index, prepared)
        db.execute("""
            INSERT INTO encounter_controls VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET update_id = excluded.update_id
        """, (user_id, update_id))
        rows = [
            ((option.title, f"choose:{update_id}:{number}"),)
            for number, option in enumerate(scene.options, 1)
        ]
        if detour:
            if detour["aid_available"]:
                rows.append(((f"{detour['aid']} · {detour['cost']} монет", f"choose:{update_id}:aid"),))
            rows.append(((f"{detour['risk']} · риск", f"choose:{update_id}:risk"),))
        rows.append((("Вернуться", f"choose:{update_id}:leave"),))
        return controls(rows), ROUTE_ART[route]
    if reply == ROUTE_MENU:
        rows = (
            *(((f"{area.title} · ур. {area.level}", f"region_{key}"),) for key, area in ROUTES.items()),
            (("Пошаговая охота", "hunt"), ("Одиночный босс", "boss")),
            (("Рейды", "raid"), ("Дуэли", "pvp")),
            BACK,
        )
        return controls(rows), "village"

    if command in {"/story", "/story_claim"} and hero:
        current = story_state(db, user_id)["current"]
        story_rows = []
        if current:
            if current["ready"]:
                story_rows.append((("Завершить главу", f"story_claim_{current['key']}"),))
            else:
                for goal in current["goals"]:
                    if not goal["done"]:
                        story_rows.append(((goal["label"], goal["command"]),))
        art = current["art"] if current else "village"
        return controls([*story_rows, BACK]), art
    if command == "/region" and argument in ROUTES:
        rows = [(("Отправиться", f"adventure_{argument}"),),
                (("Все походы", "adventure"), ("Профессии", "professions")), BACK]
        return controls(rows), ROUTES[argument].art

    fieldwork = fieldwork_view(db, user_id, command, argument, subject_before)
    if fieldwork:
        fieldwork_rows, fieldwork_art = fieldwork
        return controls([*fieldwork_rows, BACK]), fieldwork_art
    if command == "/adventure" and reply == "Сначала закончи текущий бой. /hunt":
        return controls([(("Вернуться в бой", "hunt"),), BACK]), "patrol"
    art = SCREEN_ART.get(command)
    rows = MENU
    if command == "/gallery":
        return gallery_controls(argument), "village" if argument not in GALLERY else None
    if command == "/art":
        art = argument if argument in TITLES else None
        rows = [(("Галерея", "gallery"),), BACK]
        if argument in ITEMS and db.execute(
            "SELECT 1 FROM loot WHERE hero_id = ? AND item = ?", (user_id, argument)
        ).fetchone():
            rows.insert(0, (("Надеть", f"equip_{argument}"),))
        return controls(rows), art
    if command == "/choose" and route_before:
        art = CHOICE_ART.get(route_before, {}).get(argument, ROUTE_ART[route_before])
        rows = ((("Походы", "adventure"), ("Сумка", "bag")), (("История", "story"),), BACK)
    if command == "/adventure" and argument in ROUTE_ART:
        art = ROUTE_ART[argument]
    if command == "/npc" or (command == "/quest" and not argument):
        quest_rows = [((ROUTES[key].title if key in ROUTES else "Пепельный смотритель", f"quest_{key}"),)
                      for key in QUESTS]
        rows = (*quest_rows, BACK)
    if command == "/quest":
        art = QUEST_ART.get(argument, art)
    if command == "/hero":
        rows = ((("Профессии", "professions"),), *MENU)
    if command in {"/professions", "/train"}:
        rows = (
            (("Следопыт", "art:scout"), ("Травник", "art:herbalist")),
            (("Тренировать следопыта", "train_scout"),),
            (("Тренировать травника", "train_herbalist"),),
            (("Мини-игры", "practice"),),
            BACK,
        )
        if command == "/train" and argument in {"scout", "herbalist"}:
            art = argument
    if command == "/journal":
        recent = journal_illustrations(db, user_id)
        if recent:
            art = recent[0]
            event_rows = [((TITLES[key], f"art:{key}"),) for key in recent]
            rows = (*event_rows, *MENU)
    if command == "/bag":
        items = db.execute("SELECT item FROM loot WHERE hero_id = ? ORDER BY item", (user_id,)).fetchall()
        item_rows = [((TITLES[item["item"]], f"art:{item['item']}"),) for item in items]
        rows = (*item_rows, *MENU)
    if command == "/equip" and argument in ITEMS:
        art = argument
    return controls(rows), art
