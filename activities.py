"""Loot, quests and multiplayer activities for the Telegram RPG."""
import random
import time

from world import advance_hero, combat_stats, fight_stats


ITEMS = {
    "knife": ("Походный нож", "weapon", 1),
    "blade": ("Клинок стражи", "weapon", 3),
    "charm": ("Плетёный оберег", "charm", 2),
    "seal": ("Печать смотрителя", "charm", 4),
    "star": ("Осколок звезды", "charm", 6),
}
COMMANDS = {
    "bag": "Добыча и экипировка",
    "equip": "Надеть предмет",
    "npc": "Поговорить с NPC",
    "quest": "Принять задание или получить награду",
    "boss": "Бросить вызов боссу",
    "raid": "Создать рейд или вступить в отряд",
    "pvp": "Дуэли по согласию",
}
INVITE_SECONDS = 600


def init_activities(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS loot (
            hero_id INTEGER NOT NULL REFERENCES heroes(user_id),
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            PRIMARY KEY (hero_id, item)
        );
        CREATE TABLE IF NOT EXISTS equipped (
            hero_id INTEGER NOT NULL REFERENCES heroes(user_id),
            slot TEXT NOT NULL,
            item TEXT NOT NULL,
            PRIMARY KEY (hero_id, slot),
            FOREIGN KEY (hero_id, item) REFERENCES loot(hero_id, item)
        );
        CREATE TABLE IF NOT EXISTS quest_progress (
            hero_id INTEGER NOT NULL REFERENCES heroes(user_id),
            quest TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (hero_id, quest)
        );
        CREATE TABLE IF NOT EXISTS boss_victory (
            hero_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            day INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS raid_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader INTEGER NOT NULL REFERENCES heroes(user_id),
            closed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS raid_members (
            hero_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            room INTEGER NOT NULL REFERENCES raid_rooms(id)
        );
        CREATE TABLE IF NOT EXISTS raid_victory (
            hero_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            day INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS duel_invites (
            target INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            challenger INTEGER NOT NULL REFERENCES heroes(user_id),
            expires INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS duel_record (
            hero_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0
        );
    """)


def reward(db, hero_id, xp=0, coins=0, item=None):
    description = ""
    if xp or coins:
        db.execute("UPDATE heroes SET xp = xp + ?, coins = coins + ? WHERE user_id = ?", (xp, coins, hero_id))
        description = f"+{xp} опыта, +{coins} монет"
    if item:
        db.execute("""
            INSERT INTO loot VALUES (?, ?, 1)
            ON CONFLICT (hero_id, item) DO UPDATE SET quantity = quantity + 1
        """, (hero_id, item))
        description += f"{', ' if description else ''}добыча: {ITEMS[item][0]} ({item})"
    return description


def record_objective(db, hero_id, quest, target):
    db.execute("""
        UPDATE quest_progress SET progress = MIN(progress + 1, ?)
        WHERE hero_id = ? AND quest = ? AND claimed = 0
    """, (target, hero_id, quest))


def inventory(db, hero, argument, equip=False):
    hero_id = hero["user_id"]
    if equip:
        if argument not in ITEMS or not db.execute(
            "SELECT 1 FROM loot WHERE hero_id = ? AND item = ?", (hero_id, argument)
        ).fetchone():
            return "Выбери предмет, который у тебя есть. /bag"
        name, slot, _ = ITEMS[argument]
        db.execute("""
            INSERT INTO equipped VALUES (?, ?, ?)
            ON CONFLICT (hero_id, slot) DO UPDATE SET item = excluded.item
        """, (hero_id, slot, argument))
        return f"Надето: {name}."
    rows = db.execute("""
        SELECT loot.*, equipped.item IS NOT NULL AS worn FROM loot
        LEFT JOIN equipped USING (hero_id, item) WHERE hero_id = ? ORDER BY loot.item
    """, (hero_id,)).fetchall()
    if not rows:
        return "Сумка пуста. Первые предметы можно найти в походе."
    lines = ["Сумка"]
    for row in rows:
        item = row["item"]
        name, slot, bonus = ITEMS[item]
        stat = "урону" if slot == "weapon" else "здоровью"
        worn = " · надето" if row["worn"] else ""
        lines.append(f"{name} ×{row['quantity']} · +{bonus} к {stat}{worn} · /equip {item}")
    return "\n".join(lines)


def quest(db, hero_id, argument):
    quests = {
        "forest": ("Дозорница Мира", "Дважды успешно вернись из Туманного леса.", 2, 20, 15, "charm"),
        "keeper": ("Архивист Орин", "Победи Пепельного смотрителя.", 1, 30, 25, None),
    }
    if not argument:
        return "\n".join(f"{npc}: {goal} /quest {key}" for key, (npc, goal, *_) in quests.items())
    if argument not in quests:
        return "Доступные задания: /npc"
    npc, goal, target, xp, coins, item = quests[argument]
    row = db.execute("SELECT * FROM quest_progress WHERE hero_id = ? AND quest = ?", (hero_id, argument)).fetchone()
    if row is None:
        db.execute("INSERT INTO quest_progress (hero_id, quest) VALUES (?, ?)", (hero_id, argument))
        return f"{npc}: «{goal}» Принято (0/{target})."
    if row["claimed"]:
        return "Задание завершено, награда уже получена."
    if row["progress"] < target:
        return f"{npc}: {goal} Готово: {row['progress']}/{target}."
    db.execute("UPDATE quest_progress SET claimed = 1 WHERE hero_id = ? AND quest = ?", (hero_id, argument))
    return f"{npc} вручает награду: {reward(db, hero_id, xp, coins, item)}."


def stats(db, hero):
    health, attack = combat_stats(hero)
    for row in db.execute("SELECT item FROM equipped WHERE hero_id = ?", (hero["user_id"],)):
        _, slot, bonus = ITEMS[row["item"]]
        if slot == "weapon":
            attack += bonus
        else:
            health += bonus
    return health, attack


def boss(db, hero, now):
    hero_id = hero["user_id"]
    if hero["xp"] < 30:
        return "Пепельный смотритель доступен с уровня 2."
    day = now // 86400
    if db.execute("SELECT 1 FROM boss_victory WHERE hero_id = ? AND day = ?", (hero_id, day)).fetchone():
        return "Пепельный смотритель уже побеждён сегодня. Он вернётся в полночь UTC."
    if not fight_stats(*stats(db, hero), random, 19, 4):
        return "Пепельный смотритель отбил атаку. Потренируйся, надень снаряжение и попробуй ещё раз."
    db.execute("INSERT INTO boss_victory VALUES (?, ?) ON CONFLICT (hero_id) DO UPDATE SET day = excluded.day", (hero_id, day))
    record_objective(db, hero_id, "keeper", 1)
    return f"Пепельный смотритель повержен. {reward(db, hero_id, 22, 20, 'seal')}."


def numeric_id(value):
    if value.isascii() and value.isdecimal() and len(value) <= 18:
        return int(value)
    return None


def raid(db, hero, argument, now):
    hero_id = hero["user_id"]
    action, _, code = argument.partition(" ")
    room = db.execute("""
        SELECT raid_rooms.* FROM raid_rooms JOIN raid_members ON raid_members.room = raid_rooms.id
        WHERE raid_members.hero_id = ?
    """, (hero_id,)).fetchone()
    if not action:
        current = f"Твой отряд: {room['id']}.\n" if room else ""
        return current + "Каменный колосс (ур. 3, 2–4 героя)\n/raid open · /raid join НОМЕР · /raid start · /raid leave"
    day = now // 86400
    if action in {"open", "join"}:
        if hero["xp"] < 60:
            return "Рейд доступен с уровня 3."
        if db.execute("SELECT 1 FROM raid_victory WHERE hero_id = ? AND day = ?", (hero_id, day)).fetchone():
            return "Награда за Колосса уже получена сегодня. Возвращайся после полуночи UTC."
        if room:
            return f"Ты уже в отряде {room['id']}. /raid leave"
        if action == "open":
            room_id = db.execute("INSERT INTO raid_rooms (leader) VALUES (?)", (hero_id,)).lastrowid
        else:
            room_id = numeric_id(code.strip())
            if not db.execute("SELECT 1 FROM raid_rooms WHERE id = ? AND closed = 0", (room_id,)).fetchone():
                return "Открытый отряд с таким номером не найден."
            if db.execute("SELECT COUNT(*) FROM raid_members WHERE room = ?", (room_id,)).fetchone()[0] >= 4:
                return "В отряде уже четыре героя."
        db.execute("INSERT INTO raid_members VALUES (?, ?)", (hero_id, room_id))
        return f"Ты в отряде {room_id}. Приглашение: /raid join {room_id}. Лидер начинает через /raid start."
    if action not in {"leave", "start"}:
        return "Команды рейда: /raid"
    if not room:
        return "Сначала вступи в отряд. /raid"
    room_id = room["id"]
    if action == "leave":
        if room["leader"] == hero_id:
            close_raid(db, room_id)
            return "Лидер распустил отряд."
        db.execute("DELETE FROM raid_members WHERE hero_id = ?", (hero_id,))
        return "Ты вышел из отряда."
    if room["leader"] != hero_id:
        return "Начать бой может лидер."
    members = db.execute("SELECT hero_id FROM raid_members WHERE room = ? ORDER BY hero_id", (room_id,)).fetchall()
    count = len(members)
    if count < 2:
        return "Для боя нужны минимум два героя."
    total_hp = total_attack = 0
    for member in members:
        member_id = member["hero_id"]
        advance_hero(db, member_id, now)
        participant = db.execute("SELECT * FROM heroes WHERE user_id = ?", (member_id,)).fetchone()
        hp, attack = stats(db, participant)
        total_hp += hp
        total_attack += attack
    close_raid(db, room_id)
    if not fight_stats(total_hp, total_attack, random, 16 + 13 * count, 6 * count):
        return "Колосс выдержал атаку. Отряд отступил. Можно собрать новый отряд."
    for member in members:
        member_id = member["hero_id"]
        db.execute("INSERT INTO raid_victory VALUES (?, ?) ON CONFLICT (hero_id) DO UPDATE SET day = excluded.day", (member_id, day))
        prize = reward(db, member_id, 30, 25, "star")
    return f"Каменный колосс побеждён. Каждый из {count} участников получает {prize}."


def close_raid(db, room_id):
    db.execute("DELETE FROM raid_members WHERE room = ?", (room_id,))
    db.execute("UPDATE raid_rooms SET closed = 1 WHERE id = ?", (room_id,))


def duel(db, hero, argument, now):
    hero_id = hero["user_id"]
    action, _, code = argument.partition(" ")
    if not action:
        record = db.execute("SELECT * FROM duel_record WHERE hero_id = ?", (hero_id,)).fetchone()
        score = f"{record['wins']} побед / {record['losses']} поражений" if record else "0 побед / 0 поражений"
        invite = db.execute("SELECT challenger FROM duel_invites WHERE target = ? AND expires > ?", (hero_id, now)).fetchone()
        pending = f"\nВходящий вызов: /pvp accept {invite['challenger']}" if invite else ""
        return f"Твой ID: {hero_id} · {score}\n/pvp challenge ID · /pvp accept ID · /pvp decline{pending}"
    if action == "decline":
        db.execute("DELETE FROM duel_invites WHERE target = ?", (hero_id,))
        return "Входящий вызов отклонён."
    other_id = numeric_id(code.strip())
    other = db.execute("SELECT * FROM heroes WHERE user_id = ?", (other_id,)).fetchone()
    if other is None or other_id == hero_id:
        return "Укажи ID другого героя. Его можно посмотреть командой /pvp."
    if action == "challenge":
        db.execute("DELETE FROM duel_invites WHERE expires <= ?", (now,))
        if db.execute("SELECT 1 FROM duel_invites WHERE challenger = ? OR target = ?", (hero_id, other_id)).fetchone():
            return "У тебя уже есть исходящий вызов или у соперника занят входящий слот. Вызовы действуют 10 минут."
        db.execute("INSERT INTO duel_invites VALUES (?, ?, ?)", (other_id, hero_id, now + INVITE_SECONDS))
        return f"Вызов для {other['name']}. Передай сопернику команду /pvp accept {hero_id}."
    if action != "accept":
        return "Команды дуэли: /pvp"
    invite = db.execute("""
        DELETE FROM duel_invites WHERE target = ? AND challenger = ? AND expires > ?
    """, (hero_id, other_id, now)).rowcount
    if not invite:
        return "Активного вызова от этого героя нет."
    advance_hero(db, other_id, now)
    other = db.execute("SELECT * FROM heroes WHERE user_id = ?", (other_id,)).fetchone()
    fighters = [hero, other]
    random.shuffle(fighters)
    first, second = fighters
    hp, attack = stats(db, first)
    other_hp, other_attack = stats(db, second)
    winner, loser = (first, second) if fight_stats(hp, attack, random, other_hp, other_attack) else (second, first)
    for fighter, wins in ((winner, 1), (loser, 0)):
        db.execute("""
            INSERT INTO duel_record VALUES (?, ?, ?) ON CONFLICT (hero_id) DO UPDATE SET
            wins = wins + excluded.wins, losses = losses + excluded.losses
        """, (fighter["user_id"], wins, 1 - wins))
    return f"Дуэль: {hero['name']} против {other['name']}. Победа: {winner['name']}."
