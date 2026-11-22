"""Settlement commands and shared presentation for the browser and Telegram."""
from activities import numeric_id, reward
from contests import DAY, MODES, STANCES, active_contest, contest, contest_scene, contest_status, init_contests, rankings
from guilds import board, board_text, guild_command, guild_of, guild_text, init_guilds, invitations
from loot import ITEMS
from workshop import (
    CAVE, FORGE_ACTIONS, PETS, POTIONS, active_effect, add, brew, cave, cave_run, companion, energy,
    claim, claimed, count, forge, init_workshop, materials_text, pet, spend, spend_coins, training,
)


SECTIONS = {
    "cave": ("Пещера", "mine"),
    "forge": ("Кузница", "smithy"),
    "lab": ("Лаборатория", "laboratory"),
    "trade": ("Обменник", "merchant"),
    "sage": ("Хижина мудреца", "sage"),
    "battle": ("Сражения и лига", "coliseum"),
    "clan": ("Кланы и турниры", "guildhall"),
    "records": ("Зал славы", "rewards"),
    "collection": ("Коллекции", "bag"),
    "training": ("Тренировка", "hero"),
    "pet": ("Спутники", "wolf"),
    "chest": ("Сундук", "chest"),
    "mail": ("Почта", "raven"),
    "chat": ("Общий чат", "village"),
    "forum": ("Форум", "quests"),
    "guildchat": ("Клановый чат", "guildhall"),
}
EXCHANGE = {
    "gold": ("12 монет → 1 золото", "coins", 12, "gold", 1),
    "ore": ("1 золото → 4 руды", "gold", 1, "ore", 4),
    "herbs": ("1 золото → 4 травы", "gold", 1, "herbs", 4),
    "rune": ("2 золота → 1 руна", "gold", 2, "runes", 1),
    "marks": ("3 знака → 1 золото", "marks", 3, "gold", 1),
}
COLLECTIONS = {
    "explorer": ("Первая тропа", ("knife", "charm", "fang")),
    "watch": ("Лесной дозор", ("spear", "vest", "ring")),
    "ancient": ("След древних", ("amulet", "lantern", "star", "seal")),
}
TROPHIES = {
    "miner": ("Шахтёр", "Забери добычу из пещеры три раза."),
    "smith": ("Оружейник", "Улучши снаряжение три раза."),
    "champion": ("Чемпион дозора", "Выиграй три испытания."),
    "collector": ("Коллекционер", "Найди пять разных предметов."),
    "master": ("Хранитель коллекции", "Найди десять разных предметов."),
}


def init_town(db):
    init_workshop(db)
    init_guilds(db)
    init_contests(db)


def trophy_checks(db, user_id):
    found = db.execute("SELECT COUNT(*) FROM loot WHERE hero_id = ?", (user_id,)).fetchone()[0]
    return {
        "miner": count(db, user_id, "cave") >= 3,
        "smith": count(db, user_id, "forge") >= 3,
        "champion": count(db, user_id, "contests") >= 3,
        "collector": found >= 5,
        "master": found >= 10,
    }


def sage(db, user_id, action, key, day):
    if action == "gift":
        if not claim(db, user_id, "gift", day):
            return "Подарок за сегодня уже получен."
        add(db, user_id, "ore", 2)
        add(db, user_id, "herbs", 2)
        return "Подарок дня: +2 руды, +2 травы. " + reward(db, user_id, 0, 8) + "."
    if action in {"gather", "arena"}:
        done = count(db, user_id, f"cave:{day}") if action == "gather" else contest_status(db, user_id, "arena", day)[1]
        if not done:
            return "Сначала выполни ежедневное поручение."
        if not claim(db, user_id, f"task:{action}", day):
            return "Награда за это поручение сегодня уже получена."
        add(db, user_id, "marks", 1)
        return "Поручение выполнено. +1 знак. " + reward(db, user_id, 8, 6) + "."
    if action == "trophy" and key in TROPHIES:
        if not trophy_checks(db, user_id)[key]:
            return "Условие достижения ещё не выполнено."
        if not claim(db, user_id, f"trophy:{key}"):
            return "Этот трофей уже получен."
        return f"Трофей «{TROPHIES[key][0]}» получен. +1 к максимальному здоровью. {reward(db, user_id, 6, 8)}."
    return ""


def handle(db, hero, argument, now):
    section, action, value = parse(argument)
    user_id = hero["user_id"]
    if not action:
        return ""
    if section == "cave":
        return cave(db, hero, action, now)
    if section == "forge" and action != "item":
        return forge(db, hero, action, value)
    if section == "lab":
        return brew(db, user_id, action, now)
    if section == "trade" and action in EXCHANGE:
        label, currency, price, target, amount = EXCHANGE[action]
        accepted = spend_coins(db, user_id, price) if currency == "coins" else spend(db, user_id, currency, price)
        if not accepted:
            return "Недостаточно средств для обмена."
        add(db, user_id, target, amount)
        return f"Обмен выполнен. {label}."
    if section == "sage":
        return sage(db, user_id, action, value, now // DAY)
    if section == "battle":
        return contest(db, hero, action, value, now)
    if section == "clan":
        return guild_command(db, hero, action, value, now)
    if section == "mail" and action == "send":
        number, _, content = value.partition(" ")
        recipient = numeric_id(number)
        if recipient == user_id or not db.execute("SELECT 1 FROM heroes WHERE user_id = ?", (recipient,)).fetchone():
            return "Укажи номер другого героя и текст письма."
        if not content:
            return "Добавь текст письма."
        return board(db, user_id, f"mail:{recipient}", "post", content, now)
    if section == "pet":
        return pet(db, hero, action)
    if section == "training":
        return training(db, user_id, action)
    if section == "chest" and action == "energy":
        day = now // DAY
        if count(db, user_id, f"energy:{day}") < 3:
            return "Потрать три единицы энергии в испытаниях."
        if not claim(db, user_id, "energy-chest", day):
            return "Сегодня сундук уже открыт."
        add(db, user_id, "runes", 1)
        add(db, user_id, "marks", 2)
        return "Сундук открыт. +1 руна, +2 знака."
    if section == "collection" and action in COLLECTIONS:
        name, items = COLLECTIONS[action]
        owned = {row["item"] for row in db.execute("SELECT item FROM loot WHERE hero_id = ?", (user_id,))}
        if not set(items) <= owned:
            return "Коллекция ещё не собрана."
        if not claim(db, user_id, f"collection:{action}"):
            return "Награда коллекции уже получена."
        add(db, user_id, "marks", len(items))
        return f"Коллекция «{name}» закрыта. +{len(items)} знака."
    if section in {"chat", "forum", "guildchat"} and action != "open":
        return board(db, user_id, section, action, value, now)
    return ""


def parse(argument):
    section, separator, tail = argument.strip().partition(" ")
    action, _, value = tail.strip().partition(" ") if separator else ("", "", "")
    return section, action, value.strip()


def button(label, command):
    return {"label": label, "command": "town " + command}


def panel(db, hero, argument, now):
    section, action, value = parse(argument)
    user_id, day = hero["user_id"], now // DAY
    buttons, fields = [], []
    if section not in SECTIONS:
        return {"section": "", "title": "Поселение", "art": "village",
                "text": "Кузница, ремесло, добыча и общие испытания.",
                "buttons": [{**button(name, key), "art": image} for key, (name, image) in SECTIONS.items()], "fields": []}
    title, art = SECTIONS[section]
    text = ""
    if section == "cave":
        run = cave_run(db, user_id)
        if run:
            remaining = max(0, run["ready_at"] - now)
            text = f"{CAVE[run['trail']][0]} · " + (f"осталось {remaining} сек." if remaining else "добыча ждёт.")
            buttons = [button("Забрать добычу", "cave collect")]
        else:
            text = "Выбери ход. Пещера даёт руду, травы, иногда руны. Поход можно закончить и после перезапуска."
            buttons = [button(f"{name} · {seconds} сек.", f"cave {key}") for key, (name, seconds, _) in CAVE.items()]
    if section == "forge":
        rows = db.execute("SELECT item FROM loot WHERE hero_id = ? ORDER BY item", (user_id,)).fetchall()
        owned = {row["item"] for row in rows}
        text = "Заточка расходует руду, руна усиливает вещь, возвышение за знаки даёт дополнительные звёзды. Комплект дозора (рогатина, жилет и кольцо): +3 здоровья и +2 атаки."
        if value in owned:
            row = db.execute("SELECT sharpening, rune, stars FROM gear_upgrades WHERE user_id = ? AND item = ?",
                             (user_id, value)).fetchone()
            sharpen, rune, stars = tuple(row) if row else (0, 0, 0)
            text += f"\n{ITEMS[value][0]} · заточка {sharpen}/3 · руна {rune}/1 · звёзды {stars}/2."
            buttons = [button(label, f"forge {key} {value}") for key, label, _ in FORGE_ACTIONS]
            buttons.append(button("К списку вещей", "forge"))
        else:
            buttons = [button(ITEMS[row["item"]][0], f"forge item {row['item']}") for row in rows]
            buttons.extend([button("Кольцо · 4 руды, ур. 3", "forge make ring"),
                            button("Амулет · 8 руды, ур. 5", "forge make amulet")])
    if section == "lab":
        effect = active_effect(db, user_id, now)
        text = "Свари настой из пещерных трав. Одновременно действует один настой."
        if effect:
            text += f"\n{POTIONS[effect['effect']][0]} · осталось {(effect['expires'] - now + 59) // 60} мин."
        buttons = [button(f"{name} · {cost} трав", f"lab {key}") for key, (name, _, cost) in POTIONS.items()]
        text += "\n" + "\n".join(f"{name}: {description}" for name, description, _ in POTIONS.values())
    if section == "trade":
        text = f"Внутриигровой обмен. У героя {hero['coins']} монет."
        buttons = [button(label, f"trade {key}") for key, (label, *_) in EXCHANGE.items()]
    if section == "sage":
        text = "Подарок и поручения обновляются в 00:00 UTC. Трофеи дают постоянное здоровье."
        tasks = (("gift", "Подарок дня"), ("gather", "Добыча из пещеры"), ("arena", "Победа на арене"))
        for key, label in tasks:
            prize = key if key == "gift" else f"task:{key}"
            if not claimed(db, user_id, prize, day):
                buttons.append(button(label, f"sage {key}"))
        for key, ready in trophy_checks(db, user_id).items():
            name, description = TROPHIES[key]
            done = claimed(db, user_id, f"trophy:{key}")
            text += f"\n{'✓' if done else '○'} {name} · {description}"
            if ready and not done:
                buttons.append(button(f"Забрать: {name}", f"sage trophy {key}"))
    if section == "battle":
        run = active_contest(db, user_id, day)
        league = count(db, user_id, "league")
        division = "Бронза" if league < 15 else "Серебро" if league < 45 else "Золото"
        available_energy, _ = energy(db, user_id, now)
        text = (f"Лига: {division} · {league} очков. Энергия: {available_energy}/6. "
                "Восстановление: 1 за 15 минут. Попытки и дневные награды обновляются в 00:00 UTC.")
        if run:
            text += "\n" + contest_scene(run)
            buttons = [button(name, f"battle {key} {run['token']}") for key, name in STANCES.items()]
            buttons.append(button("Отступить", f"battle retreat {run['token']}"))
        else:
            for key, (name, level, maximum, _, description) in MODES.items():
                attempts, _ = contest_status(db, user_id, key, day)
                text += f"\n{name}: {description}"
                buttons.append(button(f"{name} · ур. {level} · {maximum - attempts}/{maximum}", f"battle start {key}"))
        buttons.append(button("Забрать дневную награду лиги", "battle prize"))
    if section == "clan":
        text = guild_text(db, user_id, now)
        guild = guild_of(db, user_id)
        if guild:
            buttons = [button("Покинуть клан", "clan leave"), button("Клановый чат", "guildchat")]
            if guild["leader"] == user_id:
                buttons.append(button("Изменить правила вступления", "clan toggle"))
                fields = [("Номер героя для приглашения", "clan invite"),
                          ("Номер героя для одобрения", "clan approve")]
        else:
            buttons = [button(f"Принять приглашение: {row['name']}", f"clan accept {row['id']}")
                       for row in invitations(db, user_id)]
            fields = [("Название клана", "clan create"), ("Номер клана", "clan join")]
        buttons.append(button("Награда за прошлую неделю", "clan prize"))
    if section == "records":
        kind = action if action in MODES or action == "league" else "heroes"
        leaders = rankings(db, kind, day)
        label = "Уровень и опыт" if kind == "heroes" else "Лига" if kind == "league" else MODES[kind][0]
        text = f"{label}\nМои записи: пещера {count(db, user_id, 'cave')} · испытания {count(db, user_id, 'contests')} · кузница {count(db, user_id, 'forge')}."
        text += "\n" + ("\n".join(f"{index}. {row['name']} · {row['points']}"
                                     for index, row in enumerate(leaders, 1)) or "Записей пока нет.")
        buttons = [button("Герои", "records"), button("Лига", "records league")]
        buttons.extend(button(mode[0], f"records {key}") for key, mode in MODES.items())
    if section == "pet":
        owned = companion(db, user_id)
        if owned:
            name, bonus = PETS[owned["kind"]]
            art = owned["kind"]
            text = f"{name} · ранг {owned['rank']}/3. {bonus}"
            if owned["rank"] < 3:
                buttons.append(button(f"Покормить · {owned['rank'] + 2} трав", "pet feed"))
        else:
            text = "Возьми одного спутника со 2-го уровня за 25 монет."
            buttons = [button(name, f"pet {key}") for key, (name, _) in PETS.items()]
    if section == "training":
        text = "Основные тренировки дают +1 к атаке или +2 к здоровью. У каждого упражнения три ранга."
        for key, name in (("attack", "Атака"), ("health", "Здоровье")):
            rank = count(db, user_id, f"training:{key}")
            text += f"\n{name} · ранг {rank}/3."
            if rank < 3:
                buttons.append(button(f"{name} · {12 + 8 * rank} монет", f"training {key}"))
    if section == "chest":
        spent = min(3, count(db, user_id, f"energy:{day}"))
        text = f"За три единицы энергии в испытаниях можно открыть суточный сундук. Сегодня: {spent}/3."
        if not claimed(db, user_id, "energy-chest", day):
            buttons.append(button("Открыть сундук", "chest energy"))
    if section == "mail":
        text = f"Твой номер для писем и дуэлей: {user_id}.\n" + board_text(db, f"mail:{user_id}")
        fields = [("Номер героя и текст письма", "mail send")]
    if section == "collection":
        owned = {row["item"] for row in db.execute("SELECT item FROM loot WHERE hero_id = ?", (user_id,))}
        rows = []
        for key, (name, items) in COLLECTIONS.items():
            found = len(owned.intersection(items))
            rows.append(f"{name} · {found}/{len(items)}. " + ", ".join(ITEMS[item][0] for item in items))
            if found == len(items) and not claimed(db, user_id, f"collection:{key}"):
                buttons.append(button(f"Забрать: {name}", f"collection {key}"))
        text = "\n".join(rows)
    if section in {"chat", "forum", "guildchat"}:
        room = section
        if section == "guildchat":
            guild = guild_of(db, user_id)
            room = f"guild:{guild['id']}" if guild else None
        if room:
            text = (board(db, user_id, room, "open", value, now)
                    if room == "forum" and action == "open" else board_text(db, room))
            fields = [("Текст сообщения", f"{section} post")]
            if section == "forum":
                fields = [("Новая тема", "forum post"), ("Номер темы", "forum open"),
                          ("Номер темы и текст ответа", "forum reply")]
        else:
            text = "Клановый чат доступен участникам клана."

    if section in {"cave", "forge", "lab", "trade", "sage", "battle", "pet", "chest"}:
        text += "\n" + materials_text(db, user_id)
    return {"section": section, "title": title, "art": art, "text": text,
            "buttons": buttons, "fields": [{"label": label, "command": "town " + cmd} for label, cmd in fields]}


def town_text(view):
    lines = [view["title"], view["text"]]
    lines.extend(f"/{field['command']} … — {field['label']}" for field in view["fields"])
    return "\n".join(lines)
