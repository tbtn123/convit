from utils.singleton import ItemID as ITEMS

"""
hostile means agressive
loot means no attack damage


"""
class HawkThief:
    type = "hostile"
    name = "hawk thief"
    icon = ":eagle:"
    health = 10
    damage = 5
    crit_chance = 0.23
    parry_chance = 0.25
    bulletproof_chance = 0.4
    loot = [{
        "id": ITEMS.SCRAP, "amount": [1, 2], "chance": 0.4
    }, {
        "id": ITEMS.WOOD, "amount": [1, 2], "chance": 0.3
    }, {
        "id": ITEMS.STONE, "amount": [1, 1], "chance": 0.2
    }]


class Hawk:
    type = "hostile"
    name = "hawk"
    icon = ":eagle:"
    health = 15
    damage = 8
    crit_chance = 0.35
    parry_chance = 0.15
    bulletproof_chance = 0.2
    loot = [{
        "id": ITEMS.HERB, "amount": [1, 3], "chance": 0.5
    }, {
        "id": ITEMS.WOOD, "amount": [1, 3], "chance": 0.4
    }, {
        "id": ITEMS.STONE, "amount": [1, 2], "chance": 0.3
    }]


class HawkGoblin:
    type = "hostile"
    name = "hawk goblin"
    icon = ":eagle:"
    health = 12
    damage = 6
    crit_chance = 0.25
    parry_chance = 0.3
    bulletproof_chance = 0.1
    loot = [{
        "id": ITEMS.SCRAP, "amount": [2, 4], "chance": 0.6
    }, {
        "id": ITEMS.COAL, "amount": [1, 2], "chance": 0.4
    }, {
        "id": ITEMS.STONE, "amount": [1, 2], "chance": 0.3
    }]


class HawkUndead:
    type = "hostile"
    name = "hawk undead"
    icon = ":eagle:"
    health = 18
    damage = 7
    crit_chance = 0.2
    parry_chance = 0.4
    bulletproof_chance = 0.6
    loot = [{
        "id": ITEMS.STONE, "amount": [2, 5], "chance": 0.7
    }, {
        "id": ITEMS.WOOD, "amount": [2, 4], "chance": 0.5
    }, {
        "id": ITEMS.COAL, "amount": [1, 2], "chance": 0.3
    }]


class HawkWarrior:
    type = "hostile"
    name = "hawk warrior"
    icon = ":eagle:"
    health = 25
    damage = 12
    crit_chance = 0.3
    parry_chance = 0.2
    bulletproof_chance = 0.5
    loot = [{
        "id": ITEMS.IRON_ORE, "amount": [2, 4], "chance": 0.5
    }, {
        "id": ITEMS.COAL, "amount": [2, 4], "chance": 0.4
    }, {
        "id": ITEMS.STONE, "amount": [3, 6], "chance": 0.3
    }]


class Eagle:
    type = "hostile"
    name = "eagle"
    icon = ":eagle:"
    health = 30
    damage = 15
    crit_chance = 0.4
    parry_chance = 0.1
    bulletproof_chance = 0.3
    loot = [{
        "id": ITEMS.HERB, "amount": [3, 6], "chance": 0.5
    }, {
        "id": ITEMS.WOOD, "amount": [3, 6], "chance": 0.4
    }, {
        "id": ITEMS.STONE, "amount": [2, 4], "chance": 0.3
    }]


class HawkTroll:
    type = "hostile"
    name = "hawk troll"
    icon = ":eagle:"
    health = 40
    damage = 18
    crit_chance = 0.25
    parry_chance = 0.15
    bulletproof_chance = 0.7
    loot = [{
        "id": ITEMS.STONE, "amount": [5, 10], "chance": 0.8
    }, {
        "id": ITEMS.WOOD, "amount": [4, 8], "chance": 0.6
    }, {
        "id": ITEMS.COAL, "amount": [2, 4], "chance": 0.4
    }]


class Phoenix:
    type = "hostile"
    name = "phoenix"
    icon = ":fire:"
    health = 60
    damage = 25
    crit_chance = 0.5
    parry_chance = 0.05
    bulletproof_chance = 0.8
    loot = [{
        "id": ITEMS.DIAMOND, "amount": [1, 2], "chance": 0.4
    }, {
        "id": ITEMS.GOLD_BAR, "amount": [2, 5], "chance": 0.5
    }, {
        "id": ITEMS.COAL, "amount": [3, 6], "chance": 0.3
    }]


class HawkScavenger:
    type = "hostile"
    name = "hawk scavenger"
    icon = ":eagle:"
    health = 8
    damage = 4
    crit_chance = 0.15
    parry_chance = 0.35
    bulletproof_chance = 0.0
    loot = [{
        "id": ITEMS.SCRAP, "amount": [3, 6], "chance": 0.8
    }, {
        "id": ITEMS.WOOD, "amount": [1, 3], "chance": 0.5
    }, {
        "id": ITEMS.STONE, "amount": [1, 2], "chance": 0.4
    }]


class HawkMiner:
    type = "hostile"
    name = "hawk miner"
    icon = ":eagle:"
    health = 22
    damage = 9
    crit_chance = 0.18
    parry_chance = 0.2
    bulletproof_chance = 0.4
    loot = [{
        "id": ITEMS.STONE, "amount": [4, 8], "chance": 0.7
    }, {
        "id": ITEMS.COAL, "amount": [3, 6], "chance": 0.6
    }, {
        "id": ITEMS.IRON_ORE, "amount": [1, 3], "chance": 0.4
    }]


class HawkForager:
    type = "hostile"
    name = "hawk forager"
    icon = ":eagle:"
    health = 14
    damage = 6
    crit_chance = 0.22
    parry_chance = 0.28
    bulletproof_chance = 0.1
    loot = [{
        "id": ITEMS.HERB, "amount": [2, 5], "chance": 0.8
    }, {
        "id": ITEMS.WOOD, "amount": [2, 4], "chance": 0.6
    }, {
        "id": ITEMS.WHEAT, "amount": [1, 3], "chance": 0.4
    }]


class HawkTreasure:
    type = "loot"
    name = "hawk treasure"
    icon = ":eagle:"
    health = 5
    damage = 0
    crit_chance = 0.0
    parry_chance = 0.0
    bulletproof_chance = 0.0
    loot = [{
        "id": ITEMS.GOLD_BAR, "amount": [1, 3], "chance": 0.8
    }, {
        "id": ITEMS.DIAMOND, "amount": [1, 2], "chance": 0.3
    }, {
        "id": ITEMS.IRON_ORE, "amount": [2, 4], "chance": 0.5
    }]


class HawkMerchant:
    type = "loot"
    name = "hawk merchant"
    icon = ":eagle:"
    health = 8
    damage = 0
    crit_chance = 0.0
    parry_chance = 0.0
    bulletproof_chance = 0.0
    loot = [{
        "id": ITEMS.BREAD, "amount": [5, 10], "chance": 0.7
    }, {
        "id": ITEMS.HERB, "amount": [4, 8], "chance": 0.6
    }, {
        "id": ITEMS.SCRAP, "amount": [2, 5], "chance": 0.4
    }]


class HawkLumberjack:
    type = "loot"
    name = "hawk lumberjack"
    icon = ":eagle:"
    health = 6
    damage = 0
    crit_chance = 0.0
    parry_chance = 0.0
    bulletproof_chance = 0.0
    loot = [{
        "id": ITEMS.WOOD, "amount": [8, 15], "chance": 0.9
    }, {
        "id": ITEMS.STONE, "amount": [1, 3], "chance": 0.3
    }]
