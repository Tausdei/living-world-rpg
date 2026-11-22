"""Advance autonomous events using elapsed wall-clock time."""
import random
import time

EVENT_INTERVAL = 30 * 60
MAX_CATCHUP = 24
JOURNAL_SIZE = 30


def init_world(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS world_schedule (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            next_event INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS world_schedule_due ON world_schedule(next_event);
        CREATE TABLE IF NOT EXISTS world_journal (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            occurred_at INTEGER NOT NULL,
            summary TEXT NOT NULL,
            PRIMARY KEY (user_id, occurred_at)
        );
    """)
    with db:
        db.execute("""
            INSERT OR IGNORE INTO world_schedule (user_id, next_event)
            SELECT user_id, ? FROM heroes WHERE user_id NOT IN (SELECT user_id FROM world_schedule)
        """, (int(time.time()) + EVENT_INTERVAL,))


def schedule_hero(db, user_id):
    db.execute("INSERT INTO world_schedule VALUES (?, ?)", (user_id, int(time.time()) + EVENT_INTERVAL))


def combat_stats(hero):
    level = 1 + hero["xp"] // 30
    health = 12 + min(12, level - 1) + min(5, hero["herbalist"] // 3)
    attack = 3 + min(5, hero["scout"] // 3)
    return health, attack


def fight_stats(health, attack, rng, enemy_hp, enemy_attack):
    while health > 0:
        enemy_hp -= attack + rng.randint(0, 2)
        if enemy_hp <= 0:
            return True
        health -= enemy_attack + rng.randint(0, 2)
    return False


def resolve_event(hero, rng):
    event = rng.randrange(4)
    if event == 0:
        return "Ты нашёл лечебные травы у ручья.", 5, 2, 0, 1
    if event == 1:
        return "Ты вывел заблудившегося путника к дороге.", 6, 3, 1, 0

    enemy, hp, attack = ("лесным волком", 10, 3) if event == 2 else ("курганным призраком", 16, 4)
    if fight_stats(*combat_stats(hero), rng, hp, attack):
        return f"Ты победил в бою с {enemy}.", 10, 5, 1, 0
    return f"Ты отступил после боя с {enemy}.", 3, 0, 1, 0


def advance_hero(db, user_id, now, rng=random):
    scheduled = db.execute("SELECT next_event FROM world_schedule WHERE user_id = ?", (user_id,)).fetchone()
    if scheduled is None or scheduled["next_event"] > now:
        return
    first = scheduled["next_event"]
    due = (now - first) // EVENT_INTERVAL + 1
    first += max(0, due - MAX_CATCHUP) * EVENT_INTERVAL
    for occurred_at in range(first, now + 1, EVENT_INTERVAL):
        hero = db.execute("SELECT * FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
        event, xp, coins, scout, herbalist = resolve_event(hero, rng)
        db.execute("""
            UPDATE heroes SET xp = xp + ?, coins = coins + ?,
                scout = scout + ?, herbalist = herbalist + ? WHERE user_id = ?
        """, (xp, coins, scout, herbalist, user_id))
        skill = "Следопыт" if scout else "Травник"
        summary = f"{event} +{xp} опыта, +{coins} монет, +1 очко навыка «{skill}»."
        if (hero["xp"] + xp) // 30 > hero["xp"] // 30:
            summary += f" Новый уровень: {1 + (hero['xp'] + xp) // 30}."
        db.execute("INSERT INTO world_journal VALUES (?, ?, ?)", (user_id, occurred_at, summary))

    db.execute("UPDATE world_schedule SET next_event = ? WHERE user_id = ?", (occurred_at + EVENT_INTERVAL, user_id))
    db.execute("""
        DELETE FROM world_journal WHERE user_id = ? AND occurred_at < (
            SELECT occurred_at FROM world_journal WHERE user_id = ?
            ORDER BY occurred_at DESC LIMIT 1 OFFSET ?
        )
    """, (user_id, user_id, JOURNAL_SIZE - 1))


def advance_world(db, now=None):
    now = int(time.time()) if now is None else now
    due = db.execute("""
        SELECT user_id FROM world_schedule WHERE next_event <= ?
        ORDER BY next_event, user_id LIMIT 100
    """, (now,)).fetchall()
    for hero in due:
        with db:
            db.execute("BEGIN IMMEDIATE")
            advance_hero(db, hero["user_id"], now)
