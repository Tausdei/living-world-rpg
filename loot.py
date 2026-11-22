"""Equipment definitions and shared inventory mutations."""
ITEMS = {
    "knife": ("Походный нож", "weapon", 1),
    "blade": ("Клинок стражи", "weapon", 3),
    "charm": ("Плетёный оберег", "charm", 2),
    "seal": ("Печать смотрителя", "charm", 4),
    "star": ("Осколок звезды", "charm", 6),
    "vest": ("Кожаный жилет", "armor", 4),
    "spear": ("Рогатина дозорного", "weapon", 4),
    "cloak": ("Плащ путника", "armor", 6),
    "fang": ("Волчий клык", "charm", 3),
    "lantern": ("Фонарь духов", "charm", 5),
    "ring": ("Кольцо дозора", "ring", 1),
    "amulet": ("Амулет искателей", "amulet", 2),
}


def grant_item(db, hero_id, item):
    db.execute("""
        INSERT INTO loot VALUES (?, ?, 1)
        ON CONFLICT (hero_id, item) DO UPDATE SET quantity = quantity + 1
    """, (hero_id, item))
    return f"добыча: {ITEMS[item][0]} ({item})"


def gear_bonuses(db, hero_id):
    health = attack = 0
    worn = set()
    for row in db.execute("""
        SELECT equipped.item, COALESCE(sharpening, 0) + COALESCE(rune, 0) + COALESCE(stars, 0) AS increase
        FROM equipped LEFT JOIN gear_upgrades
        ON equipped.hero_id = gear_upgrades.user_id AND equipped.item = gear_upgrades.item
        WHERE equipped.hero_id = ?
    """, (hero_id,)):
        worn.add(row["item"])
        _, slot, bonus = ITEMS[row["item"]]
        bonus += row["increase"]
        if slot == "weapon":
            attack += bonus
        else:
            health += bonus
    if {"spear", "vest", "ring"} <= worn:
        health += 3
        attack += 2
    return health, attack
