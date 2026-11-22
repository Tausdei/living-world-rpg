"""Ranked solo trials and scheduled prize periods."""
from secrets import token_hex

from activities import reward, stats
from guilds import contribute
from workshop import add, bump, claim, count, use_energy


# Each wave has health and damage before the selected stance modifies combat.
MODES = {
    "arena": ("Арена дозора", 1, 5, ((12, 2),), "Один бой, очки за победу."),
    "coliseum": ("Каменный круг", 3, 3, ((11, 2), (15, 2), (18, 3)), "Три волны с общим запасом здоровья."),
    "crown": ("Испытание короны", 4, 2, ((14, 2), (18, 3), (24, 4)), "Три сильных соперника. Неудача лишает награды серии."),
    "beacons": ("Сторожевые маяки", 3, 3, ((12, 3), (16, 2), (20, 2)), "После каждой победы у маяка восстанавливается 4 здоровья."),
    "valley": ("Долина теней", 4, 2, ((10, 2), (11, 2), (13, 2), (17, 3)), "Четыре засады. Награды растут с длиной серии."),
}
STANCES = {"steady": "Ровный бой", "guard": "Осторожный бой", "rush": "Рывок"}
DAY = 86400


def init_contests(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS contest_runs (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            mode TEXT NOT NULL,
            day INTEGER NOT NULL,
            zone INTEGER NOT NULL,
            hp INTEGER NOT NULL,
            maxhp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            token TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contest_day (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            mode TEXT NOT NULL,
            day INTEGER NOT NULL,
            attempts INTEGER NOT NULL,
            score INTEGER NOT NULL,
            PRIMARY KEY(user_id, mode, day)
        );
    """)


def active_contest(db, user_id, day):
    return db.execute("SELECT * FROM contest_runs WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()


def contest_status(db, user_id, mode, day):
    row = db.execute("SELECT attempts, score FROM contest_day WHERE user_id = ? AND mode = ? AND day = ?",
                     (user_id, mode, day)).fetchone()
    return (row["attempts"], row["score"]) if row else (0, 0)


def contest_scene(run):
    name, _, _, waves, _ = MODES[run["mode"]]
    enemy_hp, enemy_attack = waves[run["zone"]]
    return (f"{name} · волна {run['zone'] + 1}/{len(waves)}\n"
            f"Здоровье: {run['hp']}/{run['maxhp']} · противник: здоровье {enemy_hp}, урон {enemy_attack}.")


def contest(db, hero, action, argument, now):
    user_id, day = hero["user_id"], now // DAY
    run = active_contest(db, user_id, day)
    if action == "prize":
        points = count(db, user_id, "league")
        if not points:
            return "Чтобы получить дневную награду лиги, сначала выиграй на арене."
        if not claim(db, user_id, "league", day):
            return "Сегодня награда лиги уже получена."
        marks = min(5, 1 + points // 15)
        add(db, user_id, "marks", marks)
        return f"Награда лиги: +{marks} знаков. {reward(db, user_id, 0, 3 * marks)}."
    if action == "start" and argument in MODES:
        if run:
            return contest_scene(run)
        title, level, maximum, _, _ = MODES[argument]
        if 1 + hero["xp"] // 30 < level:
            return f"«{title}» открывается на уровне {level}."
        attempts, _ = contest_status(db, user_id, argument, day)
        if attempts >= maximum:
            return "Сегодня попытки в этом испытании закончились. Обновление в 00:00 UTC."
        if not use_energy(db, user_id, now):
            return "Энергия исчерпана. На восстановление единицы нужно 15 минут."
        hp, attack = stats(db, hero)
        db.execute("INSERT OR REPLACE INTO contest_runs VALUES (?, ?, ?, 0, ?, ?, ?, ?)",
                   (user_id, argument, day, hp, hp, attack, token_hex(5)))
        db.execute("""
            INSERT INTO contest_day VALUES (?, ?, ?, 1, 0)
            ON CONFLICT(user_id, mode, day) DO UPDATE SET attempts = attempts + 1
        """, (user_id, argument, day))
        return contest_scene(active_contest(db, user_id, day))
    if not run:
        return "Выбери испытание."
    if action in {*STANCES, "retreat"} and argument and argument != run["token"]:
        return "Этот ход уже недоступен."
    if action == "retreat":
        db.execute("DELETE FROM contest_runs WHERE user_id = ?", (user_id,))
        return "Ты вышел из испытания. Попытка израсходована."
    if action not in STANCES:
        return contest_scene(run)

    mode = run["mode"]
    _, _, _, waves, _ = MODES[mode]
    foe_hp, foe_attack = waves[run["zone"]]
    attack = max(1, run["attack"] + {"steady": 0, "guard": -2, "rush": 3}[action])
    incoming = max(1, foe_attack + {"steady": 0, "guard": -2, "rush": 2}[action])
    blows = (foe_hp + attack - 1) // attack
    hp = run["hp"] - (blows - 1) * incoming
    final = run["zone"] + 1 == len(waves)
    if mode == "valley" and hp > 0 and not final:
        extra = 1 + run["zone"]
        reward(db, user_id, 0, extra)
        prefix = f"Засада отражена. +{extra} монет.\n"
    else:
        prefix = ""
    if hp <= 0 or final:
        db.execute("DELETE FROM contest_runs WHERE user_id = ?", (user_id,))
        if hp <= 0:
            return "Противник выиграл. Испытание завершено."
        points = 3 * len(waves)
        if mode == "arena":
            bump(db, user_id, "league", points)
        bump(db, user_id, "contests")
        db.execute("UPDATE contest_day SET score = score + ? WHERE user_id = ? AND mode = ? AND day = ?",
                   (points, user_id, mode, day))
        add(db, user_id, "marks", 1 + (mode != "arena"))
        contribute(db, user_id, now, points)
        return f"Испытание пройдено. +{points} очков турнира, получены знаки. {reward(db, user_id, 4 * len(waves), 3 * len(waves))}."
    if mode == "beacons":
        hp = min(hp + 4, run["maxhp"])
    db.execute("UPDATE contest_runs SET zone = zone + 1, hp = ?, token = ? WHERE user_id = ?",
               (hp, token_hex(5), user_id))
    return prefix + contest_scene(active_contest(db, user_id, day))


def rankings(db, kind, day):
    if kind == "league":
        sql = """SELECT name, amount AS points FROM settlement_counters JOIN heroes USING(user_id)
                 WHERE activity = 'league' ORDER BY points DESC, user_id LIMIT 8"""
        return db.execute(sql).fetchall()
    if kind in MODES:
        return db.execute("""
            SELECT name, score AS points FROM contest_day JOIN heroes USING(user_id)
            WHERE mode = ? AND day = ? AND score > 0 ORDER BY points DESC, user_id LIMIT 8
        """, (kind, day)).fetchall()
    return db.execute("""SELECT name, xp AS points FROM heroes ORDER BY xp DESC, user_id LIMIT 8""").fetchall()
