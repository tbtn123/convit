BASE_TICK = 30


class EffectID:
    """User effect IDs"""
    REST = 1
    ROB_PROTECT = 2
    INJURED = 3
    TAX_PERK = 4
    REPLENISHED = 5
    EXHAUSTED = 6
    GAMBLING_ADDICT = 7
    MOTIVATED = 8
    DEMORALIZED = 9
    OVERWORKED = 10


class ItemID:
    """Item IDs"""
    BREAD = 1
    LOTTERY_TICKET = 2
    SCRAP = 3
    WALLET_LOCK = 4
    GOLD_BAR = 5
    PICKAXE = 6
    GOLD_ORE = 7
    GAME_KIT = 8
    REVOLVER = 9
    HERB = 10
    MEDKIT = 11
    BULLET = 12
    RICE_SEED = 13
    RICE_EAR = 14
    COAL = 15
    COOKED_RICE = 16
    FURNACE = 17
    STONE = 18
    WOOD = 19
    WHEAT = 20
    IRON_ORE = 21
    IRON_INGOT = 22
    STICK = 23
    ROPE = 24
    DUMBBELL = 25
    TOOLBELT = 26
    IRON_PICKAXE = 27
    DIAMOND_ORE = 28
    DIAMOND = 29
    DIAMOND_PICKAXE = 30
    WOODEN_PICKAXE = 31
    STONE_PICKAXE = 32
    WHEAT_SEED = 33
    CAKE = 34
    SWORD = 35


# Legacy support - will be removed in future versions
tick = BASE_TICK
EFFECT_MAP = {
    "rob_protect": EffectID.ROB_PROTECT,
    "rest": EffectID.REST
}
ITEM_ID = ItemID
