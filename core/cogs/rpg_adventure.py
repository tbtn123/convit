from discord.ext import commands
from discord import app_commands
import discord
import random
import asyncio
from utils.db_helpers import ensure_user, ensure_inventory
from utils.singleton import EffectID, ItemID
from utils.enemy_rpg_class import *

class RPGAdventure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.battle_sessions = {}  # Store active battles: {user_id: battle_data}
        self.safe_zone_sessions = {}  # Store safe zone sessions: {user_id: session_data}
        
    @app_commands.command(name="rpg-battle", description="Start an RPG adventure from the safe zone")
    async def rpg_battle(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user_id = interaction.user.id
        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)

        async with self.bot.db.acquire() as conn:
            is_injured = await conn.fetchval("""
                SELECT 1 FROM current_effects
                WHERE user_id = $1 AND effect_id = $2
            """, user_id, EffectID.INJURED)

            if is_injured:
                return await interaction.followup.send("ur injured! rest 5 mins before adventuring again")

        if user_id in self.battle_sessions or user_id in self.safe_zone_sessions:
            return await interaction.followup.send("ur already adventuring bro")

        async with self.bot.db.acquire() as conn:
            weapon_check = await conn.fetchrow("""
                SELECT i.item_id, i.quantity, w.needs_ammo, w.ammo_item_id
                FROM inventory i
                INNER JOIN item_weapons w ON i.item_id = w.item_id
                WHERE i.id = $1 AND i.quantity > 0
                ORDER BY i.quantity DESC
                LIMIT 1
            """, user_id)

            if weapon_check:
                weapon_id = weapon_check['item_id']
                weapon_quantity = weapon_check['quantity']
                needs_ammo = weapon_check['needs_ammo']
                ammo_item_id = weapon_check['ammo_item_id']

                ammo_count = 0
                if needs_ammo and ammo_item_id:
                    ammo_check = await conn.fetchrow("""
                        SELECT quantity FROM inventory
                        WHERE id = $1 AND item_id = $2
                    """, user_id, ammo_item_id)
                    ammo_count = ammo_check['quantity'] if ammo_check else 0

                    if ammo_count == 0:
                        return await interaction.followup.send("out of ammo dude")
            else:
                weapon_id = 0
                weapon_quantity = 1
                needs_ammo = False
                ammo_item_id = None
                ammo_count = 0

        player_health = 100
        player_max_health = 100

        session_data = {
            'player_health': player_health,
            'player_max_health': player_max_health,
            'weapon_id': weapon_id,
            'weapon_quantity': weapon_quantity,
            'ammo_count': ammo_count,
            'initial_ammo': ammo_count,
            'loot': [],
            'message': None,
            'location': 'safe_zone',
            'item_selection': None,
            'weapon_selection': None
        }

        self.safe_zone_sessions[user_id] = session_data

        message = await interaction.followup.send("Starting adventure...", ephemeral=False)
        session_data['message_obj'] = message
        await self.update_safe_zone_message(user_id)

    async def process_turn(self, user_id: int, action_number: int):
        if user_id not in self.battle_sessions:
            return

        battle_data = self.battle_sessions[user_id]
        enemy = battle_data['enemy']
        enemy_health = battle_data['enemy_health']
        player_health = battle_data['player_health']
        weapon_id = battle_data['weapon_id']
        ammo_count = battle_data['ammo_count']


        actions = await self.get_available_actions(user_id, battle_data)

        if action_number < 1 or action_number > len(actions):
            await self.update_battle_message(user_id, "thats not valid number. try again")
            return

        action = actions[action_number - 1]


        if action['type'] == 'attack':

            if action['weapon_id'] == 0:
                base_damage = random.randint(1, 3)
                player_message = "You punch with your fists!"
                crit_multiplier = 2 if random.random() < 0.1 else 1
                weapon_broken = False
            else:
                async with self.bot.db.acquire() as conn:
                    weapon_stats = await conn.fetchrow("""
                        SELECT damage_min, damage_max, crit_rate, break_chance, needs_ammo, ammo_item_id, mag_capacity
                        FROM item_weapons WHERE item_id = $1
                    """, action['weapon_id'])

                    if not weapon_stats:
                        await self.update_battle_message(user_id, "wtf invalid weapon")
                        return


                    base_damage = random.randint(weapon_stats['damage_min'], weapon_stats['damage_max'])


                    if weapon_stats['needs_ammo']:
                        if ammo_count <= 0:
                            await self.update_battle_message(user_id, "out of ammo bro!")
                            return
                        ammo_count -= 1

                    weapon_broken = False
                    break_chance = weapon_stats['break_chance']
                    if battle_data.get('double_break_chance', False):
                        break_chance *= 2
                    if random.random() < break_chance:
                        weapon_broken = True
                        player_message = "Your weapon breaks!"
                    else:
                        weapon_type = await conn.fetchval("SELECT weapon_type FROM item_weapons WHERE item_id = $1", action['weapon_id'])
                        if weapon_stats['needs_ammo']:
                            player_message = "You fire your weapon!"
                        elif weapon_type == "melee":
                            player_message = "You strike with your weapon!"
                        else:
                            player_message = "You attack with your weapon!"

                    crit_multiplier = 2 if random.random() < weapon_stats['crit_rate'] else 1

            player_damage = int(base_damage * crit_multiplier)

            if crit_multiplier > 1:
                player_message += " (Critical hit!)"

                enemy_health -= player_damage
                battle_data['weapon_broken'] = weapon_broken
            
        elif action['type'] == 'reload':
            async with self.bot.db.acquire() as conn:
                ammo_check = await conn.fetchrow("""
                    SELECT quantity FROM inventory
                    WHERE id = $1 AND item_id = $2
                """, user_id, action['ammo_item_id'])
                available_ammo = ammo_check['quantity'] if ammo_check else 0

                if available_ammo <= 0:
                    player_message = "No ammo available to reload!"
                else:
                    current_ammo = battle_data.get('ammo_count', 0)
                    mag_capacity = action['mag_capacity']
                    ammo_needed = mag_capacity - current_ammo
                    ammo_to_reload = min(ammo_needed, available_ammo)


                    battle_data['ammo_count'] = current_ammo + ammo_to_reload

                    await conn.execute("""
                        UPDATE inventory SET quantity = quantity - $3
                        WHERE id = $1 AND item_id = $2
                    """, user_id, action['ammo_item_id'], ammo_to_reload)

                    player_message = f"Reloaded {action['weapon_name']}! +{ammo_to_reload} ammo ({battle_data['ammo_count']}/{mag_capacity})"

        elif action['type'] == 'defend':
            player_message = "You brace yourself for the enemy's attack!"

            battle_data['defending'] = True
            battle_data['double_break_chance'] = True

        elif action['type'] == 'skip':
            await self.end_battle(user_id, "skipped")
            return

        elif action['type'] == 'run':
            if random.random() < 0.6:
                await self.end_battle(user_id, "escaped")
                return
            else:
                player_message = "You failed to escape!"

        battle_data['enemy_health'] = max(0, enemy_health)
        battle_data['ammo_count'] = ammo_count
        battle_data['defending'] = battle_data.get('defending', False)

        if enemy_health <= 0:
            await self.end_battle(user_id, "victory")
            return

        if action['type'] != 'run':
            enemy_message, player_health = await self.enemy_attack(user_id, player_health, battle_data)
            battle_data['player_health'] = player_health

            if player_health <= 0:
                await self.end_battle(user_id, "defeat")
                return

        await self.update_battle_message(user_id, player_message, enemy_message if action['type'] != 'run' else "")

        if 'defending' in battle_data:
            del battle_data['defending']
        if 'double_break_chance' in battle_data:
            del battle_data['double_break_chance']

    async def enemy_attack(self, user_id: int, player_health: int, battle_data: dict):
        enemy = battle_data['enemy']
        enemy_message = ""

        defending = battle_data.get('defending', False)

        if random.random() < enemy.parry_chance:
            enemy_message = f"{enemy.name} parries your attack!"
            return enemy_message, player_health

        if random.random() < enemy.bulletproof_chance and battle_data['weapon_id'] == ItemID.REVOLVER:
            enemy_message = f"{enemy.name} dodges your bullet!"
            return enemy_message, player_health

        base_damage = enemy.damage
        if defending:
            base_damage = int(base_damage * 0.5)
            enemy_message = f"{enemy.name} attacks! (Reduced damage due to defense)"
        else:
            enemy_message = f"{enemy.name} attacks!"


        crit_multiplier = 2 if random.random() < enemy.crit_chance else 1
        if crit_multiplier > 1:
            base_damage = int(base_damage * crit_multiplier)
            enemy_message += " (Critical hit!)"

        player_health -= base_damage

        return enemy_message, max(0, player_health)

    async def update_battle_message(self, user_id: int, player_message: str = "", enemy_message: str = ""):
        if user_id not in self.battle_sessions:
            return
            
        battle_data = self.battle_sessions[user_id]
        enemy = battle_data['enemy']
        enemy_health = battle_data['enemy_health']
        player_health = battle_data['player_health']
        
        
        actions = await self.get_available_actions(user_id, battle_data)
        
        
        action_list = []
        for i, action in enumerate(actions, 1):
            action_list.append(f"[{i}] : {action['description']}")
        
        action_text = "\n".join(action_list)
        
       
        message = f"""
**RPG Battle**

Enemy: {enemy.name}
Enemy Health: {enemy_health}/{enemy.health}
Your Health: {player_health}/{battle_data['player_max_health']}

{player_message}
{enemy_message}

Available Actions:
{action_text}

Enter action number:
        """.strip()
        
        if battle_data['message']:
            await battle_data['message'].edit(content=message)
        else:
            message_obj = await battle_data['message_obj'].edit(content=message)
            battle_data['message'] = message_obj

    async def get_available_actions(self, user_id: int, battle_data: dict):
        actions = []
        enemy = battle_data['enemy']


        async with self.bot.db.acquire() as conn:
            weapons = await conn.fetch("""
                SELECT i.item_id, i.quantity, it.name, w.damage_min, w.damage_max,
                       w.crit_rate, w.break_chance, w.needs_ammo, w.ammo_item_id, w.mag_capacity
                FROM inventory i
                INNER JOIN items it ON i.item_id = it.id
                INNER JOIN item_weapons w ON i.item_id = w.item_id
                WHERE i.id = $1 AND i.quantity > 0
                ORDER BY w.damage_max DESC
            """, user_id)

            if not weapons:
                actions.append({
                    'type': 'attack',
                    'weapon_id': 0,
                    'description': f"Attack {enemy.name} with your fists"
                })

            for weapon in weapons:
                weapon_name = weapon['name']
                needs_ammo = weapon['needs_ammo']
                ammo_item_id = weapon['ammo_item_id']

                ammo_info = ""
                if needs_ammo and ammo_item_id:
                    ammo_check = await conn.fetchrow("""
                        SELECT quantity FROM inventory
                        WHERE id = $1 AND item_id = $2
                    """, user_id, ammo_item_id)
                    ammo_count = ammo_check['quantity'] if ammo_check else 0
                    mag_capacity = weapon['mag_capacity'] or 1
                    ammo_info = f" ({ammo_count}/{mag_capacity} remaining)"

                actions.append({
                    'type': 'attack',
                    'weapon_id': weapon['item_id'],
                    'description': f"Attack {enemy.name} with {weapon_name}{ammo_info}"
                })


            async with self.bot.db.acquire() as conn:
                for weapon in weapons:
                    if weapon['needs_ammo'] and weapon['ammo_item_id']:

                        ammo_check = await conn.fetchrow("""
                            SELECT quantity FROM inventory
                            WHERE id = $1 AND item_id = $2
                        """, user_id, weapon['ammo_item_id'])
                        available_ammo = ammo_check['quantity'] if ammo_check else 0

                        if available_ammo > 0:
                            mag_capacity = weapon['mag_capacity'] or 1
                            current_ammo = battle_data.get('ammo_count', 0)
                            if current_ammo < mag_capacity:
                                actions.append({
                                    'type': 'reload',
                                    'weapon_id': weapon['item_id'],
                                    'weapon_name': weapon['name'],
                                    'ammo_item_id': weapon['ammo_item_id'],
                                    'mag_capacity': mag_capacity,
                                    'available_ammo': available_ammo,
                                    'description': f'Reload {weapon["name"]} ({available_ammo} ammo available)'
                                })

            if weapons:
                first_weapon = weapons[0]['name']
                actions.append({
                    'type': 'defend',
                    'description': f'Defend with {first_weapon} (reduces damage taken)'
                })

            if enemy.type == "loot":
                actions.append({
                    'type': 'skip',
                    'description': f'Skip battle and take loot from {enemy.name}'
                })

            actions.append({
                'type': 'run',
                'description': 'Run away'
            })

        return actions

    async def end_battle(self, user_id: int, result: str, weapon_id: int = None):
        if user_id not in self.battle_sessions:
            return

        battle_data = self.battle_sessions.pop(user_id)
        enemy = battle_data['enemy']

        loot_messages = []
        status_messages = []
        async with self.bot.db.acquire() as conn:
            if result in ["victory", "skipped"]:
                for loot_item in enemy.loot:
                    if random.random() < loot_item['chance']:
                        amount = random.randint(loot_item['amount'][0], loot_item['amount'][1])
                        item_row = await conn.fetchrow("SELECT name FROM items WHERE id = $1", loot_item['id'])
                        item_name = item_row['name'] if item_row else f"Item {loot_item['id']}"

                        battle_data['loot'].append({'id': loot_item['id'], 'amount': amount})

                        loot_messages.append(f"Got {amount}x {item_name}")

            if battle_data.get('weapon_broken', False):
                await conn.execute("""
                    UPDATE inventory SET quantity = quantity - 1
                    WHERE id = $1 AND item_id = $2 AND quantity > 0
                """, user_id, battle_data['weapon_id'])
                status_messages.append("Your weapon broke!")

            weapon_stats = await conn.fetchrow("""
                SELECT needs_ammo, ammo_item_id FROM item_weapons WHERE item_id = $1
            """, battle_data['weapon_id'])

            if weapon_stats and weapon_stats['needs_ammo'] and weapon_stats['ammo_item_id']:
                initial_ammo = battle_data.get('initial_ammo', battle_data['ammo_count'])
                ammo_used = initial_ammo - battle_data['ammo_count']
                if ammo_used > 0:
                    await conn.execute("""
                        UPDATE inventory SET quantity = quantity - $3
                        WHERE id = $1 AND item_id = $2
                    """, user_id, weapon_stats['ammo_item_id'], ammo_used)

            if result == "defeat":
                await conn.execute("""
                    INSERT INTO current_effects (user_id, effect_id, duration, ticks)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, effect_id) DO UPDATE
                    SET duration = $3, ticks = $4
                """, user_id, EffectID.INJURED, 300, 300)
                status_messages.append("You're injured! Rest for 5 minutes.")

        # Create result message
        if result == "victory":
            message = f"Victory! Defeated {enemy.name}!"
        elif result == "defeat":
            message = f"Defeat! You were defeated by {enemy.name}!"
        elif result == "skipped":
            message = f"Skipped! You peacefully took loot from {enemy.name}!"
        else:  # escape
            message = f"Escape! You escaped from {enemy.name}!"

        if loot_messages:
            message += "\n\nLoot:\n" + "\n".join(loot_messages)
        if status_messages:
            message += "\n\n" + "\n".join(status_messages)

        # After battle, return to safe zone or force home if defeated
        if result == "defeat":
            # Force player home on defeat
            await self.force_return_home_on_defeat(user_id, message, battle_data)
        else:
            await self.return_to_safe_zone_after_battle(user_id, message, battle_data)

    async def return_to_safe_zone_after_battle(self, user_id: int, battle_result_message: str, battle_data: dict):
        session_data = {
            'player_health': battle_data['player_health'],
            'player_max_health': battle_data['player_max_health'],
            'weapon_id': battle_data['weapon_id'],
            'weapon_quantity': battle_data['weapon_quantity'],
            'ammo_count': battle_data['ammo_count'],
            'initial_ammo': battle_data['initial_ammo'],
            'loot': battle_data['loot'],
            'message': None,
            'message_obj': battle_data['message_obj'] if battle_data.get('message_obj') else battle_data.get('message')
        }

        self.safe_zone_sessions[user_id] = session_data

        result_message = battle_result_message + "\n\n*Returning to safe zone...*"

        if session_data['message_obj']:
            await session_data['message_obj'].edit(content=result_message)

        await asyncio.sleep(2)
        await self.update_safe_zone_message(user_id)

    async def force_return_home_on_defeat(self, user_id: int, defeat_message: str, battle_data: dict):
        self.safe_zone_sessions.pop(user_id, None)
        self.battle_sessions.pop(user_id, None)

        final_message = defeat_message + "\n\n*You have been defeated and returned home...*"

        if battle_data['message_obj']:
            await battle_data['message_obj'].edit(content=final_message)

    async def safe_zone_use_item(self, user_id: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]

        async with self.bot.db.acquire() as conn:
            usable_items = await conn.fetch("""
                SELECT i.item_id, i.quantity, it.name, eff.name as effect_name, eff.value
                FROM inventory i
                INNER JOIN items it ON i.item_id = it.id
                INNER JOIN item_effects eff ON it.id = eff.item_id
                WHERE i.id = $1 AND (eff.name LIKE 'rpg_%' OR eff.name = 'add_energy') AND i.quantity > 0
                ORDER BY it.name
            """, user_id)

            if not usable_items:
                await self.update_safe_zone_message(user_id, "no usable items in ur inv bro")
                return

            item_list = []
            for i, item in enumerate(usable_items, 1):
                item_name = item['name']
                quantity = item['quantity']
                effect_name = item['effect_name']
                effect_value = item['value']

                if effect_name == 'add_energy':
                    effect_desc = f"Restores {effect_value} energy"
                elif effect_name=="rpg_heal":
                    effect_desc = f"Heals {effect_value} health"
                else:
                    effect_desc = f"{effect_value}"

                item_list.append(f"[{i}] {item_name} x{quantity} - {effect_desc}")

            item_text = "\n".join(item_list)

            session_data['item_selection'] = usable_items

            selection_message = f"""
**Select Item to Use**

Available Items:
{item_text}

[0] : Cancel

Enter item number:
            """.strip()

            if session_data['message']:
                await session_data['message'].edit(content=selection_message)
            else:
                message_obj = await session_data['message_obj'].edit(content=selection_message)
                session_data['message'] = message_obj

    async def safe_zone_use_selected_item(self, user_id: int, item_index: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]

        if 'item_selection' not in session_data or not session_data['item_selection']:
            await self.update_safe_zone_message(user_id, "No item selection active!")
            return

        usable_items = session_data['item_selection']

        if item_index < 1 or item_index > len(usable_items):
            del session_data['item_selection']
            await self.update_safe_zone_message(user_id, "Invalid item number!")
            return

        selected_item = usable_items[item_index - 1]
        item_id = selected_item['item_id']
        item_name = selected_item['name']
        effect_name = selected_item['effect_name']
        effect_value = selected_item['value']

        del session_data['item_selection']

        async with self.bot.db.acquire() as conn:
            if effect_name == 'add_energy':
                energy_amount = int(effect_value)
                await conn.execute("""
                    UPDATE users SET energy = LEAST(energy + $2, energy_max)
                    WHERE id = $1
                """, user_id, energy_amount)
                message = f"Used {item_name}! Restored {energy_amount} energy."
            elif effect_value.startswith('heal:'):
                heal_amount = int(effect_value.split(':')[1])
                session_data['player_health'] = min(
                    session_data['player_health'] + heal_amount,
                    session_data['player_max_health']
                )
                message = f"Used {item_name}! Healed {heal_amount} health."
            else:
                message = f"Used {item_name}! (Effect: {effect_value})"

            await conn.execute("""
                UPDATE inventory SET quantity = quantity - 1
                WHERE id = $1 AND item_id = $2
            """, user_id, item_id)

        await self.update_safe_zone_message(user_id, message)

    async def safe_zone_show_loot(self, user_id: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]
        loot = session_data['loot']

        if not loot:
            message = "You haven't collected any loot yet."
        else:
            loot_items = []
            for loot_item in loot:
                async with self.bot.db.acquire() as conn:
                    item_row = await conn.fetchrow("SELECT name FROM items WHERE id = $1", loot_item['id'])
                    item_name = item_row['name'] if item_row else f"Item {loot_item['id']}"
                loot_items.append(f"{loot_item['amount']}x {item_name}")

            message = "Your accumulated loot:\n" + "\n".join(loot_items)

        await self.update_safe_zone_message(user_id, message)

    async def safe_zone_change_weapon(self, user_id: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]

        available_weapons = [{'item_id': 0, 'name': 'Fists', 'quantity': 1, 'needs_ammo': False, 'ammo_item_id': None}]

        async with self.bot.db.acquire() as conn:
            db_weapons = await conn.fetch("""
                SELECT i.item_id, i.quantity, it.name, w.needs_ammo, w.ammo_item_id
                FROM inventory i
                INNER JOIN items it ON i.item_id = it.id
                INNER JOIN item_weapons w ON i.item_id = w.item_id
                WHERE i.id = $1 AND i.quantity > 0
                ORDER BY w.damage_max DESC
            """, user_id)

            available_weapons.extend(db_weapons)

            if len(available_weapons) <= 1:
                await self.update_safe_zone_message(user_id, "you only have 1 weapon bro. no need to change")
                return

            weapon_list = []
            for i, weapon in enumerate(available_weapons, 1):
                weapon_name = weapon['name']
                quantity = weapon['quantity']
                needs_ammo = weapon['needs_ammo']
                ammo_item_id = weapon['ammo_item_id']

                ammo_info = ""
                if needs_ammo and ammo_item_id:
                    ammo_check = await conn.fetchrow("""
                        SELECT quantity FROM inventory
                        WHERE id = $1 AND item_id = $2
                    """, user_id, ammo_item_id)
                    ammo_count = ammo_check['quantity'] if ammo_check else 0
                    ammo_info = f" (ammo: {ammo_count})"

                current_marker = " [CURRENT]" if weapon['item_id'] == session_data['weapon_id'] else ""
                weapon_list.append(f"[{i}] {weapon_name} x{quantity}{ammo_info}{current_marker}")

            weapon_text = "\n".join(weapon_list)

            session_data['weapon_selection'] = available_weapons

            selection_message = f"""
**Select Weapon to Equip**

Available Weapons:
{weapon_text}

[0] : Cancel

Enter weapon number:
            """.strip()

            if session_data['message']:
                await session_data['message'].edit(content=selection_message)
            else:
                message_obj = await session_data['message_obj'].edit(content=selection_message)
                session_data['message'] = message_obj

    async def safe_zone_change_selected_weapon(self, user_id: int, weapon_index: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]

        if 'weapon_selection' not in session_data or not session_data['weapon_selection']:
            await self.update_safe_zone_message(user_id, "No weapon selection active!")
            return

        available_weapons = session_data['weapon_selection']

        if weapon_index < 1 or weapon_index > len(available_weapons):
            del session_data['weapon_selection']
            await self.update_safe_zone_message(user_id, "Invalid weapon number!")
            return

        selected_weapon = available_weapons[weapon_index - 1]
        weapon_id = selected_weapon['item_id']
        weapon_name = selected_weapon['name']
        weapon_quantity = selected_weapon['quantity']
        needs_ammo = selected_weapon['needs_ammo']
        ammo_item_id = selected_weapon['ammo_item_id']

        del session_data['weapon_selection']

        session_data['weapon_id'] = weapon_id
        session_data['weapon_quantity'] = weapon_quantity

        if needs_ammo and ammo_item_id:
            async with self.bot.db.acquire() as conn:
                ammo_check = await conn.fetchrow("""
                    SELECT quantity FROM inventory
                    WHERE id = $1 AND item_id = $2
                """, user_id, ammo_item_id)
                ammo_count = ammo_check['quantity'] if ammo_check else 0
                session_data['ammo_count'] = ammo_count
                session_data['initial_ammo'] = ammo_count

        message = f"Equipped {weapon_name}! Ready for battle."
        await self.update_safe_zone_message(user_id, message)

    async def safe_zone_return_home(self, user_id: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions.pop(user_id)

        if session_data['loot']:
            async with self.bot.db.acquire() as conn:
                for loot_item in session_data['loot']:
                    await conn.execute("""
                        INSERT INTO inventory (id, item_id, quantity)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (id, item_id) DO UPDATE
                        SET quantity = inventory.quantity + $3
                    """, user_id, loot_item['id'], loot_item['amount'])

        message = f"""
**Returned Home**

You safely returned home with your loot!
Final Health: {session_data['player_health']}/{session_data['player_max_health']}
        """.strip()

        if session_data['message']:
            await session_data['message'].edit(content=message)
        else:
            await session_data['message_obj'].edit(content=message)

    async def safe_zone_move_forward(self, user_id: int):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]

        async with self.bot.db.acquire() as conn:
            user_data = await conn.fetchrow("SELECT energy FROM users WHERE id = $1", user_id)
            if user_data and user_data['energy'] > 0:
                await conn.execute("UPDATE users SET energy = energy - 1 WHERE id = $1", user_id)
            else:
                await self.update_safe_zone_message(user_id, "You're out of energy! Rest before continuing.")
                return

        if random.random() < 0.5:
            await self.start_battle_from_safe_zone(user_id)
        else:
            await self.update_safe_zone_message(user_id, "You continue exploring... still in safe zone.")

    async def start_battle_from_safe_zone(self, user_id: int):
        session_data = self.safe_zone_sessions.pop(user_id)

        enemy_classes = [HawkThief, Hawk, HawkGoblin, HawkUndead, HawkWarrior, Eagle, HawkTroll, Phoenix, HawkScavenger, HawkMiner, HawkForager, HawkTreasure, HawkMerchant, HawkLumberjack]
        enemy_class = random.choice(enemy_classes)
        enemy = enemy_class()

        battle_data = {
            'enemy': enemy,
            'enemy_health': enemy.health,
            'player_health': session_data['player_health'],
            'player_max_health': session_data['player_max_health'],
            'weapon_id': session_data['weapon_id'],
            'weapon_quantity': session_data['weapon_quantity'],
            'ammo_count': session_data['ammo_count'],
            'initial_ammo': session_data['initial_ammo'],
            'loot': session_data['loot'],
            'turn': 'player',
            'message': None,
            'message_obj': None
        }

        self.battle_sessions[user_id] = battle_data

        message = f"""
**RPG Battle**

Enemy: {enemy.name}
Enemy Health: {enemy.health}/{enemy.health}
Your Health: {session_data['player_health']}/{session_data['player_max_health']}

Enemy encountered! Choose your action:
        """.strip()

        message_obj = await session_data['message_obj'].edit(content=message)
        battle_data['message_obj'] = message_obj

        await self.update_battle_message(user_id)

    async def update_safe_zone_message(self, user_id: int, message: str = ""):
        if user_id not in self.safe_zone_sessions:
            return

        session_data = self.safe_zone_sessions[user_id]

        async with self.bot.db.acquire() as conn:
            user_data = await conn.fetchrow("SELECT energy, energy_max FROM users WHERE id = $1", user_id)
            current_energy = user_data['energy'] if user_data else 0
            max_energy = user_data['energy_max'] if user_data else 100

        actions = [
            "[1] : Use item",
            "[2] : Show loot",
            "[3] : Return home",
            "[4] : Change weapon",
            "[5] : Continue"
        ]

        action_text = "\n".join(actions)

        safe_zone_message = f"""
**Safe Zone**

You are safe here. Choose your next action:

Your Health: {session_data['player_health']}/{session_data['player_max_health']}
Your Energy: {current_energy}/{max_energy}

{message}

Available Actions:
{action_text}

Enter action number:
        """.strip()

        if session_data['message']:
            await session_data['message'].edit(content=safe_zone_message)
        else:
            message_obj = await session_data['message_obj'].edit(content=safe_zone_message)
            session_data['message'] = message_obj

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        user_id = message.author.id

        if user_id not in self.safe_zone_sessions and user_id not in self.battle_sessions:
            return

        try:
            action_number = int(message.content.strip())
        except ValueError:
            return

        try:
            await message.delete()
        except discord.Forbidden:
            pass
        except discord.NotFound:
            pass

        if user_id in self.safe_zone_sessions:
            session_data = self.safe_zone_sessions[user_id]

            if 'weapon_selection' in session_data and session_data['weapon_selection'] is not None:
                if action_number == 0:
                    del session_data['weapon_selection']
                    await self.update_safe_zone_message(user_id, "Weapon selection cancelled.")
                else:
                    await self.safe_zone_change_selected_weapon(user_id, action_number)
                return

            if 'item_selection' in session_data and session_data['item_selection'] is not None:
                if action_number == 0:
                    del session_data['item_selection']
                    await self.update_safe_zone_message(user_id, "Item selection cancelled.")
                else:
                    await self.safe_zone_use_selected_item(user_id, action_number)
                return

            if action_number == 1:
                await self.safe_zone_use_item(user_id)
            elif action_number == 2:
                await self.safe_zone_show_loot(user_id)
            elif action_number == 3:
                await self.safe_zone_return_home(user_id)
            elif action_number == 4:
                await self.safe_zone_change_weapon(user_id)
            elif action_number == 5:
                await self.safe_zone_move_forward(user_id)
            else:
                await self.update_safe_zone_message(user_id, "Invalid action number!")

        elif user_id in self.battle_sessions:
            await self.process_turn(user_id, action_number)

# --- SETUP ---
async def setup(bot):
    await bot.add_cog(RPGAdventure(bot))
