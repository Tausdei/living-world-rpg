"""Persistent turn-based hunts and profession challenges."""
import json
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
PRACTICES = {
    "scout": (
        ("Какое животное оставляет раздвоенные отпечатки копыт?", "Кабан", "Волк", "Лисица"),
        ("Какие следы свежее после дождя?", "Чёткие края без скопившейся воды", "Размытые края и лужа внутри", "Края заросли мхом"),
        ("Чьи следы выдают длинные прыжки и две длинные задние лапы?", "Заяц", "Человек", "Кабан"),
        ("Чтобы определить направление движения зверя, что осмотреть первым?", "Куда смотрят пальцы или копыта", "Цвет земли", "Высоту ближайшего дерева"),
    ),
    "herbalist": (
        ("Для прохладного ароматного настоя нужны листья лунной мяты. Что взять?", "Зелёные листья с прохладным запахом", "Смолистую кору", "Сухие семена без запаха"),
        ("Как сушить лекарственные листья, чтобы между ними проходил воздух?", "Разложить тонким слоем", "Сложить в закрытый мокрый мешок", "Утрамбовать в горшок"),
        ("Что поможет отличить похожие растения у ручья?", "Проверить листья, стебель и цветки", "Посмотреть только на высоту", "Смешать всё в одной корзине"),
        ("Что сделать с незнакомой травой перед приготовлением игрового настоя?", "Отложить и свериться с травником", "Добавить её первой", "Смешать с остальными"),
    ),
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
        CREATE TABLE IF NOT EXISTS practices (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            skill TEXT NOT NULL,
            questions TEXT NOT NULL,
            step INTEGER NOT NULL,
            score INTEGER NOT NULL,
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


def active_practice(db, user_id):
    return db.execute("SELECT * FROM practices WHERE user_id = ?", (user_id,)).fetchone()


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


def practice_question(state):
    questions = json.loads(state["questions"])
    index, order = questions[state["step"]]
    prompt, *choices = PRACTICES[state["skill"]][index]
    return prompt, [choices[position] for position in order], order.index(0) + 1


def practice_scene(state):
    prompt, labels, _ = practice_question(state)
    rows = [f"Испытание {state['step'] + 1}/3 · верных ответов: {state['score']}", prompt]
    rows.extend(f"/practice_answer_{number} — {label}" for number, label in enumerate(labels, 1))
    return "\n".join(rows)


def practice(db, hero, action, now, rng=random):
    user_id = hero["user_id"]
    state = active_practice(db, user_id)
    if state:
        return practice_scene(state)
    if action not in PRACTICES:
        return "Мини-игры профессий\n/practice_scout — чтение следов\n/practice_herbalist — травник"
    remaining = wait_seconds(db, user_id, action, now)
    if remaining:
        return f"Следующая попытка этой профессии через {remaining} сек."
    questions = [(index, rng.sample(range(3), 3)) for index in rng.sample(range(len(PRACTICES[action])), 3)]
    db.execute("INSERT INTO practices VALUES (?, ?, ?, 0, 0, ?)", (user_id, action, json.dumps(questions), token_hex(5)))
    return practice_scene(active_practice(db, user_id))


def answer(db, hero, action, now):
    user_id = hero["user_id"]
    state = active_practice(db, user_id)
    if not state:
        return "Сначала открой мини-игру: /practice"
    skill = state["skill"]
    if action == "cancel":
        db.execute("DELETE FROM practices WHERE user_id = ?", (user_id,))
        set_cooldown(db, user_id, skill, now + PRACTICE_DELAY)
        return "Испытание завершено досрочно. /practice"
    if action not in {"1", "2", "3"}:
        return practice_scene(state)
    _, labels, correct = practice_question(state)
    score = state["score"] + (int(action) == correct)
    feedback = f"Правильный ответ: {labels[correct - 1]}."
    if state["step"] < 2:
        db.execute("UPDATE practices SET step = step + 1, score = ?, token = ? WHERE user_id = ?",
                   (score, token_hex(5), user_id))
        return feedback + "\n" + practice_scene(active_practice(db, user_id))
    db.execute("DELETE FROM practices WHERE user_id = ?", (user_id,))
    set_cooldown(db, user_id, skill, now + PRACTICE_DELAY)
    if score < 2:
        return f"{feedback}\nРезультат: {score}/3. Для награды нужны два верных ответа."
    xp, coins, points = (12, 6, 2) if score == 3 else (8, 3, 1)
    db.execute(f"UPDATE heroes SET {skill} = {skill} + ? WHERE user_id = ?", (points, user_id))
    return f"{feedback}\nРезультат: {score}/3. +{points} очк. навыка, {reward(db, user_id, xp, coins)}."
