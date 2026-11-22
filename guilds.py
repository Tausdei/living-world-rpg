"""Player guilds, weekly team scores and in-game communication."""
import re

from activities import numeric_id, reward
from workshop import claim, spend_coins


GUILD_NAME = re.compile(r"[\w -]{2,24}")
WEEK = 7 * 86400


def week_index(now):
    return (now + 3 * 86400) // WEEK


def init_guilds(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            leader INTEGER NOT NULL REFERENCES heroes(user_id),
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS guild_members (
            user_id INTEGER PRIMARY KEY REFERENCES heroes(user_id),
            guild INTEGER NOT NULL REFERENCES guilds(id)
        );
        CREATE INDEX IF NOT EXISTS guild_members_group ON guild_members(guild, user_id);
        CREATE TABLE IF NOT EXISTS guild_admission (
            guild INTEGER PRIMARY KEY REFERENCES guilds(id),
            approval INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS guild_invites (
            guild INTEGER NOT NULL REFERENCES guilds(id),
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            invited INTEGER NOT NULL,
            PRIMARY KEY(guild, user_id)
        );
        CREATE TABLE IF NOT EXISTS league_contributions (
            week INTEGER NOT NULL,
            guild INTEGER NOT NULL REFERENCES guilds(id),
            user_id INTEGER NOT NULL REFERENCES heroes(user_id),
            points INTEGER NOT NULL,
            PRIMARY KEY(week, guild, user_id)
        );
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author INTEGER NOT NULL REFERENCES heroes(user_id),
            room TEXT NOT NULL,
            thread INTEGER REFERENCES boards(id),
            body TEXT NOT NULL,
            sent_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS boards_room ON boards(room, thread, id);
        CREATE INDEX IF NOT EXISTS boards_author ON boards(author, sent_at);
    """)


def guild_of(db, user_id):
    return db.execute("""
        SELECT guilds.* FROM guild_members JOIN guilds ON guild_members.guild = guilds.id
        WHERE guild_members.user_id = ?
    """, (user_id,)).fetchone()


def guild_rank(db, week, limit=10):
    return db.execute("""
        SELECT guilds.id, name, SUM(points) AS total
        FROM league_contributions JOIN guilds ON guilds.id = guild
        WHERE week = ? GROUP BY guilds.id ORDER BY total DESC, guilds.id LIMIT ?
    """, (week, limit)).fetchall()


def contribute(db, user_id, now, points):
    guild = guild_of(db, user_id)
    if guild:
        db.execute("""
            INSERT INTO league_contributions VALUES (?, ?, ?, ?)
            ON CONFLICT(week, guild, user_id) DO UPDATE SET points = points + excluded.points
        """, (week_index(now), guild["id"], user_id, points))


def requires_approval(db, clan_id):
    row = db.execute("SELECT approval FROM guild_admission WHERE guild = ?", (clan_id,)).fetchone()
    return bool(row and row["approval"])


def invitations(db, user_id):
    return db.execute("""
        SELECT guilds.id, name FROM guild_invites JOIN guilds ON guild_invites.guild = guilds.id
        WHERE guild_invites.user_id = ? AND invited = 1 AND active = 1 ORDER BY guilds.id LIMIT 5
    """, (user_id,)).fetchall()


def admit(db, target, user_id):
    count = db.execute("SELECT COUNT(*) FROM guild_members WHERE guild = ?", (target["id"],)).fetchone()[0]
    if count >= 20:
        return "В клане уже 20 героев."
    db.execute("INSERT INTO guild_members VALUES (?, ?)", (user_id, target["id"]))
    db.execute("DELETE FROM guild_invites WHERE user_id = ?", (user_id,))
    return f"Герой вступил в клан «{target['name']}»."


def guild_command(db, hero, action, argument, now):
    user_id = hero["user_id"]
    guild = guild_of(db, user_id)
    if action == "prize":
        week = week_index(now) - 1
        leaders = guild_rank(db, week, 3)
        for place, leader in enumerate(leaders, 1):
            contributed = db.execute("""
                SELECT 1 FROM league_contributions WHERE week = ? AND guild = ? AND user_id = ?
            """, (week, leader["id"], user_id)).fetchone()
            if contributed:
                if not claim(db, user_id, "guild-prize", week):
                    return "Награда за прошлую неделю уже получена."
                return f"Клан занял место {place}. {reward(db, user_id, 12, 45 - 10 * place)}."
        return "За прошлую неделю нет награды клана. Она доступна участникам трёх лучших кланов."
    if action == "create":
        name = argument.strip()
        if guild:
            return "Сначала выйди из клана."
        if not GUILD_NAME.fullmatch(name):
            return "Введи название клана из 2–24 букв, цифр и пробелов."
        if 1 + hero["xp"] // 30 < 2:
            return "Клан можно создать со 2-го уровня."
        if db.execute("SELECT 1 FROM guilds WHERE lower(name) = lower(?)", (name,)).fetchone():
            return "Название уже занято."
        if not spend_coins(db, user_id, 25):
            return "Создание клана стоит 25 монет."
        clan_id = db.execute("INSERT INTO guilds(name, leader) VALUES (?, ?)", (name, user_id)).lastrowid
        db.execute("INSERT INTO guild_members VALUES (?, ?)", (user_id, clan_id))
        return f"Клан «{name}» основан. Номер для вступления: {clan_id}."
    if action in {"toggle", "invite", "approve"}:
        if not guild or guild["leader"] != user_id:
            return "Действие доступно главе клана."
        clan_id = guild["id"]
        if action == "toggle":
            value = int(not requires_approval(db, clan_id))
            db.execute("""
                INSERT INTO guild_admission VALUES (?, ?)
                ON CONFLICT(guild) DO UPDATE SET approval = excluded.approval
            """, (clan_id, value))
            return "Для вступления теперь нужна заявка." if value else "Клан открыт для вступления."
        target_id = numeric_id(argument)
        if not db.execute("SELECT 1 FROM heroes WHERE user_id = ?", (target_id,)).fetchone() or guild_of(db, target_id):
            return "Выбери героя, который пока без клана."
        if action == "invite":
            db.execute("INSERT OR REPLACE INTO guild_invites VALUES (?, ?, 1)", (clan_id, target_id))
            return f"Герой №{target_id} увидит приглашение в разделе кланов."
        if not db.execute("SELECT 1 FROM guild_invites WHERE guild = ? AND user_id = ? AND invited = 0",
                          (clan_id, target_id)).fetchone():
            return "Заявки от этого героя нет."
        return admit(db, guild, target_id)
    if action in {"join", "accept"}:
        if guild:
            return "Ты уже состоишь в клане."
        clan_id = numeric_id(argument)
        target = db.execute("SELECT * FROM guilds WHERE id = ? AND active = 1", (clan_id,)).fetchone()
        if not target:
            return "Клан с таким номером не найден."
        invite = db.execute("SELECT invited FROM guild_invites WHERE guild = ? AND user_id = ?",
                            (clan_id, user_id)).fetchone()
        if invite and invite["invited"]:
            return admit(db, target, user_id)
        if action == "accept":
            return "Активного приглашения нет."
        if requires_approval(db, clan_id):
            db.execute("INSERT OR IGNORE INTO guild_invites VALUES (?, ?, 0)", (clan_id, user_id))
            return "Заявка передана главе клана."
        return admit(db, target, user_id)
    if action == "leave":
        if not guild:
            return "Ты пока без клана."
        db.execute("DELETE FROM guild_members WHERE user_id = ?", (user_id,))
        if guild["leader"] == user_id:
            successor = db.execute("SELECT user_id FROM guild_members WHERE guild = ? ORDER BY user_id LIMIT 1",
                                   (guild["id"],)).fetchone()
            if successor:
                db.execute("UPDATE guilds SET leader = ? WHERE id = ?", (successor["user_id"], guild["id"]))
            else:
                db.execute("UPDATE guilds SET active = 0 WHERE id = ?", (guild["id"],))
        return "Ты покинул клан."
    return "Кланы набирают очки за испытания и рейды. Соревнование обновляется раз в неделю (UTC)."


def guild_text(db, user_id, now):
    guild = guild_of(db, user_id)
    rows = []
    if guild:
        roster = db.execute("""
            SELECT name FROM guild_members JOIN heroes USING(user_id)
            WHERE guild = ? ORDER BY user_id
        """, (guild["id"],)).fetchall()
        members = ", ".join(member["name"] for member in roster)
        admission = "по заявке" if requires_approval(db, guild["id"]) else "свободное вступление"
        rows.extend([f"Твой клан: {guild['name']} · №{guild['id']} · {admission}", f"Состав: {members}"])
        if guild["leader"] == user_id:
            requests = db.execute("""
                SELECT heroes.name, heroes.user_id FROM guild_invites JOIN heroes USING (user_id)
                WHERE guild = ? AND invited = 0 ORDER BY user_id LIMIT 10
            """, (guild["id"],))
            rows.extend(f"Заявка: {row['name']} · №{row['user_id']}" for row in requests)
    else:
        rows.append("Создай клан за 25 монет или вступи по номеру.")
        available = db.execute("SELECT id, name FROM guilds WHERE active = 1 ORDER BY id DESC LIMIT 5")
        rows.extend(f"№{row['id']} · {row['name']}" for row in available)
    leaders = guild_rank(db, week_index(now), 5)
    rows.append("Командный турнир недели · обновление в понедельник, 00:00 UTC")
    rows.extend(f"{place}. {row['name']} · {row['total']} очков" for place, row in enumerate(leaders, 1))
    if not leaders:
        rows.append("Очков пока нет.")
    return "\n".join(rows)


def board(db, user_id, room, action, argument, now):
    if room == "guildchat":
        guild = guild_of(db, user_id)
        if not guild:
            return "Клановый чат доступен участникам клана."
        room = f"guild:{guild['id']}"
    if room == "forum" and action == "open":
        thread_id = numeric_id(argument)
        thread = db.execute("SELECT id FROM boards WHERE id = ? AND room = 'forum' AND thread IS NULL",
                            (thread_id,)).fetchone()
        return board_text(db, "forum", thread_id) if thread else "Тема не найдена."
    if action not in {"post", "reply"}:
        return board_text(db, room)
    thread_id = None
    content = argument.strip()
    if action == "reply":
        number, _, content = content.partition(" ")
        thread_id = numeric_id(number)
        parent = db.execute("SELECT 1 FROM boards WHERE id = ? AND room = 'forum' AND thread IS NULL",
                            (thread_id,)).fetchone()
        if room != "forum" or not parent:
            return "Укажи номер темы и текст ответа."
    if not 1 <= len(content) <= 200 or any(not char.isprintable() for char in content):
        return "Сообщение должно содержать от 1 до 200 символов."
    if db.execute("SELECT 1 FROM boards WHERE author = ? AND sent_at > ?", (user_id, now - 10)).fetchone():
        return "Между сообщениями должно пройти 10 секунд."
    db.execute("INSERT INTO boards(author, room, thread, body, sent_at) VALUES (?, ?, ?, ?, ?)",
               (user_id, room, thread_id, content, now))
    return "Сообщение опубликовано."


def board_text(db, room, thread=None):
    rows = db.execute("""
        SELECT boards.*, name FROM boards JOIN heroes ON author = heroes.user_id
        WHERE room = ? AND thread IS ? ORDER BY boards.id DESC LIMIT 5
    """, (room, thread)).fetchall()
    lines = []
    if thread:
        parent = db.execute("SELECT body FROM boards WHERE id = ?", (thread,)).fetchone()
        lines.append(f"Тема №{thread}: {parent['body']}")
    lines.extend(f"№{row['id']} · {row['name']}: {row['body']}" for row in reversed(rows))
    return "\n".join(lines) or "Здесь пока нет сообщений."
