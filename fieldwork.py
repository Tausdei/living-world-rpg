"""Persistent turn-based hunts and shared activity cooldowns."""
import random
from secrets import token_hex

from activities import record_objective, reward, stats


HUNT_DELAY = 180
PRACTICE_DELAY = 900
HUNT_ACTIONS = {
    "strike": "Ударить",
    "guard": "Защита и контратака",
    "heal": "Лечебный настой",
    "retreat": "Отступить",
}
# Name, level, health, damage, experience, coins, guaranteed item.
ENEMIES = {
    "wolf": ("Лесной волк", 1, 10, 2, 10, 5, "fang"),
    "boar": ("Дикий кабан", 1, 13, 2, 12, 6, "vest"),
    "bandit": ("Лесной разбойник", 2, 18, 3, 16, 10, "spear"),
    "ghost": ("Курганный призрак", 3, 23, 4, 20, 12, "lantern"),
    "keeper": ("Пепельный смотритель", 2, 24, 4, 22, 20, "seal"),
}


def init_fieldwork(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS hunts (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            enemy TEXT NOT NULL,
            hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            foe_hp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            turn INTEGER NOT NULL,
            used_heal INTEGER NOT NULL,
            token TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fieldwork_cooldowns (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            activity TEXT NOT NULL,
            ready_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, activity)
        );
    """)


def active_hunt(db, user_id):
    return db.execute("SELECT * FROM hunts WHERE user_id = ?", (user_id,)).fetchone()


def wait_seconds(db, user_id, activity, now):
    row = db.execute("""
        SELECT ready_at FROM fieldwork_cooldowns WHERE user_id = ? AND activity = ?
    """, (user_id, activity)).fetchone()
    return max(0, row["ready_at"] - now) if row else 0


def set_cooldown(db, user_id, activity, ready_at):
    db.execute("""
        INSERT INTO fieldwork_cooldowns VALUES (?, ?, ?)
        ON CONFLICT (user_id, activity) DO UPDATE SET ready_at = excluded.ready_at
    """, (user_id, activity, ready_at))


def hunt_scene(state):
    name = ENEMIES[state["enemy"]][0]
    heavy = state["turn"] % 3 == 0
    warning = "⚠️ Противник готовит сильный удар." if heavy else "Противник готовит обычную атаку."
    heal = "Настой уже использован." if state["used_heal"] else "/turn_heal — выпить настой (раз за бой)"
    return (f"{name} · ход {state['turn']}\n"
            f"Здоровье героя: {state['hp']}/{state['max_hp']} · противника: {state['foe_hp']}\n"
            f"{warning}\n/turn_strike · /turn_guard · /turn_retreat\n{heal}")


def hunt(db, hero, enemy, now):
    user_id = hero["user_id"]
    state = active_hunt(db, user_id)
    if state:
        return hunt_scene(state)
    if enemy not in ENEMIES:
        rows = [f"/hunt_{key} — {name}, ур. {level}" for key, (name, level, *_) in ENEMIES.items()]
        return "Пошаговая охота\n" + "\n".join(rows)
    if hero["route"]:
        return "Закончи текущий поход, затем возвращайся на охоту. /adventure"
    name, level, foe_hp, *_ = ENEMIES[enemy]
    if hero["xp"] // 30 + 1 < level:
        return f"«{name}» доступен с уровня {level}."
    if enemy == "keeper":
        if db.execute("SELECT 1 FROM boss_victory WHERE hero_id = ? AND day = ?", (user_id, now // 86400)).fetchone():
            return "Пепельный смотритель уже побеждён сегодня. Он вернётся в полночь UTC."
    remaining = wait_seconds(db, user_id, "hunt", now)
    if remaining:
        return f"Отдохни после боя. Следующая охота через {remaining} сек."
    hp, attack = stats(db, hero)
    db.execute("INSERT INTO hunts VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)",
               (user_id, enemy, hp, hp, foe_hp, attack, token_hex(5)))
    return hunt_scene(active_hunt(db, user_id))


def end_hunt(db, user_id, now):
    db.execute("DELETE FROM hunts WHERE user_id = ?", (user_id,))
    set_cooldown(db, user_id, "hunt", now + HUNT_DELAY)


def turn(db, hero, action, now, rng=random):
    user_id = hero["user_id"]
    state = active_hunt(db, user_id)
    if not state:
        return "Активного боя нет. Выбери противника: /hunt"
    if action == "retreat":
        end_hunt(db, user_id, now)
        return "Ты отступил и сохранил снаряжение. /hunt"
    if action not in HUNT_ACTIONS:
        return hunt_scene(state)

    key = state["enemy"]
    name, _, _, base_damage, xp, coins, item = ENEMIES[key]
    foe_hp, hp, used_heal = state["foe_hp"], state["hp"], state["used_heal"]
    enemy_damage = base_damage + rng.randint(0, 1)
    if state["turn"] % 3 == 0:
        enemy_damage += 3
    if action == "heal":
        if used_heal or hp == state["max_hp"]:
            return "Настой уже использован или здоровье полное.\n" + hunt_scene(state)
        restored = min(state["max_hp"] - hp, 7)
        hp += restored
        used_heal = 1
        log = f"Настой восстановил {restored} здоровья."
    elif action == "guard":
        enemy_damage = max(1, enemy_damage // 3)
        counter = max(1, state["attack"] // 2)
        foe_hp -= counter
        log = f"Ты укрылся и нанёс {counter} урона контратакой."
    else:
        damage = state["attack"] + rng.randint(0, 2)
        foe_hp -= damage
        log = f"Ты нанёс {damage} урона."

    if foe_hp <= 0:
        end_hunt(db, user_id, now)
        if key == "keeper":
            db.execute("""
                INSERT INTO boss_victory VALUES (?, ?)
                ON CONFLICT (hero_id) DO UPDATE SET day = excluded.day
            """, (user_id, now // 86400))
            record_objective(db, user_id, "keeper", 1)
        return f"{log}\nПобеда над противником «{name}». {reward(db, user_id, xp, coins, item)}."
    hp -= enemy_damage
    log += f" Противник нанёс {enemy_damage} урона."
    if hp <= 0:
        end_hunt(db, user_id, now)
        return f"{log}\nТы потерпел поражение и вернулся в лагерь. /hunt"
    db.execute("""
        UPDATE hunts SET hp = ?, foe_hp = ?, turn = turn + 1, used_heal = ?, token = ? WHERE user_id = ?
    """, (hp, foe_hp, used_heal, token_hex(5), user_id))
    return log + "\n" + hunt_scene(active_hunt(db, user_id))
