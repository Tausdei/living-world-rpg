"""Rules for the command-driven RPG. Each command runs in a database transaction."""
import re
import sqlite3
import time
from datetime import UTC, datetime

import activities
from world import advance_hero, init_world, schedule_hero


COMMANDS = {
    **activities.COMMANDS,
    "start": "Команды игры",
    "create": "Создать персонажа",
    "journal": "Журнал событий героя",
    "hero": "Посмотреть персонажа",
    "professions": "Посмотреть профессии",
    "train": "Обучиться профессии",
    "adventure": "Выбрать маршрут",
    "choose": "Принять решение в походе",
}
SHORTCUTS = {
    "adventure_forest": ("adventure", "forest"),
    "adventure_ruins": ("adventure", "ruins"),
    "choose_1": ("choose", "1"),
    "choose_2": ("choose", "2"),
    "train_scout": ("train", "scout"),
    "train_herbalist": ("train", "herbalist"),
    "quest_forest": ("quest", "forest"),
    "quest_keeper": ("quest", "keeper"),
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
/journal — что случилось с героем
/professions — навыки
/train_scout или /train_herbalist — обучение
/adventure — маршруты
/choose_1 или /choose_2 — решение в походе
/bag — добыча и снаряжение
/npc — NPC и задания
/boss — Пепельный смотритель
/pvp — дуэли
/raid — рейд на Каменного колосса"""

PROFESSIONS = {"scout": "Следопыт", "herbalist": "Травник"}

ROUTES = {
    "forest": (
        "За мостом затопило тропу. На берегу видны свежие следы.",
        ("scout", "Пойти по следам в обход", 12),
        ("herbalist", "Собрать лунную мяту у воды", 9),
    ),
    "ruins": (
        "В сторожевой башне обрушилась лестница. Из-под плит тянет горьким дымом.",
        ("scout", "Пробраться по обходной галерее", 20),
        ("herbalist", "Приготовить отвар и спуститься через дым", 17),
    ),
}


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
    """)
    db.execute("PRAGMA foreign_keys = ON")
    init_world(db)
    activities.init_activities(db)
    return db


def encounter(route):
    description, *options = ROUTES[route]
    choices = "\n".join(
        f"/choose_{number} — {label} ({PROFESSIONS[skill]})"
        for number, (skill, label, _) in enumerate(options, 1)
    )
    return f"{description}\n{choices}"


def play(db, user_id, message, bot_name=None):
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
    if command in {"/start", "/help"}:
        return HELP

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
        return f"{argument} отправляется в путь. У тебя 10 монет. /adventure · /journal"
    if command.lstrip("/") not in COMMANDS or not command.startswith("/"):
        return "Список команд — /help"
    if hero is None:
        return "Сначала создай героя: /create Имя"

    if command in {"/bag", "/equip"}:
        return activities.inventory(db, hero, argument, equip=command == "/equip")
    if command in {"/npc", "/quest"}:
        return activities.quest(db, user_id, argument if command == "/quest" else "")
    if command == "/boss":
        return activities.boss(db, hero, now)
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
        if route:
            return encounter(route)
        if argument not in ROUTES:
            return "/adventure_forest — Туманный лес\n/adventure_ruins — Старая башня (с уровня 2)"
        if argument == "ruins" and level < 2:
            return "Старая башня откроется на уровне 2."
        db.execute("UPDATE heroes SET route = ? WHERE user_id = ?", (argument, user_id))
        return encounter(argument)

    if not route:
        return "Сначала выбери маршрут. /adventure"
    if argument not in {"1", "2"}:
        return encounter(route)
    skill, _, reward = ROUTES[route][int(argument)]
    difficulty = 0 if route == "forest" else 2
    success = hero[skill] // 3 >= difficulty
    xp = 15 if success else 5
    coins = reward if success else 2
    db.execute(
        f"UPDATE heroes SET route = NULL, xp = xp + ?, coins = coins + ?, {skill} = {skill} + 1 WHERE user_id = ?",
        (xp, coins, user_id),
    )
    loot = ""
    if success:
        if route == "forest":
            activities.record_objective(db, user_id, "forest", 2)
        item = "blade" if route == "ruins" else ("knife" if skill == "scout" else "charm")
        loot = " " + activities.reward(db, user_id, item=item) + ". /bag"
    outcome = "Ты вернулся с добычей." if success else "Не хватило навыка. Ты отступил и сберёг снаряжение."
    new_level = 1 + (hero["xp"] + xp) // 30
    promotion = f" Новый уровень: {new_level}." if new_level > level else ""
    return f"{outcome} +{xp} опыта, +{coins} монет, +1 очко профессии «{PROFESSIONS[skill]}».{promotion}{loot}\n/adventure"
