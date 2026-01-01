import discord
from discord.ext import commands
from datetime import datetime
import random
import traceback
from typing import Optional

from utils.db_helpers import *
from utils.economy import format_number
from utils.singleton import BASE_TICK
from .items import get_inventory_total, get_inventory_penalty, get_inventory_warning
from utils.parser import parse_amount, AmountParseError  # Added for flexible amount parsing

async def calculate_transfer_tax(db, guild_id: int, amount: int):
    """Calculate transfer tax for a given amount in a guild.

    Returns:
        tuple: (tax_amount, remaining_amount)
    """
    try:
        async with db.acquire() as conn:
            tax_rate = await conn.fetchval(
                "SELECT transfer_tax_rate FROM guild_config WHERE guild_id = $1",
                guild_id
            )

            if tax_rate is None:
                tax_rate = 0.0

            tax_amount = int(amount * tax_rate)
            remaining_amount = amount - tax_amount

            return tax_amount, remaining_amount
    except Exception:
        # If there's any error, assume no tax
        return 0, amount

BASE_COMM = 0.05
MULTIPLIERS   = [1,   2,   3,   5,    10,  0,  -1,  -2]
MULTI_WEIGHTS = [0.25, 0.15, 0.03, 0.01, 0.001, 0.25, 0.20, 0.109]




def generate_grid():
    return [
        [random.choices(MULTIPLIERS, weights=MULTI_WEIGHTS, k=1)[0] for _ in range(3)]
        for _ in range(3)
    ]

class ScratchView(discord.ui.View):
    def __init__(self, user_id: int, grid: list[list[int]], bet: int, pool, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.grid = grid
        self.revealed = [[False] * 3 for _ in range(3)]
        self.bet = bet
        self.pool = pool
        self.cog = cog
        self.clicks = 0

        for r in range(3):
            for c in range(3):
                self.add_item(ScratchButton(r, c))

    async def reveal(self, interaction: discord.Interaction, r: int, c: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your scratchcard!", ephemeral=True
            )

        await interaction.response.defer()

        if self.revealed[r][c]:
            return await interaction.followup.send(
                "You already scratched this spot.", ephemeral=True
            )

        self.revealed[r][c] = True
        self.clicks += 1

        for child in self.children:
            if isinstance(child, ScratchButton) and child.row == r and child.col == c:
                multiplier = self.grid[r][c]
                label = f"+{multiplier}x" if multiplier > 0 else (f"{multiplier}x" if multiplier < 0 else "0x")
                child.label = label
                child.style = discord.ButtonStyle.success
                child.disabled = True

        remaining_spots = 3 - self.clicks
        if remaining_spots > 0:
            await interaction.edit_original_response(
                content=f"{remaining_spots} spot(s) left to scratch", view=self
            )
        else:
            await interaction.edit_original_response(
                content="Alright. Here is your result :)", view=self
            )
            await self.finish(interaction)

    async def finish(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
            if isinstance(child, ScratchButton):
                if self.revealed[child.row][child.col]:
                    val = self.grid[child.row][child.col]
                    child.label = f"+{val}x" if val > 0 else (f"{val}x" if val < 0 else "0x")
                    child.style = discord.ButtonStyle.success
                else:
                    child.label = "❓"

        picks = [self.grid[r][c] for r in range(3) for c in range(3) if self.revealed[r][c]]
        total_multi = sum(picks)
        winnings = self.bet * total_multi if total_multi > 0 else 0

        async with self.pool.acquire() as conn:
            is_addict = await conn.fetchval("""
                SELECT 1 FROM current_effects 
                WHERE user_id = $1 AND effect_id = 7
            """, self.user_id)
            
            mood_change = 4 if is_addict else 2
            
            if winnings > 0:
                # Pay winnings directly (coins appear)
                await conn.execute(
                    "UPDATE users SET coins = coins + $1, mood = LEAST(mood + $2, mood_max) WHERE id = $3",
                    winnings, mood_change, self.user_id
                )
                
                mood_row = await conn.fetchrow("SELECT mood, mood_max FROM users WHERE id = $1", self.user_id)
                if is_addict and mood_row and mood_row['mood'] >= mood_row['mood_max']:
                    await conn.execute("""
                        DELETE FROM current_effects 
                        WHERE user_id = $1 AND effect_id = 7
                    """, self.user_id)
                
                desc = (
                    f"Your picks: {picks}\n"
                    f"Total multiplier: {total_multi}x\n"
                    f"You won **{winnings}** coins!"
                )
            else:
                await conn.execute("UPDATE users SET mood = GREATEST(mood - $1, 0) WHERE id = $2", mood_change, self.user_id)
                desc = (
                    f"Your picks: {picks}\n"
                    f"Total multiplier: {total_multi}x\n"
                    f"You lost your bet of {self.bet} coins."
                )

        embed = discord.Embed(
            title="Scratchcard Result",
            description=desc,
            color=discord.Color.gold()
        )

        await interaction.edit_original_response(embed=embed, view=self)

class ScratchButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(label="🦆", style=discord.ButtonStyle.secondary, row=row)
        self.row = row
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view: ScratchView = self.view
        await view.reveal(interaction, self.row, self.col)



# ------------------- Embed helper -------------------
def make_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    return e

# --- Leaderboard View ---
class LeaderboardView(discord.ui.View):
    def __init__(self, cog, ctx: commands.Context, mode: str = "server"):
        super().__init__(timeout=300)  # Increased timeout to 5 minutes
        self.cog = cog
        self.ctx = ctx
        self.mode = mode

        # Add mode switch button
        if mode == "server":
            self.add_item(GlobalButton())
        else:
            self.add_item(ServerButton())

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            try:
                await interaction.response.send_message("Only the command user can refresh.", ephemeral=True)
            except discord.NotFound:
                pass
            return
        
        try:
            await interaction.response.defer()
            await self.cog.send_leaderboard(interaction, self.ctx, self.mode)
        except discord.NotFound:
            try:
                await self.ctx.send(embed=make_embed("Error", "Interaction expired. Please use the command again.", discord.Color.red()))
            except:
                pass

class GlobalButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Global", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        view: LeaderboardView = self.view
        if interaction.user != view.ctx.author:
            try:
                await interaction.response.send_message("You can't use this menu.", ephemeral=True)
            except discord.NotFound:
                pass  # Interaction expired
            return
        
        try:
            await interaction.response.defer()
            await view.cog.send_leaderboard(interaction, view.ctx, "global")
        except discord.NotFound:
            # Interaction expired, try to send a new message
            try:
                await view.ctx.send(embed=make_embed("Error", "Interaction expired. Please use the command again.", discord.Color.red()))
            except:
                pass

class ServerButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="This Server", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        view: LeaderboardView = self.view
        if interaction.user != view.ctx.author:
            try:
                await interaction.response.send_message("You can't use this menu.", ephemeral=True)
            except discord.NotFound:
                pass  # Interaction expired
            return
        
        try:
            await interaction.response.defer()
            await view.cog.send_leaderboard(interaction, view.ctx, "server")
        except discord.NotFound:
            # Interaction expired, try to send a new message
            try:
                await view.ctx.send(embed=make_embed("Error", "Interaction expired. Please use the command again.", discord.Color.red()))
            except:
                pass

# ------------------- Confirm Give View -------------------
class ConfirmGiveView(discord.ui.View):
    def __init__(self, giver_id: int, target_id: int, amount: int, cog: "Econ"):
        super().__init__(timeout=30)
        self.giver_id = giver_id
        self.target_id = target_id
        self.amount = amount
        self.cog = cog

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.giver_id:
            return await interaction.response.send_message("This confirmation is only for the command author.", ephemeral=True)
        await interaction.response.defer()
        await self.cog._give_confirmed(interaction, self.giver_id, self.target_id, self.amount)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.giver_id:
            return await interaction.response.send_message("This confirmation is only for the command author.", ephemeral=True)
        await interaction.response.edit_message(embed=make_embed("Cancelled", "Transfer cancelled.", discord.Color.orange()), view=None)
        self.stop()


# ------------------- PickUp View (for drop-coins) -------------------
class PickUpView(discord.ui.View):
    def __init__(self, bot, amount: int, message: discord.Message):
        super().__init__(timeout=30)
        self.bot = bot
        self.amount = amount
        self.claimed = False
        self.msg = message

    @discord.ui.button(label="Pick Up 💰", style=discord.ButtonStyle.green)
    async def pickup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            return await interaction.response.send_message("The coins have already been claimed.", ephemeral=True)
        self.claimed = True
        button.disabled = True
        await interaction.response.defer()
        try:
            await ensure_user(self.bot.db, interaction.user.id)
            async with self.bot.db.acquire() as conn:
                await conn.execute("UPDATE users SET coins = coins + $1 WHERE id = $2", self.amount, interaction.user.id)
            await self.msg.edit(view=self)
            await interaction.followup.send(f"🎉 You picked up **{self.amount}** coins!", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("An error occurred claiming the coins.", ephemeral=True)
        finally:
            self.stop()

    async def on_timeout(self):
        for c in self.children:
            try:
                c.disabled = True
            except Exception:
                pass
        try:
            await self.msg.edit(view=self)
        except Exception:
            pass
        if not self.claimed:
            try:
                await self.msg.channel.send("The dropped coins have disappeared...")
            except Exception:
                pass


# ------------------- Econ Cog (full ready-to-use) -------------------
class Econ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------- status / health ----------------
    @commands.hybrid_command(name="health", description="Check your current stats")
    async def health(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        await ctx.defer()
        try:
            if target is None:
                target = ctx.author

            await ensure_user(self.bot.db, target.id)
            await ensure_inventory(self.bot.db, target.id)

            async with self.bot.db.acquire() as conn:
                row = await conn.fetchrow("SELECT coins, energy, energy_max, mood, mood_max FROM users WHERE id = $1", target.id)
                effects = await conn.fetch("""
                    SELECT ue.icon, ue.name, ce.duration, ce.ticks, ce.applied_at
                    FROM current_effects ce
                    JOIN user_effects ue ON ce.effect_id = ue.id
                    WHERE ce.user_id = $1
                """, target.id)
                
                # Get inventory status
                total_items = await get_inventory_total(conn, target.id)
                inv_penalty = get_inventory_penalty(total_items)

            if not row:
                return await ctx.send(embed=make_embed("Error: Data Not Found", "User record not detected in database.", discord.Color.red()))

            energy = row["energy"]
            energy_max = row["energy_max"]
            mood = row["mood"]
            mood_max = row["mood_max"]

            energy_pct = round((energy / energy_max) * 100, 2) if energy_max else 0
            mood_pct = round((mood / mood_max) * 100, 2) if mood_max else 0

            color = discord.Color.green() if energy_pct >= 50 else discord.Color.gold() if energy_pct >= 20 else discord.Color.red()

            desc = (
                f"**Energy:** {energy} / {energy_max} ({energy_pct}%)\n"
                f"**Mood:** {mood} / {mood_max} ({mood_pct}%)\n\n"
                "Note: Energy and Mood parameters affect operational efficiency and reward calculations."
            )

            embed = make_embed(f"User Status Report: {target.display_name}", desc, color)
            try:
                embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
            except Exception:
                pass

            if effects:
                for eff in effects[:6]:
                    icon = eff.get('icon') or ''
                    name = eff.get('name') or 'Effect'
                    applied_at = eff.get('applied_at')
                    duration = eff.get('duration') or 0
                    try:
                        applied_ts = int(applied_at.timestamp())
                        remaining_seconds = duration * BASE_TICK
                        end_ts = applied_ts + remaining_seconds
                        embed.add_field(name=f"{icon} {name}", value=f"Remaining: <t:{int(end_ts)}:R>", inline=True)
                    except Exception:
                        embed.add_field(name=f"{icon} {name}", value=f"Duration: {duration}", inline=True)
            
            # Display inventory status
            if inv_penalty > 0:
                penalty_pct = int(inv_penalty * 100)
                embed.add_field(
                    name="⚠️ Alert: Inventory Overload",
                    value=f"Load: {total_items} items\nPerformance degradation: -{penalty_pct}%\nRecommendation: Reduce inventory load",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Inventory Status",
                    value=f"Load: {total_items} items\nStatus: Operational",
                    inline=False
                )

            await ctx.send(embed=embed)
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    # ---------------- work ----------------
    @commands.hybrid_command(name="work", description="Work to earn coins. May reduce energy if unlucky.")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def work(self, ctx: commands.Context):
        await ctx.defer()
        uid = ctx.author.id
        
        # Constants
        energy_cost = 10
        reward_range = (200, 800)
        mood_penalty = 5

        try:
            async with self.bot.db.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_config (user_id) VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                """, uid)
                
                user_exists = await conn.fetchrow("SELECT id FROM users WHERE id = $1", uid)
                if not user_exists:
                    await conn.execute("""
                        INSERT INTO users (id, coins, energy, energy_max, mood, mood_max)
                        VALUES ($1, 0, 100, 100, 100, 100)
                    """, uid)
                is_overworked = await conn.fetchval("""
                    SELECT 1 FROM current_effects 
                    WHERE user_id = $1 AND effect_id = 10
                """, uid)
                
                if is_overworked:
                    embed = discord.Embed(
                        title="Alert. Overworked",
                        description="Mandatory rest period active. Duration fifteen minutes. Wait for effect to expire.",
                        color=discord.Color.red()
                    )
                    return await ctx.send(embed=embed)
                
                from datetime import datetime, timedelta
                from bot import work_cache
                
                now = datetime.now()
                five_mins_ago = now - timedelta(minutes=5)
                
                if uid not in work_cache:
                    work_cache[uid] = []
                
                work_cache[uid] = [ts for ts in work_cache[uid] if ts > five_mins_ago]
                work_cache[uid].append(now)
                work_count = len(work_cache[uid])
                
                # Get user data
                row = await conn.fetchrow("SELECT coins, energy, energy_max, mood, mood_max FROM users WHERE id = $1", uid)
                if not row:
                    return await ctx.send("User data not found.")

                if row["energy"] < energy_cost:
                    embed = discord.Embed(
                        title="Warning. Energy insufficient",
                        description=f"Energy level at {row['energy']} out of {row['energy_max']}. Minimum {energy_cost} required. Rest or consume energy items.",
                        color=discord.Color.red()
                    )
                    return await ctx.send(embed=embed)
                
                if row["energy"] < 10:
                    await conn.execute("""
                        INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                        VALUES ($1, 6, 60, 60, NOW())
                        ON CONFLICT (user_id, effect_id) DO UPDATE
                        SET duration = 60, ticks = 60, applied_at = NOW()
                    """, uid)

                mood_ratio = row["mood"] / row["mood_max"] if row["mood_max"] else 0
                fail_chance = 0.1 if mood_ratio >= 0.6 else 0.5 if mood_ratio >= 0.3 else 0.8
                is_success = random.random() > fail_chance

                if is_success:
                    from bot import work_failures_cache
                    work_failures_cache[uid] = {'count': 0, 'last_reset': datetime.now().date()}
                    
                    reward = random.randint(*reward_range)
                    
                    has_toolbelt = await conn.fetchval("""
                        SELECT quantity FROM inventory 
                        WHERE id = $1 AND item_id = 26 AND quantity > 0
                    """, uid)
                    
                    toolbelt_bonus = False
                    if has_toolbelt:
                        reward = int(reward * 1.25)
                        toolbelt_bonus = True
                    
                    is_motivated = await conn.fetchval("""
                        SELECT 1 FROM current_effects 
                        WHERE user_id = $1 AND effect_id = 8
                    """, uid)
                    
                    if is_motivated:
                        reward = int(reward * 1.25)
                    
                    is_demoralized = await conn.fetchval("""
                        SELECT 1 FROM current_effects 
                        WHERE user_id = $1 AND effect_id = 9
                    """, uid)
                    
                    if is_demoralized:
                        reward = int(reward * 0.7)
                    
                    await conn.execute("""
                        UPDATE users
                        SET coins = coins + $1, energy = GREATEST(energy - $2, 0), mood = GREATEST(mood - 1, 0)
                        WHERE id = $3
                    """, reward, energy_cost, uid)
                    
                    # Determine material drops
                    materials_found = []
                    
                    # Roll for materials

                    if random.random() < 0.50:
                        scrap_amt = random.randint(1, 3)
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity) VALUES ($1, 3, $2)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $2
                        """, uid, scrap_amt)
                        materials_found.append(f"{scrap_amt}x Scrap")

                    if random.random() < 0.40:
                        wood_amt = random.randint(1, 3)
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity) VALUES ($1, 19, $2)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $2
                        """, uid, wood_amt)
                        materials_found.append(f"{wood_amt}x Wood")
                    
                    if random.random() < 0.25:
                        stone_amt = random.randint(1, 2)
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity) VALUES ($1, 18, $2)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $2
                        """, uid, stone_amt)
                        materials_found.append(f"{stone_amt}x Stone")
                    
                    if random.random() < 0.10:
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity) VALUES ($1, 3, 1)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + 1
                        """, uid)
                        materials_found.append("1x Scrap")
                    
                    if random.random() < 0.05:
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity) VALUES ($1, 10, 1)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + 1
                        """, uid)
                        materials_found.append("1x Herb")
                    
                    if random.random() < 0.03:
                        await conn.execute("""
                            INSERT INTO inventory (id, item_id, quantity) VALUES ($1, 15, 1)
                            ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + 1
                        """, uid)
                        materials_found.append("1x Coal")
                    
                    # Build VIT-style status report
                    embed = discord.Embed(
                        title="Work Complete",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Reward", value=f"{reward} coins", inline=True)
                    
                    if toolbelt_bonus:
                        embed.add_field(name="Bonus", value="Toolbelt: +25%", inline=True)
                    
                    embed.add_field(name="Energy", value=f"-{energy_cost}", inline=True)
                    
                    if materials_found:
                        embed.add_field(name="Resources Acquired", value="\n".join(materials_found), inline=False)
                    
                    embed.add_field(name="Status", value="Operational", inline=False)
                    
                    overwork_chance = min(work_count / 20, 1.0)
                    if random.random() < overwork_chance:
                        await conn.execute("""
                            INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                            VALUES ($1, 10, 30, 30, NOW())
                        """, uid)
                        embed.add_field(name="Warning", value="Overworked effect applied. Mandatory rest period: 15 minutes", inline=False)
                    
                    await ctx.send(embed=embed)
                else:
                    from bot import work_failures_cache
                    
                    if uid not in work_failures_cache:
                        work_failures_cache[uid] = {'count': 0, 'last_reset': datetime.now().date()}
                    
                    work_failures_cache[uid]['count'] += 1
                    failure_count = work_failures_cache[uid]['count']
                    
                    if failure_count >= 3:
                        await conn.execute("""
                            INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                            VALUES ($1, 9, 120, 120, NOW())
                            ON CONFLICT (user_id, effect_id) DO UPDATE
                            SET duration = 120, ticks = 120, applied_at = NOW()
                        """, uid)
                        work_failures_cache[uid]['count'] = 0
                    await conn.execute("""
                        UPDATE users
                        SET energy = GREATEST(energy - $1, 0), mood = GREATEST(mood - $2, 0)
                        WHERE id = $3
                    """, energy_cost, mood_penalty, uid)
                    
                    # Build VIT-style failure report
                    embed = discord.Embed(
                        title="Work Failed",
                        description="Operation unsuccessful. Resources depleted.",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Energy", value=f"-{energy_cost}", inline=True)
                    embed.add_field(name="Mood", value=f"-{mood_penalty}", inline=True)
                    embed.add_field(name="Status", value="Retry available", inline=False)
                    
                    await ctx.send(embed=embed)
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    @work.error
    async def work_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            embed = discord.Embed(
                title="Cooldown Active",
                description=f"Work command on cooldown. Retry available in {remaining} seconds.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            # Re-raise other errors
            raise error

    # ---------------- slot-machine ----------------
    @commands.hybrid_command(name="slot-machine", description="Spin the slots!", aliases=["slot"])
    async def slot_machine(self, ctx: commands.Context, pay: int):
        
        await ctx.defer()
        uid = ctx.author.id
        cap = await get_bet_cap(ctx.author.id)
        if( pay > cap):
            return await ctx.send(embed=make_embed("Bet exceeded", f"Your maximum bet is {cap} coins. You can upvote the bot to bet at 500k coins max.", discord.Color.red()))
        if pay <= 0:
            return await ctx.send(embed=make_embed("Error. Invalid bet", "Minimum bet one coin.", discord.Color.red()))

        await ensure_user(self.bot.db, uid)
        await ensure_inventory(self.bot.db, uid)

        energy_cost = 1
        mood_gain_on_win = 2
        mood_loss_on_fail = 1

        try:
            async with self.bot.db.acquire() as conn:
                row = await conn.fetchrow("SELECT coins, energy, mood, mood_max FROM users WHERE id = $1", uid)
                if row["coins"] < pay:
                    return await ctx.send(embed=make_embed("Error. Insufficient funds", f"Minimum {pay} coins required. Available {row['coins']} coins.", discord.Color.red()))
                if row["energy"] < energy_cost:
                    return await ctx.send(embed=make_embed("Warning. Energy insufficient", f"Minimum {energy_cost} required. Current level {row['energy']}. Rest or consume energy items.", discord.Color.red()))

                # Deduct bet from user
                await log_spending(self.bot.db, pay)
                await conn.execute("UPDATE users SET coins = coins - $1, energy = GREATEST(energy - $2, 0) WHERE id = $3", pay, energy_cost, uid)

            symbols = ["💠", "🍀", "🔔", "⭐", "🍒"]
            result = [random.choice(symbols) for _ in range(3)]
            counts = {s: result.count(s) for s in set(result)}
            max_count = max(counts.values())

            multiplier = 5.0 if max_count == 3 else 1.5 if max_count == 2 else 0.0
            winnings = round(pay * multiplier)

            async with self.bot.db.acquire() as conn:
                from bot import gambling_cache
                from datetime import datetime
                
                today = datetime.now().date()
                cache_key = f"{uid}_{today}"
                
                if cache_key not in gambling_cache:
                    gambling_cache[cache_key] = 0
                gambling_cache[cache_key] += 1
                
                gamble_count = gambling_cache[cache_key]
                
                is_addict = await conn.fetchval("""
                    SELECT 1 FROM current_effects 
                    WHERE user_id = $1 AND effect_id = 7
                """, uid)
                
                mood_change_win = mood_gain_on_win * 2 if is_addict else mood_gain_on_win
                mood_change_loss = mood_loss_on_fail * 2 if is_addict else mood_loss_on_fail
                
                if winnings > 0:
                    # Pay winnings directly (coins appear)
                    await conn.execute("UPDATE users SET coins = coins + $1, mood = LEAST(mood + $2, mood_max) WHERE id = $3", winnings, mood_change_win, uid)
                    
                    mood_row = await conn.fetchrow("SELECT mood, mood_max FROM users WHERE id = $1", uid)
                    if is_addict and mood_row and mood_row['mood'] >= mood_row['mood_max']:
                        await conn.execute("""
                            DELETE FROM current_effects 
                            WHERE user_id = $1 AND effect_id = 7
                        """, uid)
                else:
                    await conn.execute("UPDATE users SET mood = GREATEST(mood - $1, 0) WHERE id = $2", mood_change_loss, uid)
                
                if not is_addict:
                    addict_chance = min(gamble_count / 40, 1.0)
                    if random.random() < addict_chance:
                        await conn.execute("""
                            INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                            VALUES ($1, 7, 999999, 999999, NOW())
                        """, uid)

            color = discord.Color.blue() if winnings > 0 else discord.Color.red()
            status = "Success" if winnings > 0 else "Loss"
            embed = discord.Embed(title="Slot Machine Results", color=color, timestamp=datetime.utcnow())
            embed.add_field(name="Bet", value=f"{pay} coins", inline=True)
            embed.add_field(name="Result", value=" | ".join(result), inline=False)
            embed.add_field(name="Multiplier", value=f"{multiplier:.1f}x", inline=True)
            embed.add_field(name="Payout", value=f"{winnings:+} coins", inline=True)
            embed.add_field(name="Status", value=status, inline=False)
            mood_text = "+2" if winnings > 0 else "-1"
            embed.set_footer(text=f"Mood: {mood_text}")

            await ctx.send(embed=embed)
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    # ---------------- balance ----------------
    @commands.hybrid_command(name="balance", description="Check your current coin balance", aliases=["bal"])
    async def balance(self, ctx: commands.Context):
        await ctx.defer()
        await ensure_user(self.bot.db, ctx.author.id)
        try:
            async with self.bot.db.acquire() as conn:
                coins = await conn.fetchval("SELECT coins FROM users WHERE id = $1", ctx.author.id)

            embed = make_embed("💰 Coin Balance", f"Your balance: **{format_number(coins)}** coins.", discord.Color.gold())
            try:
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            except Exception:
                pass
            await ctx.send(embed=embed)
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    # ---------------- give-coins (with confirmation) ----------------
    @commands.hybrid_command(name="give-coins", description="Give coins to another user (supports 'all', '50%', '!100', etc.)", aliases=["gc", "give-coin"])
    async def give_coins(self, ctx: commands.Context, target: discord.Member, amount: str):
        await ctx.defer()
        giver_id = ctx.author.id
        target_id = target.id

        if target.bot or target_id == giver_id:
            return await ctx.send(embed=make_embed("Invalid target", "You cannot give coins to that target.", discord.Color.red()))

        await ensure_user(self.bot.db, giver_id)
        await ensure_user(self.bot.db, target_id)

        try:
            async with self.bot.db.acquire() as conn:
                coins = await conn.fetchval("SELECT coins FROM users WHERE id = $1", giver_id)
                if coins is None:
                    return await ctx.send(embed=make_embed("Error", "User data not found.", discord.Color.red()))

                # Parse amount using parser utility (supports 'all', '50%', '!100', etc.)
                try:
                    parsed_amount = parse_amount(amount, coins)
                except AmountParseError as e:
                    return await ctx.send(embed=make_embed("Invalid amount", str(e), discord.Color.red()))

                if parsed_amount <= 0:
                    return await ctx.send(embed=make_embed("Invalid amount", "Amount must be greater than 0.", discord.Color.red()))

                if coins < parsed_amount:
                    return await ctx.send(embed=make_embed("Insufficient funds", "You don't have enough coins.", discord.Color.red()))

            # Calculate transfer tax
            tax_amount, remaining_amount = await calculate_transfer_tax(self.bot.db, ctx.guild.id, parsed_amount)

            view = ConfirmGiveView(giver_id, target_id, parsed_amount, self)
            embed = make_embed(
                "Confirm Transfer",
                f"Send **{parsed_amount}** coins to {target.mention}?\n\n"
                f"**Tax Rate:** {tax_amount/parsed_amount*100:.1f}%\n"
                f"**Transfer Tax:** {tax_amount} coins\n"
                f"**Target will receive:** {remaining_amount} coins",
                discord.Color.blurple()
            )

            embed.set_footer(text=f"The tax money ({tax_amount} coins) will go to server fund")
            await ctx.send(embed=embed, view=view)
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    async def _give_confirmed(self, interaction: discord.Interaction, giver_id: int, target_id: int, amount: int):
        try:
            
            guild_id = interaction.guild.id if interaction.guild else None
            if not guild_id:
                return await interaction.followup.send(embed=make_embed("Error", "Cannot determine server for tax calculation.", discord.Color.red()), ephemeral=True)

            # Calculate transfer tax
            tax_amount, remaining_amount = await calculate_transfer_tax(self.bot.db, guild_id, amount)

            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    giver = await conn.fetchrow("SELECT coins FROM users WHERE id = $1 FOR UPDATE", giver_id)
                    if not giver or giver["coins"] < amount:
                        return await interaction.followup.send(embed=make_embed("Failed", "Insufficient funds.", discord.Color.red()), ephemeral=True)

                
                    await conn.execute("INSERT INTO guilds (id) VALUES ($1) ON CONFLICT (id) DO NOTHING", guild_id)

                   
                    await conn.execute("UPDATE users SET coins = coins - $1 WHERE id = $2", amount, giver_id)
                  
                    await conn.execute("UPDATE users SET coins = coins + $1 WHERE id = $2", remaining_amount, target_id)
                 
                    if tax_amount > 0:
                        await conn.execute("UPDATE guilds SET coins = coins + $1 WHERE id = $2", tax_amount, guild_id)

           
            if tax_amount > 0:
                await interaction.edit_original_response(embed=make_embed(
                    "Transfer Complete",
                    f"Transferred **{remaining_amount}** coins to <@{target_id}>.\n"
                    f"Tax collected by server: **{tax_amount}** coins ({tax_amount/amount*100:.1f}%)",
                    discord.Color.green()
                ), view=None)
            else:
                await interaction.edit_original_response(embed=make_embed(
                    "Transfer Complete",
                    f"Transferred **{remaining_amount}** coins to <@{target_id}>.",
                    discord.Color.green()
                ), view=None)
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send(embed=make_embed("Error", "Transaction failed." , discord.Color.red()), ephemeral=True)
            except Exception:
                pass

    # ---------------- Leaderboard Command ----------------
    @commands.hybrid_command(name="leaderboard", description="Show the richest users", aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()
        await self.send_leaderboard(ctx, ctx, "server")  # default = server


    async def send_leaderboard(self, interaction_or_ctx, ctx: commands.Context, mode: str):
        try:
            author_id = ctx.author.id
            
            if mode == "server" and ctx.guild:
                async with self.bot.db.acquire() as conn:
                    # Get top 10
                    top = await conn.fetch("""
                        SELECT id, coins FROM users
                        WHERE id = ANY($1::bigint[])
                        ORDER BY coins DESC LIMIT 10
                    """, [m.id for m in ctx.guild.members if not m.bot])
                    
                    # Get total count and author's rank
                    total_count = await conn.fetchval("""
                        SELECT COUNT(*) FROM users
                        WHERE id = ANY($1::bigint[])
                    """, [m.id for m in ctx.guild.members if not m.bot])
                    
                    author_rank = await conn.fetchval("""
                        SELECT COUNT(*) + 1 FROM users
                        WHERE id = ANY($1::bigint[]) AND coins > (
                            SELECT coins FROM users WHERE id = $2
                        )
                    """, [m.id for m in ctx.guild.members if not m.bot], author_id)
                    
                    author_coins = await conn.fetchval("SELECT coins FROM users WHERE id = $1", author_id)
            else:
                async with self.bot.db.acquire() as conn:
                    # Get top 10
                    top = await conn.fetch("""SELECT u.id, u.coins
                        FROM users u
                        JOIN user_config c ON u.id = c.user_id
                        WHERE c.lb_opt_in = TRUE
                        ORDER BY u.coins DESC
                        LIMIT 10""")
                    
                    # Get total count and author's rank
                    total_count = await conn.fetchval("""
                        SELECT COUNT(*) FROM users u
                        JOIN user_config c ON u.id = c.user_id
                        WHERE c.lb_opt_in = TRUE
                    """)
                    
                    author_rank = await conn.fetchval("""
                        SELECT COUNT(*) + 1 FROM users u
                        JOIN user_config c ON u.id = c.user_id
                        WHERE c.lb_opt_in = TRUE AND u.coins > (
                            SELECT coins FROM users WHERE id = $1
                        )
                    """, author_id)
                    
                    author_coins = await conn.fetchval("SELECT coins FROM users WHERE id = $1", author_id)

            if not top:
                embed = make_embed("No data", "No leaderboard data available.", discord.Color.red())
            else:
                title = "🏠 Server Leaderboard" if mode == "server" else "🌐 Global Leaderboard"
                embed = discord.Embed(title=title, color=discord.Color.gold(), timestamp=datetime.utcnow())

                # Add author's current ranking info
                if author_rank and author_coins is not None:
                    top_percentage = round((author_rank / total_count) * 100, 1) if total_count > 0 else 0
                    embed.add_field(
                        name="Your Ranking",
                        value=f"**Rank**: #{author_rank:,}\n**Coins**: {format_number(author_coins)}\n**Top**: {top_percentage}%",
                        inline=True
                    )

                for i, row in enumerate(top, start=1):
                    uid = row["id"]
                    coins = row["coins"]
                    
                    # Get user info
                    if mode == "server" and ctx.guild:
                        member = ctx.guild.get_member(uid)
                        if member:
                            name = member.display_name
                            username = member.name
                        else:
                            # Try to fetch user from bot cache or API
                            try:
                                user = await self.bot.fetch_user(uid)
                                name = user.display_name or user.name
                                username = user.name
                            except:
                                name = f"User {uid}"
                                username = "Unknown"
                    else:
                        # Global leaderboard - fetch user info
                        try:
                            user = await self.bot.fetch_user(uid)
                            name = user.display_name or user.name
                            username = user.name
                        except:
                            name = f"User {uid}"
                            username = "Unknown"
                    
                    # Create ranking info
                    rank_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**#{i}**"
                    
                    embed.add_field(
                        name=f"{rank_emoji} {name}", 
                        value=f"**Username**: {username}\n**Coins**: {format_number(coins)}", 
                        inline=False
                    )

                embed.set_footer(text="You can opt-out (leaving) the global ranking by using /leaderboard-opt-in ")

            view = LeaderboardView(self, ctx, mode)
            if isinstance(interaction_or_ctx, discord.Interaction):
                try:
                    # Check if interaction was already deferred
                    if interaction_or_ctx.response.is_done():
                        await interaction_or_ctx.edit_original_response(embed=embed, view=view)
                    else:
                        await interaction_or_ctx.response.edit_message(embed=embed, view=view)
                except discord.NotFound:
                    # Interaction expired, send new message
                    await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed, view=view)
        except Exception:
            traceback.print_exc()
            if isinstance(interaction_or_ctx, discord.Interaction):
                try:
                    # Check if interaction was already deferred
                    if interaction_or_ctx.response.is_done():
                        await interaction_or_ctx.followup.send(embed=make_embed("Error", "Leaderboard failed.", discord.Color.red()), ephemeral=True)
                    else:
                        await interaction_or_ctx.response.send_message(embed=make_embed("Error", "Leaderboard failed.", discord.Color.red()), ephemeral=True)
                except discord.NotFound:
                    # Interaction expired, send new message
                    await ctx.send(embed=make_embed("Error", "Leaderboard failed.", discord.Color.red()))
            else:
                await ctx.send(embed=make_embed("Error", "Leaderboard failed.", discord.Color.red()))

    # ---------------- flipbet ----------------
    @commands.hybrid_command(name="flipbet", aliases=["fb"], description="Bet coins on a coinflip (supports 'all', '50%', '!100', etc.)")
    async def flipbet(self, ctx: commands.Context, guess: str, amount: str):
        await ctx.defer()
        guess = guess.lower()
        if guess not in ["heads", "tails"]:
            return await ctx.send(embed=make_embed("Error: Invalid Input", "Valid options: `heads` or `tails`", discord.Color.red()))

        uid = ctx.author.id
        await ensure_user(self.bot.db, uid)
        
        try:
            async with self.bot.db.acquire() as conn:
                user = await conn.fetchrow("SELECT coins, energy FROM users WHERE id = $1", uid)
                if not user:
                    return await ctx.send(embed=make_embed("Error: User Not Found", "User record not detected in database.", discord.Color.red()))
                
                # Parse amount using parser utility (supports 'all', '50%', '!100', etc.)
                try:
                    parsed_amount = parse_amount(amount, user["coins"])
                except AmountParseError as e:
                    return await ctx.send(embed=make_embed("Invalid bet", str(e), discord.Color.red()))
                
                if parsed_amount <= 0:
                    return await ctx.send(embed=make_embed("Error: Invalid Bet", "Minimum bet: 1 coin", discord.Color.red()))
                
                cap = await get_bet_cap(ctx.author.id)
                if parsed_amount > cap:
                    return await ctx.send(embed=make_embed("Bet exceeded", f"Your maximum bet is {cap} coins. You can upvote the bot to bet at 500k coins max.", discord.Color.red()))
                
                if user["coins"] < parsed_amount:
                    return await ctx.send(embed=make_embed("Error. Insufficient funds", f"Minimum {parsed_amount} coins required. Available {user['coins']} coins.", discord.Color.red()))
                if user["energy"] < 1:
                    return await ctx.send(embed=make_embed("Warning. Energy insufficient", f"Minimum one required. Current level {user['energy']}. Rest or consume energy items.", discord.Color.red()))

                # Deduct energy and log spending (use parsed_amount)
                await conn.execute("UPDATE users SET energy = energy - 1 WHERE id = $1", uid)
                await log_spending(self.bot.db, parsed_amount)
                
                from bot import gambling_cache
                from datetime import datetime
                
                today = datetime.now().date()
                cache_key = f"{uid}_{today}"
                
                if cache_key not in gambling_cache:
                    gambling_cache[cache_key] = 0
                gambling_cache[cache_key] += 1
                
                gamble_count = gambling_cache[cache_key]
                
                is_addict = await conn.fetchval("""
                    SELECT 1 FROM current_effects 
                    WHERE user_id = $1 AND effect_id = 7
                """, uid)
                
                mood_change = 4 if is_addict else 2
                
                result = random.choice(["heads", "tails"])
                win = (guess == result)
                if win:
                    # Pay winnings directly (coins appear) - use parsed_amount
                    await conn.execute("UPDATE users SET coins = coins + $1, mood = LEAST(mood + $2, mood_max) WHERE id = $3", parsed_amount, mood_change, uid)
                    desc = f"Result: **{result}**\nStatus: Victory\nPayout: +{parsed_amount} coins"
                    
                    mood_row = await conn.fetchrow("SELECT mood, mood_max FROM users WHERE id = $1", uid)
                    if is_addict and mood_row and mood_row['mood'] >= mood_row['mood_max']:
                        await conn.execute("""
                            DELETE FROM current_effects 
                            WHERE user_id = $1 AND effect_id = 7
                        """, uid)
                    
                    color = discord.Color.blue()
                else:
                    # Deduct bet (coins disappear) - use parsed_amount
                    await conn.execute("UPDATE users SET coins = coins - $1, mood = GREATEST(mood - $2, 0) WHERE id = $3", parsed_amount, mood_change, uid)
                    desc = f"Result: **{result}**\nStatus: Loss\nAmount: -{parsed_amount} coins"
                    color = discord.Color.red()
                
                if not is_addict:
                    addict_chance = min(gamble_count / 40, 1.0)
                    if random.random() < addict_chance:
                        await conn.execute("""
                            INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                            VALUES ($1, 7, 999999, 999999, NOW())
                        """, uid)

            await ctx.send(embed=make_embed("Coinflip Results", desc, color))
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    # ---------------- drop-coins ----------------
    @commands.hybrid_command(name="drop-coins", aliases=["dc"], description="Drop coins for others (supports 'all', '50%', '!100', etc.)")
    async def drop_coins(self, ctx: commands.Context, amount: str):
        await ctx.defer()
        uid = ctx.author.id
        await ensure_user(self.bot.db, uid)

        try:
            async with self.bot.db.acquire() as conn:
                bal = await conn.fetchval("SELECT coins FROM users WHERE id = $1", uid)
                
                # Parse amount using parser utility (supports 'all', '50%', '!100', etc.)
                try:
                    parsed_amount = parse_amount(amount, bal)
                except AmountParseError as e:
                    return await ctx.send(embed=make_embed("Invalid amount", str(e), discord.Color.red()))
                
                if parsed_amount <= 0:
                    return await ctx.send(embed=make_embed("Invalid amount", "Amount must be greater than 0.", discord.Color.red()))
                
                if bal < parsed_amount:
                    return await ctx.send(embed=make_embed("Insufficient", "You don't have enough coins.", discord.Color.red()))
                
                await conn.execute("UPDATE users SET coins = coins - $1 WHERE id = $2", parsed_amount, uid)

            embed = make_embed("💰 Coin Drop!", f"{ctx.author.mention} dropped **{parsed_amount}** coins! Click the button to pick them up.", discord.Color.gold())
            embed.set_footer(text="Coins disappear in 30 seconds.")
            msg = await ctx.send(embed=embed)
            view = PickUpView(self.bot, parsed_amount, msg)
            await msg.edit(view=view)
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    # --------
    @commands.hybrid_command(name="scratchcard", description="Play a scratchcard", aliases=["scratch"])
    async def scratchcard(self, ctx: commands.Context, bet: int):
        await ctx.defer()
        uid = ctx.author.id
        cap = await get_bet_cap(ctx.author.id)
        if( bet > cap):
            return await ctx.send(embed=make_embed("Bet exceeded", f"Your maximum bet is {cap} coins. You can upvote the bot to bet at 500k coins max.", discord.Color.red()))
        if bet < 100:
            return await ctx.send(embed=make_embed(
                "Error: Invalid Bet", "Minimum bet: 100 coins", discord.Color.red()
            ))

        await ensure_user(self.bot.db, uid)
        await ensure_inventory(self.bot.db, uid)

        # Show multipliers & weights
        prize_lines = [f"{m:+}x ({round(w * 100, 2)}%)" for m, w in zip(MULTIPLIERS, MULTI_WEIGHTS)]
        prize_text = "\n".join(prize_lines)

        desc = (
            f"Select 3 slots to reveal multipliers.\n"
            f"Bet: {bet} coins\n\n"
            f"**Available Multipliers:**\n{prize_text}\n\n"
            "Calculation: Sum of 3 selections x bet\n"
            "• Total > 0: Victory (bet x total)\n"
            "• Total ≤ 0: Loss (bet forfeited)"
        )

        try:
            async with self.bot.db.acquire() as conn:
                row = await conn.fetchrow("SELECT coins, energy FROM users WHERE id = $1", uid)
                if row["coins"] < bet:
                    return await ctx.send(embed=make_embed(
                        "Error: Insufficient Funds", f"Required: {bet} coins\nAvailable: {row['coins']} coins", discord.Color.red()
                    ))
                if row["energy"] < 1:
                    return await ctx.send(embed=make_embed(
                        "Warning. Energy insufficient", f"Minimum one required. Current level {row['energy']}. Rest or consume energy items.", discord.Color.red()
                    ))

                # Deduct bet from user
                await conn.execute(
                    "UPDATE users SET coins = coins - $1, energy = GREATEST(energy - 1, 0) WHERE id = $2",
                    bet, uid
                )
                await log_spending(self.bot.db, bet)
                
                from bot import gambling_cache
                from datetime import datetime
                
                today = datetime.now().date()
                cache_key = f"{uid}_{today}"
                
                if cache_key not in gambling_cache:
                    gambling_cache[cache_key] = 0
                gambling_cache[cache_key] += 1
                
                gamble_count = gambling_cache[cache_key]
                
                is_addict = await conn.fetchval("""
                    SELECT 1 FROM current_effects 
                    WHERE user_id = $1 AND effect_id = 7
                """, uid)
                
                if not is_addict:
                    addict_chance = min(gamble_count / 40, 1.0)
                    if random.random() < addict_chance:
                        await conn.execute("""
                            INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                            VALUES ($1, 7, 999999, 999999, NOW())
                        """, uid)

            grid = generate_grid()
            view = ScratchView(uid, grid, bet, self.bot.db, self)

            embed = discord.Embed(
                title="Scratchcard Game",
                description=desc,
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed, view=view)

        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed(
                "Error", "An unexpected error occurred.", discord.Color.red()
            ))


    # ---------------- fund (guild) check ----------------
    @commands.hybrid_command(name="fund", description="Check your server's fund balance.", aliases=["budget"])
    async def fund_check(self, ctx: commands.Context):
        await ctx.defer()
        await ensure_guild(self.bot.db, ctx.guild.id)
        try:
            async with self.bot.db.acquire() as conn:
                guild = await conn.fetchrow("SELECT coins FROM guilds WHERE id = $1", ctx.guild.id)
            coins = guild["coins"] if guild else 0
            await ctx.send(embed=make_embed(f"{ctx.guild.name} Fund", f"Balance: **{format_number(coins)}** coins", discord.Color.gold()))
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    # Global fund system removed - gambling now uses coin appearance/disappearance model

    # ---------------- fund-give (guild -> user) ----------------
    @commands.hybrid_command(name="fund-give", description="Give from server fund (supports 'all', '50%', '!100', etc.)", aliases=["fg", "add-money"])
    async def fund_give(self, ctx: commands.Context, target: discord.User, amount: str):
        await ctx.defer()
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(embed=make_embed("Permission denied", "You need Manage Server to do this.", discord.Color.red()))

        await ensure_guild(self.bot.db, ctx.guild.id)
        await ensure_user(self.bot.db, target.id)

        try:
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    guild_row = await conn.fetchrow("SELECT coins FROM guilds WHERE id = $1 FOR UPDATE", ctx.guild.id)
                    if not guild_row:
                        return await ctx.send(embed=make_embed("Error", "Guild data not found.", discord.Color.red()))
                    
                    # Parse amount using parser utility (supports 'all', '50%', '!100', etc.)
                    try:
                        parsed_amount = parse_amount(amount, guild_row["coins"])
                    except AmountParseError as e:
                        return await ctx.send(embed=make_embed("Invalid amount", str(e), discord.Color.red()))
                    
                    if parsed_amount <= 0:
                        return await ctx.send(embed=make_embed("Invalid amount", "Amount must be greater than 0.", discord.Color.red()))
                    
                    if guild_row["coins"] < parsed_amount:
                        return await ctx.send(embed=make_embed("Insufficient fund", "Server fund does not have enough coins.", discord.Color.red()))

                    await conn.execute("UPDATE guilds SET coins = coins - $1 WHERE id = $2", parsed_amount, ctx.guild.id)
                    await conn.execute("UPDATE users SET coins = coins + $1 WHERE id = $2", parsed_amount, target.id)

            await ctx.send(embed=make_embed("Fund Transfer Complete", f"Transferred **{format_number(parsed_amount)}** coins to {target.mention}", discord.Color.green()))
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))

    #@commands.hybrid_command(name="fund-donate", description="Donate to server fund (supports 'all', '50%', '!100', etc.)")
    async def fund_donate(self, ctx: commands.Context, amount: str):
        await ctx.defer()
        target = ctx.author

        await ensure_guild(self.bot.db, ctx.guild.id)
        await ensure_user(self.bot.db, target.id)

        try:
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    # Correct table and ID used here
                    user_row = await conn.fetchrow("SELECT coins FROM users WHERE id = $1 FOR UPDATE", target.id)
                    
                    if not user_row:
                        return await ctx.send(embed=make_embed("Error", "User data not found.", discord.Color.red()))
                    
                    # Parse amount using parser utility (supports 'all', '50%', '!100', etc.)
                    try:
                        parsed_amount = parse_amount(amount, user_row["coins"])
                    except AmountParseError as e:
                        return await ctx.send(embed=make_embed("Invalid amount", str(e), discord.Color.red()))
                    
                    if parsed_amount <= 0:
                        return await ctx.send(embed=make_embed("Invalid amount", "Amount must be greater than 0.", discord.Color.red()))
                    
                    if user_row["coins"] < parsed_amount:
                        return await ctx.send(embed=make_embed("Insufficient fund", "You do not have enough coins.", discord.Color.red()))

                    await conn.execute("UPDATE guilds SET coins = coins + $1 WHERE id = $2", parsed_amount, ctx.guild.id)
                    await conn.execute("UPDATE users SET coins = coins - $1 WHERE id = $2", parsed_amount, target.id)

            await ctx.send(embed=make_embed("Fund Donation Complete", f"Donated **{format_number(parsed_amount)}** coins to {ctx.guild.name}", discord.Color.green()))
        except Exception:
            traceback.print_exc()
            await ctx.send(embed=make_embed("Error", "An unexpected error occurred.", discord.Color.red()))



    # Global fund donation removed - gambling now uses coin appearance/disappearance model
    
# ------------------- Setup -------------------
async def setup(bot):
    await bot.add_cog(Econ(bot))
