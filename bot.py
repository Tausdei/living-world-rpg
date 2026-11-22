"""Telegram long-polling adapter with a persistent single-message outbox."""
import json
import os
import re
import sys
import time
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from art_catalog import TITLES, illustration_path
from game import COMMANDS, connect, parse_command, play
from telegram_menu import callback_command, present
from world import advance_world


class TelegramError(Exception):
    pass


def telegram(token, method, photo=None, **params):
    if photo is None:
        body = json.dumps(params).encode()
        content_type = "application/json"
    else:
        boundary = uuid4().hex
        parts = []
        for key, value in params.items():
            field = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{field}\r\n'.encode()
            )
        parts.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="illustration.jpg"\r\n'
             'Content-Type: image/jpeg\r\n\r\n').encode() + photo + b"\r\n"
        )
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        content_type = f"multipart/form-data; boundary={boundary}"
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": content_type},
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
    callback = update.get("callback_query")
    message = callback.get("message", {}) if callback else update.get("message", {})
    sender = (callback or message).get("from", {})
    chat_id = message.get("chat", {}).get("id")
    content = message.get("text", "") if not callback else ""
    update_id = update["update_id"]
    with db:
        db.execute("BEGIN IMMEDIATE")
        reply = None
        ui = {}
        if callback:
            ui["callback"] = {"callback_query_id": callback["id"]}
            if sender and chat_id is not None:
                content, notice = callback_command(db, sender["id"], callback.get("data", ""))
                if notice:
                    ui["callback"]["text"] = notice
        if chat_id is not None and content.lstrip().startswith("/") and sender and not sender.get("is_bot"):
            user_id = sender["id"]
            parsed = parse_command(content, bot_name)
            if parsed:
                command, argument = parsed
                previous = None
                if command == "/choose":
                    previous = db.execute("SELECT route FROM heroes WHERE user_id = ?", (user_id,)).fetchone()
                reply = play(db, user_id, content, bot_name)
                if reply:
                    ui["markup"], ui["art"] = present(
                        db, user_id, update_id, reply, command, argument, previous["route"] if previous else None
                    )
        db.execute(
            "UPDATE delivery SET next_offset = ?, chat_id = ?, reply = ? WHERE id = 1",
            (update_id + 1, chat_id if reply else None, reply),
        )
        db.execute(
            "INSERT OR REPLACE INTO delivery_controls (id, payload) VALUES (1, ?)", (json.dumps(ui),)
        )


def deliver_message(token, pending, ui):
    params = {"chat_id": pending["chat_id"]}
    if "markup" in ui:
        params["reply_markup"] = ui["markup"]
    reply = pending["reply"]
    art = ui.get("art") or ("misty-forest" if ui.get("forest_photo") else None)
    path = illustration_path(art)
    if path and path.is_file():
        # Telegram counts captions in UTF-16 code units.
        fits_caption = len(reply.encode("utf-16-le")) <= 2048
        photo_params = params if fits_caption else {"chat_id": pending["chat_id"]}
        try:
            telegram(token, "sendPhoto", photo=path.read_bytes(),
                     caption=reply if fits_caption else TITLES[art], **photo_params)
            if fits_caption:
                return
        except TelegramError as error:
            if error.args[0] != 400:
                raise
    telegram(token, "sendMessage", text=reply, **params)


def send_pending(db, token):
    pending = db.execute("""
        SELECT delivery.*, payload FROM delivery LEFT JOIN delivery_controls USING (id)
    """).fetchone()
    ui = json.loads(pending["payload"]) if pending["payload"] else {}
    if "callback" in ui:
        try:
            telegram(token, "answerCallbackQuery", **ui["callback"])
        except TelegramError as error:
            if error.args[0] != 400:
                raise
    if pending["reply"]:
        try:
            deliver_message(token, pending, ui)
        except TelegramError as error:
            if error.args[0] not in {400, 403}:
                raise
            print(f"Ответ недоставлен (Telegram {error}).", file=sys.stderr)
    if pending["reply"] or pending["payload"]:
        with db:
            db.execute("UPDATE delivery SET reply = NULL, chat_id = NULL WHERE id = 1")
            db.execute("DELETE FROM delivery_controls WHERE id = 1")
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
                updates = telegram(token, "getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
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
