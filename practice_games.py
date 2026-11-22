"""Short playable profession puzzles shared by Telegram and the web."""
import json
import random
from secrets import token_hex

from activities import reward
from fieldwork import PRACTICE_DELAY, set_cooldown, wait_seconds


TRAILS = (
    ("S#..X", "...#.", ".##..", ".....", "....."),
    ("S...#", ".##..", "..#..", "#...#", "...X."),
    ("S.~..", "##.#.", ".....", ".###.", "...X."),
)
DIRECTIONS = {"north": (0, -1, "↑ Север"), "west": (-1, 0, "← Запад"),
              "south": (0, 1, "↓ Юг"), "east": (1, 0, "→ Восток")}
BREW = {"heat": "Подбросить дрова (+2)", "cool": "Охладить (−1)", "infuse": "Добавить порцию"}
SKILLS = {"scout": "Тропа по следам", "herbalist": "Настой у котла"}
ACTIONS = {*DIRECTIONS, *BREW, "cancel"}


def init_practice(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS practice_games (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            skill TEXT NOT NULL,
            position TEXT NOT NULL,
            token TEXT NOT NULL
        )
    """)


def active_practice(db, user_id):
    return db.execute("SELECT * FROM practice_games WHERE user_id = ?", (user_id,)).fetchone()


def trail_layout(data):
    layout = TRAILS[data["trail"]]
    mirror = data.get("mirror", 0)
    if mirror & 1:
        layout = tuple(row[::-1] for row in layout)
    if mirror & 2:
        layout = layout[::-1]
    return layout


def practice_view(state):
    data = json.loads(state["position"])
    skill = state["skill"]
    if skill == "scout":
        trail = trail_layout(data)
        row, col = data["y"], data["x"]
        board = ["".join("@" if (x, y) == (col, row) else cell
                         for x, cell in enumerate(line)) for y, line in enumerate(trail)]
        return {
            "skill": skill, "title": SKILLS[skill], "remaining": data["remaining"], "board": board,
            "description": "@ герой · X цель · # преграда · ~ топь (2 шага). Дойди до цели.",
            "actions": [{"key": key, "label": label} for key, (_, _, label) in DIRECTIONS.items()],
        }
    return {
        "skill": skill, "title": SKILLS[skill], **data,
        "description": (f"Добавляй порции при целевой температуре. Порция охлаждает котёл "
                        f"на {data['cooling']}. Перегрев выше 6 портит настой."),
        "actions": [{"key": key, "label": label} for key, label in BREW.items()],
    }


def practice_scene(state):
    view = practice_view(state)
    lines = [view["title"]]
    if view["skill"] == "scout":
        lines.append("🧭 герой · ✦ цель · ■ преграда · ≈ топь (2 шага)")
        symbols = {"@": "🧭", "X": "✦", "#": "■", ".": "·", "S": "·", "~": "≈"}
        lines.extend(" ".join(symbols[cell] for cell in row) for row in view["board"])
    else:
        lines.append(view["description"])
        lines.append(f"Температура: {view['heat']}/6 · цель: {view['target']} · порции: {view['progress']}/3 · сырьё: {view['stock']}")
    lines.append(f"Осталось ходов: {view['remaining']}")
    lines.extend(f"/practice_answer_{action['key']} — {action['label']}" for action in view["actions"])
    return "\n".join(lines)


def practice(db, hero, skill, now, rng=random):
    user_id = hero["user_id"]
    state = active_practice(db, user_id)
    if state:
        return practice_scene(state)
    if skill not in SKILLS:
        return "Мини-игры профессий\n/practice_scout — Тропа по следам\n/practice_herbalist — Настой у котла"
    remaining = wait_seconds(db, user_id, skill, now)
    if remaining:
        return f"Следующая попытка этой профессии через {remaining} сек."
    if skill == "scout":
        index = rng.randrange(len(TRAILS))
        mirror = rng.randrange(4)
        position = {
            "trail": index, "mirror": mirror, "x": 4 if mirror & 1 else 0,
            "y": 4 if mirror & 2 else 0, "remaining": (12, 10, 10)[index],
        }
    else:
        target = rng.choice([3, 4])
        position = {
            "target": target, "heat": rng.randint(1, 5), "cooling": rng.randint(1, 2),
            "stock": 4, "progress": 0, "remaining": 10,
        }
    db.execute("INSERT INTO practice_games VALUES (?, ?, ?, ?)",
               (user_id, skill, json.dumps(position), token_hex(5)))
    return practice_scene(active_practice(db, user_id))


def walk(data, action):
    dx, dy, _ = DIRECTIONS[action]
    x, y = data["x"] + dx, data["y"] + dy
    trail = trail_layout(data)
    if not (0 <= x < len(trail[0]) and 0 <= y < len(trail)) or trail[y][x] == "#":
        return 0, False, "Там нет прохода."
    cell = trail[y][x]
    cost = 2 if cell == "~" else 1
    if cost > data["remaining"]:
        data["remaining"] = 0
        return 0, False, "На переход через топь не хватило сил."
    data.update(x=x, y=y)
    return cost, cell == "X", "Ты пересёк топь." if cost == 2 else "Ты продвинулся по следу."


def brew(data, action):
    if action == "heat":
        data["heat"] += 2
        return 1, False, "Огонь разгорелся."
    if action == "cool":
        data["heat"] = max(0, data["heat"] - 1)
        return 1, False, "Котёл остыл."
    data["stock"] -= 1
    matched = data["heat"] == data["target"]
    data["progress"] += int(matched)
    data["heat"] = max(0, data["heat"] - data["cooling"])
    return 1, data["progress"] == 3, "Порция настоялась." if matched else "Порция испорчена из-за температуры."


def answer(db, hero, action, now):
    user_id = hero["user_id"]
    state = active_practice(db, user_id)
    if not state:
        return "Сначала открой мини-игру: /practice"
    skill = state["skill"]
    data = json.loads(state["position"])
    actions = DIRECTIONS if skill == "scout" else BREW
    if action not in actions and action != "cancel":
        return practice_scene(state)

    won = False
    message = "Испытание завершено досрочно."
    if action != "cancel":
        cost, won, message = walk(data, action) if skill == "scout" else brew(data, action)
        data["remaining"] -= cost
        ruined = skill == "herbalist" and (data["heat"] > 6 or data["stock"] + data["progress"] < 3)
        if not won and not ruined and data["remaining"] > 0:
            db.execute("UPDATE practice_games SET position = ?, token = ? WHERE user_id = ?",
                       (json.dumps(data), token_hex(5), user_id))
            return message + "\n" + practice_scene(active_practice(db, user_id))
        if not won:
            message += " Испытание не удалось."

    db.execute("DELETE FROM practice_games WHERE user_id = ?", (user_id,))
    set_cooldown(db, user_id, skill, now + PRACTICE_DELAY)
    if not won:
        return message + " /practice"
    points = 2 if data["remaining"] >= 2 else 1
    db.execute(f"UPDATE heroes SET {skill} = {skill} + ? WHERE user_id = ?", (points, user_id))
    return f"{message} Испытание пройдено. +{points} очк. навыка, {reward(db, user_id, 12, 6)}."
