"""Story chapters that give existing activities a narrative order."""
from dataclasses import dataclass

from activities import reward


@dataclass(frozen=True)
class Chapter:
    key: str
    title: str
    description: str
    art: str
    goals: tuple[tuple[str, str], ...]
    xp: int
    coins: int


CHAPTERS = (
    Chapter("border", "Граница тумана",
            "Дозорница Мира заметила, что береговые костры гаснут один за другим. Она просит тебя проверить дорогу через лес и подготовиться к пути дальше.",
            "misty-forest", (("forest", "Вернись с добычей из Туманного леса"),
                            ("equipped", "Надень любой предмет снаряжения")),
            8, 8),
    Chapter("bells", "Колокол под водой",
            "Из леса доносится колокол затопленной деревни. Мира распознаёт сигнал бедствия. Прежде чем выходить на болота, освой ремесло, которое поможет в поле.",
            "bell-fen", (("practice", "Пройди мини-игру любой профессии"),
                         ("fen", "Успешно заверши экспедицию в Топи колоколов")),
            12, 12),
    Chapter("snow", "Следы на снегу",
            "Спасённые лодочники видели обоз с печатью Орина. Он ушёл через Белый перевал и не вернулся. Проверь снаряжение в охоте и разыщи обоз до новой метели.",
            "white-pass", (("hunt", "Победи противника в пошаговой охоте"),
                           ("pass", "Успешно заверши экспедицию на Белом перевале")),
            16, 16),
    Chapter("records", "Печать под водой",
            "В ящике из обоза — список пропавших книг. Их спрятали в затопленном архиве. Чтобы Орин смог разобрать найденные записи, нужна печать Смотрителя.",
            "drowned-archive", (("archive", "Успешно заверши экспедицию в Затопленном архиве"),
                                ("keeper", "Победи Пепельного смотрителя")),
            20, 22),
    Chapter("cinders", "Небо из пепла",
            "Записи Орина ведут в обсерваторию на гребне. Если восстановить линзу, станет ясно, куда упала звезда и почему над поселением гаснут огни.",
            "cinder-observatory", (("observatory", "Успешно заверши экспедицию в Пепельной обсерватории"),),
            28, 35),
)
GOAL_LINKS = {
    "equipped": ("bag", "#hero"), "practice": ("practice", "#work"),
    "hunt": ("hunt", "#journey"), "keeper": ("boss", "#journey"),
}
CHAPTER_KEYS = tuple(chapter.key for chapter in CHAPTERS)
ENDING = "Маяки снова горят. Находки из обсерватории помогли Орину нанести место падения звезды на карту."


def init_campaign(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS campaign_progress (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            completed INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campaign_marks (
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            mark TEXT NOT NULL,
            PRIMARY KEY (user_id, mark)
        );
    """)


def mark(db, user_id, key):
    db.execute("INSERT OR IGNORE INTO campaign_marks VALUES (?, ?)", (user_id, key))


def story_state(db, user_id):
    row = db.execute("SELECT completed FROM campaign_progress WHERE user_id = ?", (user_id,)).fetchone()
    completed = row["completed"] if row else 0
    result = {
        "completed": completed,
        "chapters": [chapter.title for chapter in CHAPTERS],
        "ending": ENDING,
        "current": None,
    }
    if completed >= len(CHAPTERS):
        return result

    marks = {row["mark"] for row in db.execute("SELECT mark FROM campaign_marks WHERE user_id = ?", (user_id,))}
    marks.update(row["quest"] for row in db.execute(
        "SELECT quest FROM quest_progress WHERE hero_id = ? AND progress > 0", (user_id,)
    ))
    equipped = db.execute("SELECT 1 FROM equipped WHERE hero_id = ?", (user_id,)).fetchone()
    if equipped:
        marks.add("equipped")
    if db.execute("SELECT 1 FROM boss_victory WHERE hero_id = ?", (user_id,)).fetchone():
        marks.add("keeper")

    chapter = CHAPTERS[completed]
    goals = []
    for key, label in chapter.goals:
        command, destination = GOAL_LINKS.get(key, (f"region_{key}", f"#route-{key}"))
        goals.append({"label": label, "done": key in marks, "command": command, "destination": destination})
    result["current"] = {
        "key": chapter.key, "title": chapter.title, "description": chapter.description,
        "art": chapter.art, "goals": goals, "xp": chapter.xp, "coins": chapter.coins,
        "ready": all(goal["done"] for goal in goals),
    }
    return result


def story_text(state):
    current = state["current"]
    count = len(state["chapters"])
    if not current:
        return f"Летопись поселения · {count}/{count}\n{state['ending']}"
    header = f"Глава {state['completed'] + 1}/{count} · {current['title']}"
    rows = ["✓ " + goal["label"] if goal["done"] else "○ " + goal["label"] for goal in current["goals"]]
    rows.append(f"Награда за главу: {current['xp']} опыта и {current['coins']} монет.")
    if current["ready"]:
        rows.append(f"/story_claim_{current['key']} — завершить главу")
    return "\n".join([header, current["description"], "", *rows])


def story(db, user_id, claim=None):
    state = story_state(db, user_id)
    current = state["current"]
    if not claim:
        return story_text(state)
    if not current or current["key"] != claim:
        return "Эта глава уже закрыта или ещё не началась.\n" + story_text(state)
    if not current["ready"]:
        return "Сначала выполни цели главы.\n" + story_text(state)
    db.execute("""
        INSERT INTO campaign_progress VALUES (?, ?)
        ON CONFLICT (user_id) DO UPDATE SET completed = excluded.completed
    """, (user_id, state["completed"] + 1))
    prize = reward(db, user_id, current["xp"], current["coins"])
    return f"Глава «{current['title']}» завершена. {prize}.\n\n" + story_text(story_state(db, user_id))
