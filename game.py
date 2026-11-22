"""Rules for the command-driven RPG. Each command runs in a database transaction."""
import re
import sqlite3
import time
from datetime import UTC, datetime

import activities
import campaign
import fieldwork
import practice_games
import town
from adventures import PROFESSIONS, ROUTES, ROUTE_MENU, choose, encounter, init_adventures, region
from art_catalog import GALLERY, TITLES
from lore import LORE
from world import advance_hero, init_world, offline, schedule_hero
from world_events import JOBS


COMMANDS = {
    **activities.COMMANDS,
    "start": "Команды игры",
    "story": "Текущая глава и её цели",
    "town": "Пещера, кузница, турниры и общение",
    "story_claim": "Завершить главу",
    "region": "Описание места перед походом",
    "offline": "Фоновое занятие героя",
    "hunt": "Пошаговая охота",
    "turn": "Действие текущего боя",
    "practice": "Мини-игры профессий",
    "practice_answer": "Действие в мини-игре",
    "create": "Создать персонажа",
    "journal": "Журнал событий героя",
    "hero": "Посмотреть персонажа",
    "gallery": "Галерея иллюстраций",
    "art": "Открыть иллюстрацию по имени",
    "professions": "Посмотреть профессии",
    "train": "Обучиться профессии",
    "adventure": "Выбрать маршрут",
    "choose": "Принять решение в походе",
}
SHORTCUTS = {
    **{f"story_claim_{key}": ("story_claim", key) for key in campaign.CHAPTER_KEYS},
    **{f"region_{key}": ("region", key) for key in ROUTES},
    **{f"offline_{job}": ("offline", job) for job in JOBS},
    **{f"hunt_{enemy}": ("hunt", enemy) for enemy in fieldwork.ENEMIES},
    **{f"turn_{action}": ("turn", action) for action in fieldwork.HUNT_ACTIONS},
    **{f"practice_{skill}": ("practice", skill) for skill in practice_games.SKILLS},
    **{f"practice_answer_{choice}": ("practice_answer", choice) for choice in practice_games.ACTIONS},
    **{f"adventure_{key}": ("adventure", key) for key in ROUTES},
    "choose_1": ("choose", "1"),
    "choose_2": ("choose", "2"),
    **{f"choose_{key}": ("choose", key) for key in ("leave", "aid", "risk")},
    "train_scout": ("train", "scout"),
    "train_herbalist": ("train", "herbalist"),
    **{f"quest_{key}": ("quest", key) for key in activities.QUESTS},
    "raid_open": ("raid", "open"),
    "raid_start": ("raid", "start"),
    "raid_leave": ("raid", "leave"),
    "pvp_decline": ("pvp", "decline"),
    **{f"equip_{item}": ("equip", item) for item in activities.ITEMS},
}
INVITE_COMMAND = re.compile(r"/(raid_join|pvp_accept)_([0-9]{1,18})")

HELP = """Живой мир
/create Имя — создать героя
/hero — уровень, опыт и монеты
/story — глава, цели и награда
/town — пещера, кузница, турниры и общение
/journal — что случилось с героем
/professions — навыки
/train_scout или /train_herbalist — обучение
/adventure — маршруты
/choose_1 или /choose_2 — решение в походе
/bag — добыча и снаряжение
/npc — NPC и задания
/boss — Пепельный смотритель
/pvp — дуэли
/raid — рейд на Каменного колосса
/offline — выбрать фоновое занятие
/hunt — пошаговые бои
/practice — мини-игры профессий
/gallery — иллюстрации мира"""

def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS heroes (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            coins INTEGER NOT NULL DEFAULT 10,
            scout INTEGER NOT NULL DEFAULT 0,
            herbalist INTEGER NOT NULL DEFAULT 0,
            route TEXT
        );
        CREATE TABLE IF NOT EXISTS delivery (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            next_offset INTEGER NOT NULL DEFAULT 0,
            chat_id INTEGER,
            reply TEXT
        );
        INSERT OR IGNORE INTO delivery (id) VALUES (1);
        CREATE TABLE IF NOT EXISTS delivery_controls (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS encounter_controls (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            update_id INTEGER NOT NULL
        );
    """)
    db.execute("PRAGMA foreign_keys = ON")
    init_world(db)
    activities.init_activities(db)
    fieldwork.init_fieldwork(db)
    init_adventures(db)
    practice_games.init_practice(db)
    campaign.init_campaign(db)
    town.init_town(db)
    return db


def parse_command(message, bot_name=None):
    parts = message.strip().split(maxsplit=1)
    if not parts:
        return None
    command, *args = parts
    command, _, mention = command.lower().partition("@")
    if mention and mention != bot_name:
        return None
    argument = args[0] if args else ""
    if command.startswith("/") and command[1:] in SHORTCUTS:
        base, argument = SHORTCUTS[command[1:]]
        command = f"/{base}"
    elif invite := INVITE_COMMAND.fullmatch(command):
        base, action = invite[1].split("_")
        command, argument = f"/{base}", f"{action} {invite[2]}"
    return command, argument


def play(db, user_id, message, bot_name=None):
    parsed = parse_command(message, bot_name)
    if parsed is None:
        return None
    command, argument = parsed
    if command == "/help":
        return HELP
    if command == "/start":
        hero = db.execute("SELECT name FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
        if not hero:
            return "Живой мир\nСоздай героя, чтобы начать историю. Введи /create и имя, например: /create Лира"
        return f"Живой мир · {hero['name']}\nВыбери, что продолжить. Полный список команд — /help."
    if command == "/gallery":
        title, entries = GALLERY.get(argument, ("Галерея Живого мира", {}))
        if entries:
            return title + "\n" + "\n".join(f"{name} · /art {key}" for key, name in entries.items())
        return title + "\n" + "\n".join(f"{name} · /gallery {key}" for key, (name, _) in GALLERY.items())
    if command == "/art":
        title = TITLES.get(argument)
        if title is None:
            return "Выбери иллюстрацию в /gallery."
        note = LORE.get(argument)
        return f"{title}\n\n{note}" if note else title

    if command == "/region":
        return region(argument)

    now = int(time.time())
    advance_hero(db, user_id, now)
    hero = db.execute("SELECT * FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
    if command == "/create":
        if hero:
            return "У тебя уже есть персонаж. /hero"
        if not re.fullmatch(r"[\w -]{2,24}", argument):
            return "Введи /create Имя. Допустимы 2–24 буквы, цифры, пробелы, дефисы или подчёркивания."
        db.execute("INSERT INTO heroes (user_id, name) VALUES (?, ?)", (user_id, argument))
        schedule_hero(db, user_id)
        return f"{argument} отправляется в путь. У тебя 10 монет. Продолжить историю: /story"
    if command.lstrip("/") not in COMMANDS or not command.startswith("/"):
        return "Список команд — /help"
    if hero is None:
        return "Сначала создай героя: /create Имя"

    if command == "/town":
        result = town.handle(db, hero, argument, now)
        current = db.execute("SELECT * FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
        text = town.town_text(town.panel(db, current, argument, now))
        return f"{result}\n\n{text}" if result else text
    if command in {"/story", "/story_claim"}:
        return campaign.story(db, user_id, argument if command == "/story_claim" else None)
    if command in {"/bag", "/equip"}:
        return activities.inventory(db, hero, argument, equip=command == "/equip")
    if command in {"/npc", "/quest"}:
        return activities.quest(db, user_id, argument if command == "/quest" else "")
    if command == "/offline":
        return offline(db, user_id, argument)
    if command in {"/hunt", "/boss"}:
        return fieldwork.hunt(db, hero, argument if command == "/hunt" else "keeper", now)
    if command == "/turn":
        return fieldwork.turn(db, hero, argument, now)
    if command == "/practice":
        return practice_games.practice(db, hero, argument, now)
    if command == "/practice_answer":
        return practice_games.answer(db, hero, argument, now)
    if command == "/raid":
        return activities.raid(db, hero, argument, now)
    if command == "/pvp":
        return activities.duel(db, hero, argument, now)

    if command == "/journal":
        entries = db.execute("""
            SELECT occurred_at, summary FROM world_journal WHERE user_id = ?
            ORDER BY occurred_at DESC LIMIT 8
        """, (user_id,)).fetchall()
        if not entries:
            return "Журнал пока пуст. Первое событие случится через 30 минут после создания героя."
        lines = []
        for entry in entries:
            date = datetime.fromtimestamp(entry["occurred_at"], UTC).strftime("%d.%m %H:%M")
            lines.append(f"{date} UTC · {entry['summary']}")
        return "Журнал героя\n" + "\n".join(lines)

    level = 1 + hero["xp"] // 30
    if command == "/hero":
        return f'{hero["name"]} · уровень {level}\nОпыт до следующего уровня: {30 - hero["xp"] % 30}\nМонеты: {hero["coins"]}'
    if command == "/professions":
        skills = "\n".join(f"{label}: ранг {hero[key] // 3} · {hero[key]} очков" for key, label in PROFESSIONS.items())
        return f"{skills}\nТренировка стоит 5 монет и даёт 1 очко. Каждые 3 очка повышают ранг."
    if command == "/train":
        if hero["route"]:
            return "Сначала закончи поход. /adventure"
        if argument not in PROFESSIONS:
            return "/train_scout — следопыт\n/train_herbalist — травник"
        if hero["coins"] < 5:
            return "Для тренировки нужно 5 монет."
        db.execute(f"UPDATE heroes SET {argument} = {argument} + 1, coins = coins - 5 WHERE user_id = ?", (user_id,))
        return f"{PROFESSIONS[argument]}: +1 очко навыка. /professions"

    route = hero["route"]
    if command == "/adventure":
        if fieldwork.active_hunt(db, user_id):
            return "Сначала закончи текущий бой. /hunt"
        if route:
            return encounter(db, user_id, route)
        if argument not in ROUTES:
            return ROUTE_MENU
        place = ROUTES[argument]
        if level < place.level:
            return f"«{place.title}» откроется на уровне {place.level}."
        db.execute("UPDATE heroes SET route = ? WHERE user_id = ?", (argument, user_id))
        return encounter(db, user_id, argument)

    return choose(db, hero, argument)
