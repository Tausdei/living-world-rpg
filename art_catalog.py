"""Illustration keys and the player-facing gallery."""
from pathlib import Path

from activities import QUESTS
from adventures import ROUTES
from world_events import EVENTS


ASSET_DIR = Path(__file__).resolve().parent / "assets"
GALLERY = {
    "places": ("Места и сражения", {
        "village": "Поселение на границе леса",
        "misty-forest": "Туманный лес",
        **{area.art: area.title for key, area in ROUTES.items() if key != "forest"},
        "ash-keeper": "Пепельный смотритель",
        "colossus": "Каменный колосс",
        "arena": "Дуэльный двор",
        "mine": "Ходы под поселением",
        "smithy": "Кузница",
        "laboratory": "Лаборатория",
        "coliseum": "Каменный круг",
        "guildhall": "Клановый зал",
        "sage": "Хижина мудреца",
        "bandit": "Лесной разбойник",
        "boar": "Дикий кабан",
    }),
    "people": ("Герои и профессии", {
        "hero": "Портрет странника",
        "mira": "Дозорница Мира",
        "orin": "Архивист Орин",
        "scout": "Следопыт",
        "herbalist": "Травник",
        "scout-game": "Испытание следопыта",
        "herbalist-game": "Испытание травника",
    }),
    "events": ("Походы и события", {
        "forest-tracks": "Следы у затопленного моста",
        "moon-mint": "Лунная мята",
        "tower-gallery": "Обходная галерея башни",
        "tower-decoction": "Отвар против дыма",
        "wolf": "Лесной волк",
        "ghost": "Курганный призрак",
        "traveler": "Заблудившийся путник",
        "herbs": "Лечебные травы у ручья",
    }),
    "offline": ("Жизнь между визитами", {
        "merchant": "Странствующий торговец",
        "chest": "Запертый сундук",
        "storm": "Ливень",
        "caravan": "Охрана каравана",
        "relic": "Древний алтарь",
        "fireflies": "Поляна светляков",
        "camp": "Работа у костра",
        "patrol": "Лесной дозор",
        "forage": "Сбор трав",
        "ferry": "Замёрзшая переправа",
        "raven": "Ворон с донесением",
        "apiary": "Пасека",
        "wheelwright": "Мастерская колёсника",
        "snare": "Зверь в силке",
        "monastery": "Приют в монастыре",
        "fungus": "Грибная пещера",
        "meteor": "Упавшая звезда",
    }),
    "items": ("Добыча и награды", {
        "knife": "Походный нож",
        "blade": "Клинок стражи",
        "charm": "Плетёный оберег",
        "seal": "Печать смотрителя",
        "star": "Осколок звезды",
        "vest": "Кожаный жилет",
        "spear": "Рогатина дозорного",
        "cloak": "Плащ путника",
        "fang": "Волчий клык",
        "lantern": "Фонарь духов",
        "ring": "Кольцо дозора",
        "amulet": "Амулет искателей",
        "rewards": "Опыт и монеты",
        "bag": "Походная сумка",
        "journal": "Журнал героя",
        "quests": "Доска заданий",
    }),
}
TITLES = {key: title for _, entries in GALLERY.values() for key, title in entries.items()}
ROUTE_ART = {key: area.art for key, area in ROUTES.items()}
CHOICE_ART = {
    "forest": {"1": "forest-tracks", "2": "moon-mint"},
    "ruins": {"1": "tower-gallery", "2": "tower-decoction"},
}
QUEST_ART = {key: "mira" if npc == "Дозорница Мира" else "orin" for key, (npc, *_) in QUESTS.items()}
SCREEN_ART = {
    "/start": "village", "/help": "village", "/create": "hero", "/hero": "hero",
    "/adventure": "village", "/bag": "bag", "/npc": "quests", "/quest": "quests",
    "/professions": "hero", "/train": "hero", "/boss": "ash-keeper",
    "/raid": "colossus", "/pvp": "arena", "/journal": "journal",
}
JOURNAL_ART = {event[0]: key for key, event in EVENTS.items()}


def event_illustration(summary):
    description = summary.partition(" +")[0]
    return next((key for phrase, key in JOURNAL_ART.items() if phrase in description), None)


def illustration_path(key):
    if key in TITLES:
        return ASSET_DIR / f"{key}.jpg"
    return None
