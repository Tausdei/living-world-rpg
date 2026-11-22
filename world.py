"""Advance autonomous events using elapsed wall-clock time."""
import random
import time

from loot import gear_bonuses, grant_item
from world_events import EVENTS, JOBS, POOLS

EVENT_INTERVAL = 30 * 60
MAX_CATCHUP = 24
JOURNAL_SIZE = 30


def init_world(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS world_schedule (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            next_event INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS world_jobs (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            job TEXT NOT NULL
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


def current_job(db, user_id):
    job = db.execute("SELECT job FROM world_jobs WHERE user_id = ?", (user_id,)).fetchone()
    return job["job"] if job else "roam"


def offline(db, user_id, job):
    if job in JOBS:
        db.execute("""
            INSERT INTO world_jobs VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET job = excluded.job
        """, (user_id, job))
        return f"Фоновое занятие: {JOBS[job][0]}. Оно вступит в силу со следующего события."
    current = JOBS[current_job(db, user_id)][0]
    rows = [f"Фоновое занятие: {current}. События происходят каждые 30 минут."]
    rows.extend(f"/offline_{key} — {name}. {description}" for key, (name, description, _) in JOBS.items())
    return "\n".join(rows)


def resolve_event(hero, rng, job, bonuses):
    description, xp, coins, scout, herbalist, item, enemy = EVENTS[rng.choice(POOLS[job])]
    if enemy:
        hp, attack = combat_stats(hero)
        bonus_hp, bonus_attack = bonuses
        if not fight_stats(hp + bonus_hp, attack + bonus_attack, rng, *enemy):
            return f"Ты отступил после боя с {description}.", 3, 0, 1, 0, None
        description = f"Ты победил в бою с {description}."
    drop = item if item and rng.randrange(5) == 0 else None
    return description, xp, coins, scout, herbalist, drop


def advance_hero(db, user_id, now, rng=random):
    scheduled = db.execute("SELECT next_event FROM world_schedule WHERE user_id = ?", (user_id,)).fetchone()
    if scheduled is None or scheduled["next_event"] > now:
        return
    first = scheduled["next_event"]
    due = (now - first) // EVENT_INTERVAL + 1
    first += max(0, due - MAX_CATCHUP) * EVENT_INTERVAL
    job = current_job(db, user_id)
    bonuses = gear_bonuses(db, user_id)
    for occurred_at in range(first, now + 1, EVENT_INTERVAL):
        hero = db.execute("SELECT * FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
        event, xp, coins, scout, herbalist, item = resolve_event(hero, rng, job, bonuses)
        db.execute("""
            UPDATE heroes SET xp = xp + ?, coins = coins + ?,
                scout = scout + ?, herbalist = herbalist + ? WHERE user_id = ?
        """, (xp, coins, scout, herbalist, user_id))
        skill = "Следопыт" if scout else "Травник"
        summary = f"{event} +{xp} опыта, +{coins} монет, +1 очко навыка «{skill}»."
        if item:
            summary += " " + grant_item(db, user_id, item) + "."
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
