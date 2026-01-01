import discord
from discord.ext import commands
import random
import traceback
from datetime import datetime, timedelta

from utils.db_helpers import *
from utils.singleton import ItemID

# Mining Results View with continue button
class MiningResultsView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="Continue Mining", style=discord.ButtonStyle.primary)
    async def continue_mining(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mining interface.", ephemeral=True)

        await interaction.response.defer()
        await self.cog.show_mining_panel(interaction, self.user_id, edit=True)


class MiningView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
    
    @discord.ui.button(label="Go Up", style=discord.ButtonStyle.secondary)
    async def go_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mining interface.", ephemeral=True)
        
        await interaction.response.defer()
        
        current_depth = self.cog.bot.mining_depth_cache.get(self.user_id, 0)
        if current_depth <= 0:
            return await interaction.followup.send("Already at surface level.", ephemeral=True)
        

        new_depth = max(0, current_depth - 5)
        self.cog.bot.mining_depth_cache[self.user_id] = new_depth
        
        await self.cog.show_mining_panel(interaction, self.user_id, edit=True)
    
    @discord.ui.button(label="Mine Here", style=discord.ButtonStyle.primary)
    async def mine_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mining interface.", ephemeral=True)

        await interaction.response.defer()

       
        status, data = await self.cog.perform_mining(interaction, self.user_id)

        if status == "error":
            # error message a followup and don't update panel
            embed = discord.Embed(
                title=data['title'],
                description=data['description'],
                color=data['color']
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # results in the panel
            await self.cog.show_mining_panel(interaction, self.user_id, edit=True, mining_results=data)
    
    @discord.ui.button(label="Go Down", style=discord.ButtonStyle.secondary)
    async def go_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mining interface.", ephemeral=True)
        
        await interaction.response.defer()
        
        current_depth = self.cog.bot.mining_depth_cache.get(self.user_id, 0)
        
        # down 5 meters
        new_depth = current_depth + 5
        self.cog.bot.mining_depth_cache[self.user_id] = new_depth
        
        await self.cog.show_mining_panel(interaction, self.user_id, edit=True)

# Mining Zone Constants
ZONE_SURFACE_MINE = (0, 10)
ZONE_IRON_QUARRY = (10, 30)
ZONE_GOLD_DEPTHS = (30, 50)
ZONE_DIAMOND_ABYSS = (50, float('inf'))

class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize mining depth tracking (cache-based)
        if not hasattr(bot, 'mining_depth_cache'):
            bot.mining_depth_cache = {}
        if not hasattr(bot, 'mining_events_cache'):
            bot.mining_events_cache = {}

    def get_zone_info(self, depth):
        """Determine mining zone based on depth"""
        if depth <= ZONE_SURFACE_MINE[1]:
            return "Surface Mine", ZONE_SURFACE_MINE
        elif depth <= ZONE_IRON_QUARRY[1]:
            return "Iron Quarry", ZONE_IRON_QUARRY
        elif depth <= ZONE_GOLD_DEPTHS[1]:
            return "Gold Depths", ZONE_GOLD_DEPTHS
        else:
            return "Diamond Abyss", ZONE_DIAMOND_ABYSS

    def get_zone_loot_table(self, depth):
        """Get loot probabilities based on zone"""
        zone_name, _ = self.get_zone_info(depth)
        
        if zone_name == "Surface Mine":
            return {
                ItemID.STONE: 0.60,      # Stone (common)
                ItemID.COAL: 0.25,       # Coal (uncommon)
            }
        elif zone_name == "Iron Quarry":
            return {
                ItemID.IRON_ORE: 0.50,   # Iron Ore (common)
                ItemID.STONE: 0.35,      # Stone (common)
                ItemID.COAL: 0.15,       # Coal (less common)
            }
        elif zone_name == "Gold Depths":
            return {
                ItemID.GOLD_ORE: 0.45,   # Gold Ore (common)
                ItemID.IRON_ORE: 0.30,   # Iron Ore (common)
                ItemID.DIAMOND_ORE: 0.05, # Diamond Ore (5%)
                ItemID.COAL: 0.20,       # Coal
            }
        else:  # Diamond Abyss
            return {
                ItemID.DIAMOND_ORE: 0.10, # Diamond Ore (10%)
                ItemID.GOLD_ORE: 0.40,    # Gold Ore
                ItemID.IRON_ORE: 0.30,    # Iron Ore
                ItemID.COAL: 0.20,        # Coal
            }

    def get_event_probabilities(self, depth):
        """Get event probabilities based on zone"""
        zone_name, _ = self.get_zone_info(depth)
        
        base_events = {
            'cave_in': 0.05,
            'rich_vein': 0.10,
            'gas_pocket': 0.03,
            'underground_lake': 0.02,
        }
        
        # Treasure room only at depth 50+
        if depth >= 50:
            base_events['treasure_room'] = 0.01
        
        return base_events

    def check_event_cooldown(self, user_id, event_type):
        """Check if user is on cooldown for specific event"""
        cache_key = f"{user_id}_{event_type}"
        if cache_key in self.bot.mining_events_cache:
            last_event = self.bot.mining_events_cache[cache_key]
            # 5 minute cooldown per event type
            if datetime.now() - last_event < timedelta(minutes=5):
                return False
        return True

    def set_event_cooldown(self, user_id, event_type):
        """Set cooldown for specific event"""
        cache_key = f"{user_id}_{event_type}"
        self.bot.mining_events_cache[cache_key] = datetime.now()

    async def process_mining_event(self, conn, user_id, depth, user):
        """Process random mining events"""
        event_probs = self.get_event_probabilities(depth)
        event_result = None
        
        for event_type, probability in event_probs.items():
            if random.random() < probability:
                if self.check_event_cooldown(user_id, event_type):
                    event_result = await self.trigger_event(conn, user_id, event_type, depth, user)
                    self.set_event_cooldown(user_id, event_type)
                    break
        
        return event_result

    async def trigger_event(self, conn, user_id, event_type, depth, user):
        """Trigger specific mining event"""
        if event_type == 'cave_in':
            # Reset depth to 0, -20 energy
            await conn.execute(
                "UPDATE users SET energy = GREATEST(energy - 20, 0) WHERE id = $1",
                user_id
            )
            self.bot.mining_depth_cache[user_id] = 0
            return {
                'type': 'cave_in',
                'title': 'Alert: Cave-In Detected',
                'description': 'Structural collapse detected. Emergency protocols engaged.',
                'effects': 'Depth reset to surface\nEnergy: -20',
                'color': discord.Color.red()
            }
        
        elif event_type == 'rich_vein':
            # 3x ore bonus (handled by caller)
            return {
                'type': 'rich_vein',
                'title': 'Discovery: Rich Vein Located',
                'description': 'High-density ore deposit identified. Extraction efficiency increased.',
                'effects': 'Ore yield: 3x multiplier',
                'color': discord.Color.gold()
            }
        
        elif event_type == 'gas_pocket':
            # -30 energy, -10 mood
            await conn.execute(
                "UPDATE users SET energy = GREATEST(energy - 30, 0), mood = GREATEST(mood - 10, 0) WHERE id = $1",
                user_id
            )
            return {
                'type': 'gas_pocket',
                'title': 'Warning: Gas Pocket Breach',
                'description': 'Toxic gas exposure detected. Immediate evacuation recommended.',
                'effects': 'Energy: -30\nMood: -10',
                'color': discord.Color.orange()
            }
        
        elif event_type == 'underground_lake':
            # +20 energy, +5 mood
            new_energy = min(user['energy'] + 20, user['energy_max'])
            new_mood = min(user['mood'] + 5, user['mood_max'])
            await conn.execute(
                "UPDATE users SET energy = $1, mood = $2 WHERE id = $3",
                new_energy, new_mood, user_id
            )
            return {
                'type': 'underground_lake',
                'title': 'Discovery: Underground Lake',
                'description': 'Fresh water source located. Restorative properties confirmed.',
                'effects': 'Energy: +20\nMood: +5',
                'color': discord.Color.blue()
            }
        
        elif event_type == 'treasure_room':
            # 10x Diamond Ore, 5x Gold Bar
            await conn.execute("""
                INSERT INTO inventory (id, item_id, quantity)
                VALUES ($1, $2, 10)
                ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + 10
            """, user_id, ItemID.DIAMOND_ORE)
            
            await conn.execute("""
                INSERT INTO inventory (id, item_id, quantity)
                VALUES ($1, $2, 5)
                ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + 5
            """, user_id, ItemID.GOLD_BAR)
            
            return {
                'type': 'treasure_room',
                'title': 'Critical Discovery: Ancient Treasure Chamber',
                'description': 'Rare geological formation detected. High-value resources secured.',
                'effects': 'Acquired: 10x Diamond Ore, 5x Gold Bar',
                'color': discord.Color.purple()
            }
        
        return None

    async def show_mining_panel(self, ctx_or_interaction, user_id, edit=False, mining_results=None):
        """Show the mining interface panel"""
        async with self.bot.db.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

            # Get or initialize depth
            if user_id not in self.bot.mining_depth_cache:
                self.bot.mining_depth_cache[user_id] = 0

            current_depth = self.bot.mining_depth_cache[user_id]
            zone_name, _ = self.get_zone_info(current_depth)

            # Check pickaxe
            pickaxe = await conn.fetchrow("""
                SELECT i.* FROM inventory i
                INNER JOIN item_effects ie ON i.item_id = ie.item_id
                WHERE i.id = $1 AND ie.name = 'mining_tool' AND i.quantity > 0
                LIMIT 1
            """, user_id)
            has_pickaxe = pickaxe is not None

            # If we have mining results, show them instead of the normal interface
            if mining_results:
                embed = discord.Embed(
                    title="Mining operation complete",
                    description=f"Status {'Event triggered' if mining_results.get('event_result') else 'Success'}.",
                    color=mining_results.get('event_result', {}).get('color', discord.Color.blue()) if mining_results.get('event_result') else discord.Color.blue()
                )

                # Add event info if occurred
                if mining_results.get('event_result'):
                    event_result = mining_results['event_result']
                    embed.add_field(
                        name=event_result['title'],
                        value=f"{event_result['description']}\n{event_result['effects']}",
                        inline=False
                    )

                # Add resources acquired
                if mining_results.get('loot_items'):
                    loot_text = ""
                    for item_id, quantity in mining_results['loot_items']:
                        item_row = await conn.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
                        loot_text += f"{item_row['icon']} {item_row['name']} x{quantity}\n"
                    embed.add_field(
                        name="Resources Acquired",
                        value=loot_text.strip(),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Resources Acquired",
                        value="None detected",
                        inline=False
                    )

                # Add depth and zone info
                embed.add_field(
                    name="Current Depth",
                    value=f"{current_depth}m\nZone: {zone_name}",
                    inline=True
                )

                # Add energy status
                embed.add_field(
                    name="Energy",
                    value=f"{user['energy']}/{user['energy_max']}",
                    inline=True
                )

                embed.set_footer(text="Click 'Continue Mining' to return to the mining interface.")
                view = MiningResultsView(self, user_id)
            else:
                # Normal mining interface
                embed = discord.Embed(
                    title="Mining Interface",
                    description=f"Current location depth {current_depth} meters.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Zone", value=zone_name, inline=True)
                embed.add_field(name="Energy", value=f"{user['energy']}/{user['energy_max']}", inline=True)
                embed.add_field(name="Equipment", value="Pickaxe equipped" if has_pickaxe else "⚠️ Pickaxe required", inline=True)

                # Show zone loot info
                loot_table = self.get_zone_loot_table(current_depth)
                loot_info = []
                for item_id, prob in loot_table.items():
                    item_row = await conn.fetchrow("SELECT name, icon FROM items WHERE id = $1", item_id)
                    if item_row:
                        loot_info.append(f"{item_row['icon']} {item_row['name']} ({int(prob*100)}%)")

                embed.add_field(name="Available Resources", value="\n".join(loot_info) if loot_info else "None", inline=False)
                embed.set_footer(text="Use buttons to navigate or mine. Mining costs 10 energy.")

                view = MiningView(self, user_id)
            
            if edit:
                # For button interactions, edit the original response
                if hasattr(ctx_or_interaction, 'edit_original_response'):
                    await ctx_or_interaction.edit_original_response(embed=embed, view=view)
                else:
                    # For regular interactions from buttons
                    await ctx_or_interaction.edit_original_response(embed=embed, view=view)
            else:
                await ctx_or_interaction.send(embed=embed, view=view)
    
    @commands.hybrid_command(name="mine", description="Access mining interface")
    async def scrap(self, ctx: commands.Context):
        await ctx.defer()
        try:
            await ensure_user(self.bot.db, ctx.author.id)
            await ensure_inventory(self.bot.db, ctx.author.id)
            
            await self.show_mining_panel(ctx, ctx.author.id)
            
        except Exception as e:
            embed = discord.Embed(
                title="Error. System malfunction",
                description="An unexpected error occurred. Retry operation.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            print(f"[ERROR] mine {ctx.author.id}: {e}")
            traceback.print_exc()
    
    async def perform_mining(self, interaction, user_id):
        """Perform the actual mining operation"""
        base_cost = 10
        try:
            async with self.bot.db.acquire() as conn:
                user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                if not user or user["energy"] < base_cost:
                    return "error", {
                        'type': 'insufficient_energy',
                        'title': 'Warning. Energy insufficient',
                        'description': f"Energy level at {user['energy'] if user else 0} out of {user['energy_max'] if user else 100}. Minimum {base_cost} required. Rest or consume energy items.",
                        'color': discord.Color.red()
                    }

                # check pickaxe
                pickaxe = await conn.fetchrow("""
                    SELECT i.* FROM inventory i
                    INNER JOIN item_effects ie ON i.item_id = ie.item_id
                    WHERE i.id = $1 AND ie.name = 'mining_tool' AND i.quantity > 0
                    LIMIT 1
                """, user_id)
                if not pickaxe:
                    return "error", {
                        'type': 'no_pickaxe',
                        'title': 'Error. Equipment missing',
                        'description': "Pickaxe required. Not found in inventory. Action denied.",
                        'color': discord.Color.red()
                    }

                # Get current depth
                current_depth = self.bot.mining_depth_cache.get(user_id, 0)

                # Check for mining event BEFORE mining
                event_result = await self.process_mining_event(conn, user_id, current_depth, user)

                # If cave-in occurred, depth is already reset
                if event_result and event_result['type'] == 'cave_in':
                    current_depth = 0

                # Deduct energy
                await conn.execute(
                    "UPDATE users SET energy = energy - $1 WHERE id = $2",
                    base_cost, user_id
                )

                # Get zone-based loot table
                loot_table = self.get_zone_loot_table(current_depth)

                # Determine loot
                loot_items = []
                ore_multiplier = 3 if (event_result and event_result['type'] == 'rich_vein') else 1

                for item_id, probability in loot_table.items():
                    if random.random() <= probability:
                        quantity = ore_multiplier
                        loot_items.append((item_id, quantity))

                        # Add to inventory
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $3
                        """, user_id, item_id, quantity)

                # Increase depth by 1-3 meters (unless cave-in)
                if not (event_result and event_result['type'] == 'cave_in'):
                    depth_gain = random.randint(1, 3)
                    current_depth += depth_gain
                    self.bot.mining_depth_cache[user_id] = current_depth

                # Return mining results data
                return "success", {
                    'event_result': event_result,
                    'loot_items': loot_items,
                    'current_depth': current_depth
                }

        except Exception as e:
            print(f"[ERROR] perform_mining {user_id}: {e}")
            traceback.print_exc()
            return "error", {
                'type': 'system_error',
                'title': 'Error. System malfunction',
                'description': "An unexpected error occurred. Retry operation.",
                'color': discord.Color.red()
            }


async def setup(bot):
    await bot.add_cog(Mining(bot))
