"""Resource expeditions, equipment upgrades and character boosts."""
import random
import time

from loot import ITEMS, grant_item


MATERIALS = {"ore": "Руда", "herbs": "Травы", "runes": "Руны", "marks": "Знаки", "gold": "Золото"}
POTIONS = {
    "might": ("Настой силы", "На час даёт +2 к урону.", 2),
    "ward": ("Настой защиты", "На час даёт +5 здоровья.", 2),
    "insight": ("Настой прозрения", "На час даёт +50% опыта за действия.", 3),
}
CAVE = {
    "ore": ("Каменоломня", 30, (3, 1)),
    "herbs": ("Грибной ход", 30, (1, 3)),
    "deep": ("Глубинная трещина", 60, (4, 3)),
}
PETS = {
    "raven": ("Ворон-разведчик", "Помогает точно атаковать."),
    "wolf": ("Волк-страж", "Повышает запас здоровья."),
}
ENERGY_MAX = 6
ENERGY_INTERVAL = 900
FORGE_ACTIONS = (
    ("sharpen", "Заточить", "ore"),
    ("rune", "Вставить руну", "runes"),
    ("enchant", "Возвысить", "marks"),
)


def init_workshop(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS companions (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            kind TEXT NOT NULL,
            rank INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS battle_energy (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            amount INTEGER NOT NULL,
            updated INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS materials (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            material TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
            PRIMARY KEY(user_id, material)
        );
        CREATE TABLE IF NOT EXISTS cave_runs (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            trail TEXT NOT NULL,
            ready_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gear_upgrades (
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            sharpening INTEGER NOT NULL DEFAULT 0,
            rune INTEGER NOT NULL DEFAULT 0,
            stars INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, item),
            FOREIGN KEY(user_id, item) REFERENCES loot(hero_id, item)
        );
        CREATE TABLE IF NOT EXISTS hero_effects (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            effect TEXT NOT NULL,
            expires INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settlement_claims (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            prize TEXT NOT NULL,
            period INTEGER NOT NULL,
            PRIMARY KEY(user_id, prize, period)
        );
        CREATE TABLE IF NOT EXISTS settlement_counters (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            activity TEXT NOT NULL,
            amount INTEGER NOT NULL,
            PRIMARY KEY(user_id, activity)
        );
    """)


def balances(db, user_id):
    values = dict.fromkeys(MATERIALS, 0)
    values.update((row["material"], row["quantity"]) for row in db.execute(
        "SELECT material, quantity FROM materials WHERE user_id = ?", (user_id,)
    ))
    return values


def materials_text(db, user_id):
    return " · ".join(f"{MATERIALS[key]}: {value}" for key, value in balances(db, user_id).items())


def add(db, user_id, material, amount):
    db.execute("""
        INSERT INTO materials VALUES (?, ?, ?)
        ON CONFLICT(user_id, material) DO UPDATE SET quantity = quantity + excluded.quantity
    """, (user_id, material, amount))


def spend(db, user_id, material, amount):
    return bool(db.execute("""
        UPDATE materials SET quantity = quantity - ?
        WHERE user_id = ? AND material = ? AND quantity >= ?
    """, (amount, user_id, material, amount)).rowcount)


def spend_coins(db, user_id, amount):
    return bool(db.execute("UPDATE heroes SET coins = coins - ? WHERE user_id = ? AND coins >= ?",
                           (amount, user_id, amount)).rowcount)


def count(db, user_id, activity):
    row = db.execute("SELECT amount FROM settlement_counters WHERE user_id = ? AND activity = ?",
                     (user_id, activity)).fetchone()
    return row["amount"] if row else 0


def bump(db, user_id, activity, amount=1):
    db.execute("""
        INSERT INTO settlement_counters VALUES (?, ?, ?)
        ON CONFLICT(user_id, activity) DO UPDATE SET amount = amount + excluded.amount
    """, (user_id, activity, amount))


def claim(db, user_id, prize, period=0):
    return bool(db.execute("INSERT OR IGNORE INTO settlement_claims VALUES (?, ?, ?)",
                           (user_id, prize, period)).rowcount)


def claimed(db, user_id, prize, period=0):
    return db.execute("SELECT 1 FROM settlement_claims WHERE user_id = ? AND prize = ? AND period = ?",
                      (user_id, prize, period)).fetchone() is not None


def active_effect(db, user_id, now=None):
    now = int(time.time()) if now is None else now
    return db.execute("SELECT * FROM hero_effects WHERE user_id = ? AND expires > ?", (user_id, now)).fetchone()


def cave_run(db, user_id):
    return db.execute("SELECT * FROM cave_runs WHERE user_id = ?", (user_id,)).fetchone()


def cave(db, hero, action, now):
    user_id = hero["user_id"]
    run = cave_run(db, user_id)
    if action == "collect":
        if not run:
            return "Сначала выбери ход пещеры."
        if run["ready_at"] > now:
            return f"Герой ещё в пещере. Осталось {run['ready_at'] - now} сек."
        _, _, (ore, herbs) = CAVE[run["trail"]]
        db.execute("DELETE FROM cave_runs WHERE user_id = ?", (user_id,))
        add(db, user_id, "ore", ore)
        add(db, user_id, "herbs", herbs)
        bump(db, user_id, "cave")
        bump(db, user_id, f"cave:{now // 86400}")
        suffix = ""
        if run["trail"] == "deep" or random.randrange(4) == 0:
            add(db, user_id, "runes", 1)
            suffix = " По дороге найдена руна."
        return f"Герой вернулся: +{ore} руды, +{herbs} трав.{suffix}"
    if action not in CAVE:
        return "Выбери ход пещеры."
    if run:
        return "Одна вылазка уже началась. Забери её добычу."
    if action == "deep" and hero["xp"] < 60:
        return "Глубинная трещина открывается на 3-м уровне."
    title, duration, _ = CAVE[action]
    db.execute("INSERT INTO cave_runs VALUES (?, ?, ?)", (user_id, action, now + duration))
    return f"Начата вылазка «{title}». Добычу можно забрать через {duration} сек."


def forge(db, hero, action, item):
    user_id = hero["user_id"]
    accessories = {"ring": (3, 4), "amulet": (5, 8)}
    if action == "make" and item in accessories:
        level, cost = accessories[item]
        if 1 + hero["xp"] // 30 < level:
            return f"Украшение доступно с уровня {level}."
        if db.execute("SELECT 1 FROM loot WHERE hero_id = ? AND item = ?", (user_id, item)).fetchone():
            return "Это украшение уже изготовлено."
        if not spend(db, user_id, "ore", cost):
            return f"Нужно {cost} руды."
        return "Изготовлено, " + grant_item(db, user_id, item) + ". Надеть можно в сумке."
    rule = next((rule for rule in FORGE_ACTIONS if rule[0] == action), None)
    if not rule or item not in ITEMS or not db.execute(
        "SELECT 1 FROM loot WHERE hero_id = ? AND item = ?", (user_id, item)
    ).fetchone():
        return "Улучшить можно предмет из твоей сумки."
    _, verb, material = rule
    column = {"sharpen": "sharpening", "rune": "rune", "enchant": "stars"}[action]
    maximum = {"sharpen": 3, "rune": 1, "enchant": 2}[action]
    db.execute("INSERT OR IGNORE INTO gear_upgrades(user_id, item) VALUES (?, ?)", (user_id, item))
    gear = db.execute("SELECT * FROM gear_upgrades WHERE user_id = ? AND item = ?", (user_id, item)).fetchone()
    current = gear[column]
    if current >= maximum:
        return "Достигнут предел этого улучшения."
    price = current + 2 if action == "sharpen" else current + 1
    if not spend(db, user_id, material, price):
        return f"Не хватает ресурсов. Нужно {price} · {MATERIALS[material]}."
    db.execute(f"UPDATE gear_upgrades SET {column} = {column} + 1 WHERE user_id = ? AND item = ?", (user_id, item))
    bump(db, user_id, "forge")
    return f"«{ITEMS[item][0]}» · {verb.lower()} · {current + 1}/{maximum}. Усиление действует, когда предмет надет."


def brew(db, user_id, effect, now):
    if effect not in POTIONS:
        return "Выбери настой."
    if active_effect(db, user_id, now):
        return "На герое уже действует настой. Дождись окончания."
    title, _, price = POTIONS[effect]
    if not spend(db, user_id, "herbs", price):
        return f"Для настоя нужно {price} трав."
    db.execute("""
        INSERT INTO hero_effects VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET effect = excluded.effect, expires = excluded.expires
    """, (user_id, effect, now + 3600))
    bump(db, user_id, "lab")
    return f"«{title}» действует один час."


def companion(db, user_id):
    return db.execute("SELECT * FROM companions WHERE user_id = ?", (user_id,)).fetchone()


def pet(db, hero, action):
    user_id = hero["user_id"]
    owned = companion(db, user_id)
    if action in PETS:
        if owned:
            return "У героя уже есть спутник."
        if hero["xp"] < 30:
            return "Спутника можно взять со 2-го уровня."
        if not spend_coins(db, user_id, 25):
            return "Чтобы взять спутника, нужно 25 монет."
        db.execute("INSERT INTO companions VALUES (?, ?, 1)", (user_id, action))
        return f"Теперь с тобой {PETS[action][0]}."
    if action == "feed" and owned:
        if owned["rank"] >= 3:
            return "Спутник достиг третьего ранга."
        if not spend(db, user_id, "herbs", owned["rank"] + 2):
            return "Не хватает трав для корма."
        db.execute("UPDATE companions SET rank = rank + 1 WHERE user_id = ?", (user_id,))
        return "Спутник вырос и даёт более сильный бонус."
    return "Сначала выбери спутника."


def training(db, user_id, action):
    if action not in {"attack", "health"}:
        return "Выбери упражнение."
    key = f"training:{action}"
    rank = count(db, user_id, key)
    if rank >= 3:
        return "Герой уже достиг третьего ранга."
    price = 12 + rank * 8
    if not spend_coins(db, user_id, price):
        return f"На тренировку нужно {price} монет."
    bump(db, user_id, key)
    return f"Тренировка завершена, новый ранг: {rank + 1}/3."


def energy(db, user_id, now):
    row = db.execute("SELECT * FROM battle_energy WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return ENERGY_MAX, now
    elapsed = max(0, now - row["updated"]) // ENERGY_INTERVAL
    current = min(ENERGY_MAX, row["amount"] + elapsed)
    updated = now if current == ENERGY_MAX else row["updated"] + elapsed * ENERGY_INTERVAL
    return current, updated


def use_energy(db, user_id, now):
    amount, updated = energy(db, user_id, now)
    if not amount:
        return False
    db.execute("""
        INSERT INTO battle_energy VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET amount = excluded.amount, updated = excluded.updated
    """, (user_id, amount - 1, updated))
    bump(db, user_id, f"energy:{now // 86400}")
    return True
