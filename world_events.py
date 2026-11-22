"""Work plans and the events available during time away from Telegram."""
JOBS = {
    "roam": ("Странствия", "Свободные встречи, находки и опасности.", "village"),
    "patrol": ("Дозор", "Чаще вступаешь в бои, помогаешь путникам и развиваешь следопыта.", "patrol"),
    "forage": ("Сбор трав", "Ищешь растения и развиваешь травника.", "forage"),
    "camp": ("Лагерь", "Спокойная работа с припасами, меньше риска, скромные награды.", "camp"),
}

# Description, experience, coin, scout points, herbalist points, item, enemy.
EVENTS = {
    "herbs": ("Ты нашёл лечебные травы у ручья.", 5, 2, 0, 1, None, None),
    "traveler": ("Ты вывел заблудившегося путника к дороге.", 6, 3, 1, 0, None, None),
    "wolf": ("лесным волком", 10, 5, 1, 0, "fang", (10, 3)),
    "ghost": ("курганным призраком", 10, 5, 1, 0, "lantern", (16, 4)),
    "merchant": ("Странствующий торговец заплатил за помощь с повозкой.", 6, 7, 1, 0, None, None),
    "chest": ("Ты отыскал запертый сундук и нашёл ключ под корнями.", 8, 9, 1, 0, None, None),
    "storm": ("Ливень смыл следы. Ты укрылся и перевязал промокшие припасы.", 3, 0, 0, 1, None, None),
    "caravan": ("Караванщики наградили тебя за охрану перевала.", 8, 7, 1, 0, "cloak", None),
    "relic": ("У древнего алтаря ты зарисовал руну и отыскал подношение.", 8, 5, 1, 0, None, None),
    "fireflies": ("Светляки привели тебя к редким лекарственным растениям.", 7, 3, 0, 1, None, None),
    "camp": ("У костра ты разобрал припасы и подписал лекарственные сборы.", 4, 2, 0, 1, None, None),
}
POOLS = {
    "roam": tuple(EVENTS),
    "patrol": ("wolf", "wolf", "ghost", "traveler", "caravan", "chest", "storm"),
    "forage": ("herbs", "herbs", "fireflies", "fireflies", "storm", "relic"),
    "camp": ("camp", "camp", "camp", "herbs", "merchant"),
}
