"""Telegram button layouts for background work, hunts and profession challenges."""
import re

from fieldwork import ENEMIES, HUNT_ACTIONS, active_hunt, active_practice, practice_question
from world import current_job
from world_events import JOBS


HUNT_MENU = (("Охота", "hunt"), ("Сумка", "bag"))
PRACTICE_MENU = (("Мини-игры", "practice"), ("Профессии", "professions"))
HUNT_ART = {"keeper": "ash-keeper"}
PRACTICE_ART = {"scout": "scout-game", "herbalist": "herbalist-game"}
HUNT_COMMANDS = {"/hunt", "/turn", "/boss"}
PRACTICE_COMMANDS = {"/practice", "/practice_answer"}
ACTIONS = {
    "offline", "hunt", "practice",
    *(f"offline_{job}" for job in JOBS),
    *(f"hunt_{enemy}" for enemy in ENEMIES),
    *(f"practice_{skill}" for skill in PRACTICE_ART),
}
STEP = re.compile(r"(turn|quiz):([0-9a-f]{10}):([a-z0-9]+)")


def step_command(db, user_id, action):
    parsed = STEP.fullmatch(action)
    if not parsed:
        return None
    kind, token, choice = parsed.groups()
    if kind == "turn":
        state = active_hunt(db, user_id)
        command = f"/turn_{choice}" if choice in HUNT_ACTIONS else ""
    else:
        state = active_practice(db, user_id)
        command = f"/practice_answer_{choice}" if choice in {"1", "2", "3", "cancel"} else ""
    if state and state["token"] == token and command:
        return command, None
    return "", "Этот ход или ответ уже недоступен."


def previous_subject(db, user_id, command):
    if command == "/turn":
        state = active_hunt(db, user_id)
        return state["enemy"] if state else None
    if command == "/practice_answer":
        state = active_practice(db, user_id)
        return state["skill"] if state else None
    return None


def fieldwork_view(db, user_id, command, argument, previous):
    if command == "/offline":
        rows = [((name, f"offline_{key}"),) for key, (name, _, _) in JOBS.items()]
        rows.append((("Журнал", "journal"),))
        return rows, JOBS[current_job(db, user_id)][2]
    if command in HUNT_COMMANDS:
        state = active_hunt(db, user_id)
        enemy = state["enemy"] if state else previous or ("keeper" if command == "/boss" else argument)
        art = HUNT_ART.get(enemy, enemy) if enemy in ENEMIES else "patrol"
        if state:
            rows = [
                ((label, f"turn:{state['token']}:{action}"),)
                for action, label in HUNT_ACTIONS.items()
                if action != "heal" or not state["used_heal"]
            ]
        elif command == "/hunt" and not argument:
            rows = [((f"{name} · ур. {level}", f"hunt_{key}"),) for key, (name, level, *_) in ENEMIES.items()]
        else:
            rows = [HUNT_MENU]
        return rows, art
    if command in PRACTICE_COMMANDS:
        state = active_practice(db, user_id)
        skill = state["skill"] if state else previous or argument
        if state:
            _, labels, _ = practice_question(state)
            rows = [((label, f"quiz:{state['token']}:{choice}"),) for choice, label in enumerate(labels, 1)]
            rows.append((("Завершить испытание", f"quiz:{state['token']}:cancel"),))
        elif command == "/practice" and not argument:
            rows = [(("Читать следы", "practice_scout"),), (("Разобрать травы", "practice_herbalist"),)]
        else:
            rows = [PRACTICE_MENU]
        return rows, PRACTICE_ART.get(skill, "scout-game")
    return None
