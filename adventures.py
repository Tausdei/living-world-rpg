"""Locations, expedition scenes and persistent expedition progress."""
from dataclasses import dataclass

from activities import QUESTS, record_objective, reward
from campaign import mark
from region_details import DETOURS, HELP_COST, REGIONS


PROFESSIONS = {"scout": "Следопыт", "herbalist": "Травник"}


@dataclass(frozen=True)
class Option:
    skill: str
    title: str
    coins: int
    loot: str
    result: str = ""


@dataclass(frozen=True)
class Scene:
    description: str
    options: tuple[Option, Option]


@dataclass(frozen=True)
class Route:
    title: str
    art: str
    level: int
    difficulty: int
    scenes: tuple[Scene, ...]


ROUTES = {
    "forest": Route("Туманный лес", "misty-forest", 1, 0, (
        Scene("За мостом затопило тропу. На берегу видны свежие следы.", (
            Option("scout", "Пойти по следам в обход", 12, "knife", "Следы привели к брошенным мосткам. В чехле на перилах ты нашёл нож."),
            Option("herbalist", "Собрать лунную мяту у воды", 9, "charm", "Ты принёс мяту дозорным. У мостков за неё отдали плетёный оберег."),
        )),
    )),
    "ruins": Route("Старая башня", "old-tower", 2, 2, (
        Scene("В сторожевой башне обрушилась лестница. Из-под плит тянет горьким дымом.", (
            Option("scout", "Пробраться по обходной галерее", 20, "blade", "Галерея вывела в уцелевшую оружейную. Под настилом лежал клинок стражи."),
            Option("herbalist", "Приготовить отвар и спуститься через дым", 17, "blade", "Отвар помог пересечь задымлённую лестницу. В нижней караулке остался клинок стражи."),
        )),
    )),
    "fen": Route("Топь колоколов", "bell-fen", 1, 1, (
        Scene("Из затопленной деревни доносится колокол. Плоты селян застряли среди камышей.", (
            Option("scout", "Провесить тропу между сваями", 0, "", "Ты отметил безопасную тропу."),
            Option("herbalist", "Собрать светящиеся стебли для меток", 0, "", "Камышовые огни указали обратный путь."),
        )),
        Scene("За колокольней скрывается укрытие. Вода поднимается, а к пристани подходит один уцелевший плот.", (
            Option("scout", "Вывести пленённого лодочника по меткам", 13, "fang", "Лодочник добрался до берега и отдал фамильный клык."),
            Option("herbalist", "Унять приступ у раненой хранительницы", 12, "charm", "Хранительница оправилась и подарила оберег."),
        )),
    )),
    "pass": Route("Белый перевал", "white-pass", 2, 2, (
        Scene("Метель отрезала торговый обоз от сторожки. Здесь можно разбить опорный лагерь.", (
            Option("scout", "Проверить снежный склон зондом", 0, "", "Ты нашёл ложбину, по которой не пройдёт лавина."),
            Option("herbalist", "Собрать сухой мох для жаровни", 0, "", "Тёплая жаровня вернула силы возчикам."),
        )),
        Scene("Из-под снега торчат полозья. Рядом виден след к расщелине, где укрылись люди.", (
            Option("scout", "Поднять полозья и вытащить обоз", 19, "spear", "Обоз спасён, и дозорные делятся снаряжением."),
            Option("herbalist", "Отогреть путников и провести их в сторожку", 17, "cloak", "Путники выжили и подарили тёплый плащ."),
        )),
    )),
    "archive": Route("Затопленный архив", "drowned-archive", 3, 3, (
        Scene("В нижнем зале бывшего архива горит синий свет. Под водой видны знаки на ступенях.", (
            Option("scout", "Разметить безопасную глубину", 0, "", "Ты оставил знаки уровня воды."),
            Option("herbalist", "Растереть светящиеся водоросли для фонаря", 0, "", "Свет выявил выходы из подводной галереи."),
        )),
        Scene("Течение тянет створку хранилища. За неё цепляются рукописи и гаснущий фонарь.", (
            Option("scout", "Заклинить створку и вынести ларец", 24, "vest", "Архив уцелел, а в ларце лежал старый жилет."),
            Option("herbalist", "Сберечь рукописи под водостойким настоем", 22, "lantern", "Рукописи вынесены, дух хранителя оставил фонарь."),
        )),
    )),
    "observatory": Route("Пепельная обсерватория", "cinder-observatory", 4, 4, (
        Scene("Под куполом пепел вращается вокруг сломанной линзы. Каждые несколько минут купол содрогается.", (
            Option("scout", "Привязать страховочный трос к опорам", 0, "", "Трос поможет пережить следующий толчок."),
            Option("herbalist", "Погасить жар солевым настоем", 0, "", "Разогретая оправа линзы остыла."),
        )),
        Scene("Центральная линза показывает след упавшей звезды. Пол раскалывается под основанием.", (
            Option("scout", "Опустить линзу страховочным тросом", 31, "star", "Линза привела к осколку упавшей звезды."),
            Option("herbalist", "Укрепить оправу охлаждающим составом", 28, "seal", "Линза спасена, а под ней обнаружилась печать."),
        )),
    )),
}
ROUTE_MENU = "\n".join(
    f"/adventure_{key} — {route.title} · ур. {route.level}" for key, route in ROUTES.items()
)


def init_adventures(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS expedition_progress (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            stage INTEGER NOT NULL,
            prepared INTEGER NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS expedition_detours (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            choice TEXT NOT NULL
        )
    """)


def current_scene(db, user_id, key):
    progress = db.execute("SELECT stage, prepared FROM expedition_progress WHERE user_id = ?", (user_id,)).fetchone()
    stage = progress["stage"] if progress else 0
    return stage, ROUTES[key].scenes[stage], progress["prepared"] if progress else 0


def region(key):
    if key not in ROUTES:
        return "Выбери область: /adventure"
    route = ROUTES[key]
    rank = f"Базовый ранг навыка: {route.difficulty}." if route.difficulty else "Подходит для первого похода."
    preparation = (f"Подготовка с ранга {max(0, route.difficulty - 1)} облегчает финал.\n"
                   if len(route.scenes) > 1 else "")
    return (f"{route.title} · уровень {route.level}\n{REGIONS[key]}\n"
            f"Этапов: {len(route.scenes)}. {rank}\n{preparation}/adventure_{key} — отправиться")


def detour_state(db, user_id, key, index, prepared):
    base = ROUTES[key].difficulty - prepared
    detour = DETOURS.get(key) if index else None
    if not detour:
        return max(0, base), 0, None
    row = db.execute("SELECT choice FROM expedition_detours WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        choice = row["choice"]
        return max(0, base + (1 if choice == "risk" else -1)), detour.extra_coins if choice == "risk" else 0, None
    return max(0, base), 0, {
        "description": detour.description, "cost": HELP_COST, "bonus": detour.extra_coins,
        "aid_available": base > 0,
        "aid": detour.help_title, "risk": detour.risk_title,
    }


def encounter(db, user_id, key):
    route = ROUTES[key]
    index, scene, prepared = current_scene(db, user_id, key)
    lines = [scene.description]
    required, bonus, detour = detour_state(db, user_id, key, index, prepared)
    if len(route.scenes) > 1:
        lines.insert(0, f"{route.title} · этап {index + 1}/{len(route.scenes)}")
        if index:
            lines.append(f"Требуемый ранг: {required}." + (f" За успех: +{bonus} монет." if bonus else ""))
            if detour:
                lines.append(detour["description"])
                if detour["aid_available"]:
                    lines.append(f"/choose_aid — {detour['aid']} · −1 ранг за {detour['cost']} монет")
                lines.append(f"/choose_risk — {detour['risk']} · +1 ранг, +{detour['bonus']} монет за успех")
    lines.extend(f"/choose_{n} — {option.title} ({PROFESSIONS[option.skill]})"
                 for n, option in enumerate(scene.options, 1))
    lines.append("/choose_leave — вернуться")
    return "\n".join(lines)


def close_route(db, user_id):
    db.execute("UPDATE heroes SET route = NULL WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM expedition_progress WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM expedition_detours WHERE user_id = ?", (user_id,))


def choose(db, hero, argument):
    user_id, key = hero["user_id"], hero["route"]
    if not key:
        return "Сначала выбери маршрут. /adventure"
    if argument == "leave":
        close_route(db, user_id)
        return "Ты вернулся в поселение. /adventure"
    route = ROUTES[key]
    index, scene, prepared = current_scene(db, user_id, key)
    required, bonus, detour = detour_state(db, user_id, key, index, prepared)
    if argument in {"aid", "risk"} and detour:
        if argument == "aid" and not detour["aid_available"]:
            return "Путь уже безопасен, платить за помощь не нужно.\n" + encounter(db, user_id, key)
        if argument == "aid" and hero["coins"] < HELP_COST:
            return "Не хватает монет на помощь.\n" + encounter(db, user_id, key)
        if argument == "aid":
            db.execute("UPDATE heroes SET coins = coins - ? WHERE user_id = ?", (HELP_COST, user_id))
        db.execute("INSERT INTO expedition_detours VALUES (?, ?)", (user_id, argument))
        note = "Ты заручился помощью. Теперь путь безопаснее." if argument == "aid" else "Ты выбрал опасный обход ради дополнительной добычи."
        return note + "\n" + encounter(db, user_id, key)
    if argument not in {"1", "2"}:
        return encounter(db, user_id, key)

    option = scene.options[int(argument) - 1]
    skill = option.skill
    if index + 1 < len(route.scenes):
        prepared = int(hero[skill] // 3 >= route.difficulty - 1)
        db.execute("INSERT INTO expedition_progress VALUES (?, ?, ?)", (user_id, index + 1, prepared))
        note = option.result if prepared else "Подготовиться полностью не вышло, но путь открыт."
        return note + "\n" + encounter(db, user_id, key)

    success = hero[skill] // 3 >= required
    xp = (20 if index else 15) if success else 5
    coins = option.coins + bonus if success else 2
    close_route(db, user_id)
    db.execute(f"UPDATE heroes SET {skill} = {skill} + 1 WHERE user_id = ?", (user_id,))
    if success:
        mark(db, user_id, key)
        if key in QUESTS:
            record_objective(db, user_id, key, QUESTS[key][2])
    prize = reward(db, user_id, xp, coins, option.loot if success else None)
    outcome = option.result
    if not success:
        outcome = f"Ты отступил. Для навыка «{PROFESSIONS[skill]}» нужен ранг {required}, у тебя {hero[skill] // 3}."
    level = 1 + (hero["xp"] + xp) // 30
    promotion = f" Новый уровень: {level}." if level > 1 + hero["xp"] // 30 else ""
    return f"{outcome} {prize}, +1 очко профессии «{PROFESSIONS[skill]}».{promotion}\n/adventure"
