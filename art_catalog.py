"""Illustration keys and the player-facing gallery."""
from pathlib import Path

from world_events import EVENTS


ASSET_DIR = Path(__file__).resolve().parent / "assets"
GALLERY = {
    "places": ("Места и сражения", {
        "village": "Поселение на границе леса",
        "misty-forest": "Туманный лес",
        "old-tower": "Старая башня",
        "ash-keeper": "Пепельный смотритель",
        "colossus": "Каменный колосс",
        "arena": "Дуэльный двор",
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
        "rewards": "Опыт и монеты",
        "bag": "Походная сумка",
        "journal": "Журнал героя",
        "quests": "Доска заданий",
    }),
}
TITLES = {key: title for _, entries in GALLERY.values() for key, title in entries.items()}
ROUTE_ART = {"forest": "misty-forest", "ruins": "old-tower"}
CHOICE_ART = {
    "forest": {"1": "forest-tracks", "2": "moon-mint"},
    "ruins": {"1": "tower-gallery", "2": "tower-decoction"},
}
QUEST_ART = {"forest": "mira", "keeper": "orin"}
SCREEN_ART = {
    "/start": "village", "/help": "village", "/create": "hero", "/hero": "hero",
    "/adventure": "village", "/bag": "bag", "/npc": "quests", "/quest": "quests",
    "/professions": "hero", "/train": "hero", "/boss": "ash-keeper",
    "/raid": "colossus", "/pvp": "arena", "/journal": "journal",
}
JOURNAL_ART = {event[0]: key for key, event in EVENTS.items()}


def illustration_path(key):
    if key in TITLES:
        return ASSET_DIR / f"{key}.jpg"
    return None
