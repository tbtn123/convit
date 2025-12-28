from utils.singleton import ITEM_ID

class Recipe:
    def __init__(self, cost_items=None, require_items=None, energy_cost = None, mood_cost = None, results=None):
        self.cost_items = cost_items or {}
        self.require_items = require_items or {}
        self.results = results or {}
        self.energy_cost = energy_cost or 0
        self.mood_cost = mood_cost or 0

    def describe(self):
        print("== Recipe ==")
        print("Cost Items:", self.cost_items)
        print("Required Items:", self.require_items)
        print("Results:", self.results)


gold_recipe1 = Recipe(
    cost_items={ITEM_ID.GAME_KIT: 5},
    require_items={ITEM_ID.GOLD_BAR: 5},
    results={ITEM_ID.GOLD_INGOT: 100}
)

furnace_recipe1 = Recipe(
    cost_items={
        ITEM_ID.STONE : 10
    },
    energy_cost= 10,
    results={
        ITEM_ID.FURNACE : 1
    }
)

rice_cooked_recipe1 = Recipe(
    cost_items={
        ITEM_ID.RICE_EAR : 1
    },
    require_items={
        ITEM_ID.FURNACE:1
    },
    energy_cost= 5,
    results={
        ITEM_ID.COOKED_RICE : 1
    }
)
