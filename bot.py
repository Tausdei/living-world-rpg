"""Telegram long-polling adapter with a persistent single-message outbox."""
import json
import os
import re
import sys
import time
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from game import COMMANDS, connect, play
from world import advance_world


class TelegramError(Exception):
    pass


def telegram(token, method, **params):
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=40) as response:
            result = json.load(response)
    except HTTPError as error:
        raise TelegramError(error.code) from None
    except (URLError, OSError, ValueError):
        raise TelegramError("сбой соединения или ответа") from None
    if not result["ok"]:
        raise TelegramError(result.get("error_code", "ошибка API"))
    return result["result"]


def queue_reply(db, update, bot_name):
    message = update.get("message", {})
    sender = message.get("from", {})
    chat = message.get("chat", {})
    content = message.get("text", "")
    with db:
        # Acquire the write lock before reading or changing player state.
        db.execute("BEGIN IMMEDIATE")
        reply = None
        if content.lstrip().startswith("/") and sender and not sender.get("is_bot"):
            reply = play(db, sender["id"], content, bot_name)
        db.execute(
            "UPDATE delivery SET next_offset = ?, chat_id = ?, reply = ? WHERE id = 1",
            (update["update_id"] + 1, chat.get("id") if reply else None, reply),
        )


def send_pending(db, token):
    pending = db.execute("SELECT * FROM delivery").fetchone()
    if pending["reply"]:
        try:
            telegram(token, "sendMessage", chat_id=pending["chat_id"], text=pending["reply"])
        except TelegramError as error:
            # A departed chat or blocked bot must not stall everyone else's game.
            if error.args[0] not in {400, 403}:
                raise
            print(f"Ответ недоставлен (Telegram {error}).", file=sys.stderr)
        with db:
            db.execute("UPDATE delivery SET reply = NULL, chat_id = NULL WHERE id = 1")
    return pending["next_offset"]


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        sys.exit("Укажи действующий TELEGRAM_BOT_TOKEN в переменных окружения.")
    try:
        bot_name = telegram(token, "getMe")["username"].lower()
        telegram(token, "setMyCommands", commands=[
            {"command": name, "description": description}
            for name, description in COMMANDS.items()
        ])
    except TelegramError as error:
        sys.exit(f"Не удалось запустить бота (Telegram {error}).")

    with closing(connect(os.environ.get("GAME_DB", "living-world.sqlite3"))) as db:
        print(f"Бот @{bot_name} запущен.", flush=True)
        while True:
            try:
                advance_world(db)
                offset = send_pending(db, token)
                updates = telegram(token, "getUpdates", offset=offset, timeout=25, allowed_updates=["message"])
                for update in updates:
                    queue_reply(db, update, bot_name)
                    send_pending(db, token)
            except TelegramError as error:
                if error.args[0] in {401, 409}:
                    sys.exit(f"Telegram {error}. Проверь токен, webhook и другие экземпляры бота.")
                print(f"Telegram {error}. Повтор через 5 секунд.", file=sys.stderr)
                time.sleep(5)


if __name__ == "__main__":
    main()
