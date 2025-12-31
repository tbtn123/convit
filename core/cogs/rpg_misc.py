import os
import random
import discord
from discord.ext import commands
from typing import Literal
import aiohttp, traceback
from utils.db_helpers import (
    ensure_user,
    get_user_partners,
    get_user_children,
    get_parent,
    get_parents,
    is_too_closely_related,
)
from dotenv import load_dotenv
from utils.singleton import EffectID
from utils.translation import translate as tr, translate_bulk
import logging


from datetime import datetime, timedelta

# Track user's last active guild and timestamp
# Format: {user_id: (guild_id, last_seen_timestamp)}
user_current_guild = {}
ACTIVITY_TIMEOUT = timedelta(minutes=30)  # User must have chatted in last 30 minutes

load_dotenv()

logger = logging.getLogger("RPG_MISC")

class RPG_MISC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_family_relationship(self, user_id: int, target_id: int):
        """
        Returns:
            (True, relation) where relation in {"partner", "parent", "child", "sibling", "ancestor", "descendant", "extended_family"}
            or (False, "")
        """
        await ensure_user(self.bot.db, user_id)
        await ensure_user(self.bot.db, target_id)

        partners = await get_user_partners(self.bot.db, user_id)
        if target_id in partners:
            return True, "partner"

        children = await get_user_children(self.bot.db, user_id)
        if target_id in children:
            return True, "child"

        parent_ids = await get_parents(self.bot.db, user_id)
        if target_id in parent_ids:
            return True, "parent"

        # Reverse check: target considers user as parent
        target_parent_ids = await get_parents(self.bot.db, target_id)
        if user_id in target_parent_ids:
            return True, "child"

        # Check for siblings (common parent)
        common_parents = set(parent_ids) & set(target_parent_ids)
        if common_parents:
            return True, "sibling"

        # Check for extended family relationships (up to 3 generations)
        is_related = await is_too_closely_related(self.bot.db, user_id, target_id, depth=3)
        if is_related:
            return True, "extended_family"

        # Check for ancestor/descendant relationship
        async with self.bot.db.acquire() as conn:
            is_ancestor = await conn.fetchval("""
                WITH RECURSIVE ancestors(id) AS (
                    SELECT parent_id FROM parents WHERE child_id = $1
                    UNION
                    SELECT p.parent_id FROM parents p JOIN ancestors a ON p.child_id = a.id
                )
                SELECT EXISTS(SELECT 1 FROM ancestors WHERE id = $2)
            """, user_id, target_id)

            if is_ancestor:
                return True, "ancestor"

            is_descendant = await conn.fetchval("""
                WITH RECURSIVE descendants(id) AS (
                    SELECT child_id FROM parents WHERE parent_id = $1
                    UNION
                    SELECT p.child_id FROM parents p JOIN descendants d ON p.parent_id = d.id
                )
                SELECT EXISTS(SELECT 1 FROM descendants WHERE id = $2)
            """, user_id, target_id)

            if is_descendant:
                return True, "descendant"

        return False, ""

    async def add_mood(self, conn, user_id: int, amount: int):
        row = await conn.fetchrow("SELECT mood, mood_max FROM users WHERE id = $1", user_id)
        if not row:
            return
        new_mood = min(row["mood"] + amount, row["mood_max"])
        await conn.execute("UPDATE users SET mood = $1 WHERE id = $2", new_mood, user_id)

    async def maybe_apply_social_buff(self, conn, user_id: int):
        if random.random() < 0.20:
            await conn.execute("""
                INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                VALUES ($1, 8, 120, 120, NOW())
                ON CONFLICT (user_id, effect_id)
                DO UPDATE SET duration = 120, ticks = 120, applied_at = NOW()
            """, user_id)

    async def fetch_gif(self, query: str) -> str | None:
        giphy_api_key = os.getenv("GIPHY_API_KEY")
        if not giphy_api_key:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.giphy.com/v1/gifs/search",
                    params={"api_key": giphy_api_key, "q": query, "limit": 50, "rating": "pg"}
                ) as resp:
                    data = await resp.json()
                    gifs = data.get("data", [])
                    if gifs:
                        return random.choice(gifs)["images"]["original"]["url"]
        except Exception as e:
            logger.exception("Unhandled error in RPG_MISC", exc_info=e)
        return None

    # =========================
    # Mood Interaction Commands
    # =========================
    @commands.hybrid_command(description="Hug a user and gain some mood!")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def hug(self, ctx: commands.Context, target: discord.Member):
        if ctx.interaction:
            await ctx.defer()
        
        if target.id == ctx.author.id:
            msg = await tr("Error. Invalid target. Self-interaction not permitted.", ctx)
            return await ctx.reply(msg, ephemeral=True)

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        is_family, relationship_type = await self.check_family_relationship(ctx.author.id, target.id)
        
        async with self.bot.db.acquire() as conn:
            if is_family:
                await self.add_mood(conn, ctx.author.id, 8)
                await self.add_mood(conn, target.id, 8)
                mood_text = "+8 (both users) - Family bonus!"
                gif_query = "family hug warm"
            else:
                await self.add_mood(conn, ctx.author.id, 5)
                await self.add_mood(conn, target.id, 5)
                mood_text = "+5 (both users)"
                gif_query = "hug"
            
            await self.maybe_apply_social_buff(conn, ctx.author.id)

        gif_url = await self.fetch_gif(gif_query)
        translations = await translate_bulk([
            "Social Interaction Complete",
            "Action",
            "Initiator", 
            "Target",
            "Mood",
            "Status",
            "Interaction logged"
        ], ctx)
        
        embed = discord.Embed(
            title=translations[0],
            description=f"{translations[1]}: Hug\n{translations[2]}: {ctx.author.mention}\n{translations[3]}: {target.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name=translations[4], value=mood_text, inline=True)
        embed.add_field(name=translations[5], value=translations[6], inline=True)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.reply(content=target.mention, embed=embed)

    @commands.hybrid_command(description="Kiss a user and gain some mood!")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def kiss(self, ctx: commands.Context, target: discord.Member):
        if ctx.interaction:
            await ctx.defer()
        
        if target.id == ctx.author.id:
            msg = await tr("Error: Invalid target. Self-interaction not permitted.", ctx)
            return await ctx.reply(msg)

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        is_family, relationship_type = await self.check_family_relationship(ctx.author.id, target.id)
        
        async with self.bot.db.acquire() as conn:
            if is_family and relationship_type == "partner":
                await self.add_mood(conn, ctx.author.id, 10)
                await self.add_mood(conn, target.id, 10)
                mood_text = "+10 (both users) - Partner bonus!"
                gif_query = "romantic kiss couple"
            elif is_family:
                await self.add_mood(conn, ctx.author.id, 6)
                await self.add_mood(conn, target.id, 6)
                mood_text = "+6 (both users) - Family bonus!"
                gif_query = "family kiss cheek"
            else:
                await self.add_mood(conn, ctx.author.id, 5)
                await self.add_mood(conn, target.id, 5)
                mood_text = "+5 (both users)"
                gif_query = "anime kiss"
            
            await self.maybe_apply_social_buff(conn, ctx.author.id)

        gif_url = await self.fetch_gif(gif_query)
        translations = await translate_bulk([
            "Social Interaction Complete",
            "Action",
            "Initiator",
            "Target",
            "Mood",
            "Status",
            "Interaction logged"
        ], ctx)
        
        embed = discord.Embed(
            title=translations[0],
            description=f"{translations[1]}: Kiss\n{translations[2]}: {ctx.author.mention}\n{translations[3]}: {target.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name=translations[4], value=mood_text, inline=True)
        embed.add_field(name=translations[5], value=translations[6], inline=True)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.reply(content=target.mention, embed=embed)

    @commands.hybrid_command(description="Salute someone to show respect!")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def salute(self, ctx: commands.Context, target: discord.Member):
        if ctx.interaction:
            await ctx.defer()
        
        if target.id == ctx.author.id:
            msg = await tr("Error: Invalid target. Self-interaction not permitted.", ctx)
            return await ctx.reply(msg)

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        async with self.bot.db.acquire() as conn:
            await self.add_mood(conn, ctx.author.id, 5)
            await self.add_mood(conn, target.id, 5)
            
            await self.maybe_apply_social_buff(conn, ctx.author.id)

        gif_url = await self.fetch_gif("respectful salute")
        translations = await translate_bulk([
            "Social Interaction Complete",
            "Action",
            "Initiator",
            "Target",
            "Mood",
            "Status",
            "Respect acknowledged"
        ], ctx)
        
        embed = discord.Embed(
            title=translations[0],
            description=f"{translations[1]}: Salute\n{translations[2]}: {ctx.author.mention}\n{translations[3]}: {target.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name=translations[4], value="+5 (both users)", inline=True)
        embed.add_field(name=translations[5], value=translations[6], inline=True)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.reply(content=target.mention, embed=embed)

    @commands.hybrid_command(description="Pat a user and gain some mood!")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def pat(self, ctx: commands.Context, target: discord.Member):
        if ctx.interaction:
            await ctx.defer()
        
        if target.id == ctx.author.id:
            msg = await tr("Error: Invalid target. External social interaction recommended.", ctx)
            return await ctx.reply(msg, ephemeral=True)

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        
        is_family, relationship_type = await self.check_family_relationship(ctx.author.id, target.id)
        
        async with self.bot.db.acquire() as conn:
            if is_family:
                await self.add_mood(conn, ctx.author.id, 7)
                await self.add_mood(conn, target.id, 7)
                mood_text = "+7 (both users) - Family bonus!"
                gif_query = "family head pat caring"
            else:
                await self.add_mood(conn, ctx.author.id, 5)
                await self.add_mood(conn, target.id, 5)
                mood_text = "+5 (both users)"
                gif_query = "head pat"
            
            await self.maybe_apply_social_buff(conn, ctx.author.id)

        gif_url = await self.fetch_gif(gif_query)
        translations = await translate_bulk([
            "Social Interaction Complete",
            "Action",
            "Initiator",
            "Target",
            "Mood",
            "Status",
            "Interaction logged"
        ], ctx)
        
        embed = discord.Embed(
            title=translations[0],
            description=f"{translations[1]}: Pat\n{translations[2]}: {ctx.author.mention}\n{translations[3]}: {target.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name=translations[4], value=mood_text, inline=True)
        embed.add_field(name=translations[5], value=translations[6], inline=True)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.reply(content=target.mention, embed=embed)

    @commands.hybrid_command(description="Slap a user!")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def slap(self, ctx: commands.Context, target: discord.Member):
        if ctx.interaction:
            await ctx.defer()
        
        if target.id == ctx.author.id:
            msg = await tr("Error: Invalid target. Self-harm prevention protocol active.", ctx)
            return await ctx.reply(msg, ephemeral=True)

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        async with self.bot.db.acquire() as conn:
            await self.add_mood(conn, ctx.author.id, 3)
            

        gif_url = await self.fetch_gif("anime slap")
        translations = await translate_bulk([
            "Social Interaction Complete",
            "Action",
            "Initiator",
            "Target",
            "Mood",
            "Status",
            "Hostile action logged"
        ], ctx)
        
        embed = discord.Embed(
            title=translations[0],
            description=f"{translations[1]}: Slap\n{translations[2]}: {ctx.author.mention}\n{translations[3]}: {target.mention}",
            color=discord.Color.red()
        )
        embed.add_field(name=translations[4], value="+3 (initiator)", inline=True)
        embed.add_field(name=translations[5], value=translations[6], inline=True)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.reply(content=target.mention, embed=embed)

    # =========================
    # Rob Command 
    # =========================
    @commands.hybrid_command(description="Rob another user!")
    @commands.cooldown(1, 1800, commands.BucketType.user)
    async def rob(self, ctx: commands.Context, target: discord.Member, 
                  mode: Literal["quick", "normal", "careful"] = "normal"):
        if ctx.interaction:
            await ctx.defer()
        
        if target.id == ctx.author.id:
            msg = await tr("Error. Invalid target. Self-robbery not permitted.", ctx)
            return await ctx.reply(msg)

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        mode_config = {
            "quick": {"energy": 5, "success": 0.5, "multiplier": 0.2},
            "normal": {"energy": 10, "success": 0.65, "multiplier": 0.4},
            "careful": {"energy": 15, "success": 0.8, "multiplier": 0.6},
        }
        config = mode_config[mode]

        async with self.bot.db.acquire() as conn:
            user_row = await conn.fetchrow(
                "SELECT coins, energy, mood, mood_max FROM users WHERE id = $1", ctx.author.id
            )
            target_row = await conn.fetchrow("SELECT coins FROM users WHERE id = $1", target.id)
            rob_allowed = await conn.fetchval("SELECT allow_rob FROM guild_config WHERE guild_id = $1", ctx.guild.id)
            # Check if target has been active in this guild recently
            target_activity = user_current_guild.get(target.id)
            target_is_here = False
            if target_activity:
                guild_id, last_seen = target_activity
                if guild_id == ctx.guild.id and datetime.now() - last_seen < ACTIVITY_TIMEOUT:
                    target_is_here = True
            
            if not target_is_here:
                title = await tr("Error. Target unavailable", ctx)
                desc = await tr("Target has not been active in this server recently. Action denied. Target out of range.", ctx)
                return await ctx.reply(embed=discord.Embed(
                    title=title,
                    description=desc,
                    color=discord.Color.red()
                ), ephemeral=True)
            if not rob_allowed:
                title = await tr("Error. Action prohibited", ctx)
                desc = await tr("Robbery disabled in server configuration. Action denied.", ctx)
                return await ctx.reply(embed=discord.Embed(
                    title=title,
                    description=desc,
                    color=discord.Color.red()
                ), ephemeral=True)
            # check rob protection
            target_effect = await conn.fetchrow("""
                SELECT user_effects.icon, user_effects.name
                FROM current_effects
                INNER JOIN user_effects ON current_effects.effect_id = user_effects.id
                WHERE current_effects.user_id = $1 AND current_effects.effect_id = $2
            """, target.id, EffectID.ROB_PROTECT)

            if target_effect:
                return await ctx.reply(embed=discord.Embed(
                    title=f"{target_effect['icon']} {target_effect['name']}",
                    description=f"{target.mention}'s wallet is under protection. You can’t rob them!",
                    color=discord.Color.blue()
                ))

            if user_row["energy"] < config["energy"]:
                return await ctx.reply(embed=discord.Embed(
                    title="Warning. Energy insufficient",
                    description=f"Minimum {config['energy']} required. Current level {user_row['energy']}. Rest or consume energy items.",
                    color=discord.Color.red()
                ), ephemeral=True)

            # Mood-based success tweak
            success_chance = config["success"]
            if user_row["mood"] >= 100:
                success_chance += 0.1
            elif user_row["mood"] < 20:
                success_chance -= 0.1

            # Deduct energy
            await conn.execute("UPDATE users SET energy = energy - $1 WHERE id = $2", config["energy"], ctx.author.id)

            if target_row["coins"] <= 0:
                await conn.execute("UPDATE users SET mood = GREATEST(mood - 5, 0) WHERE id = $1", ctx.author.id)
                return await ctx.reply(embed=discord.Embed(
                    title="Robbery failed",
                    description=f"Target {target.mention}. No funds detected. Mood decreased by five.",
                    color=discord.Color.red()
                ).set_image(url="https://media.tenor.com/Mv43x3PXV7oAAAAM/dh9511dh-empty-wallet.gif"))

            if random.random() < success_chance:
                amount = max(1, int(target_row["coins"] * config["multiplier"]))
                await conn.execute("UPDATE users SET coins = coins - $1 WHERE id = $2", amount, target.id)
                await conn.execute("UPDATE users SET coins = coins + $1, mood = LEAST(mood + 5, mood_max) WHERE id = $2", amount, ctx.author.id)

                embed = discord.Embed(
                    title="Robbery successful",
                    description=f"Target {target.mention}. Amount stolen {amount} coins. Mode {mode}.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Energy", value=f"Decreased by {config['energy']}", inline=True)
                embed.add_field(name="Mood", value="Increased by five", inline=True)
                embed.add_field(name="Status", value="Operation complete", inline=False)
                return await ctx.reply(embed=embed, ephemeral=True)
            else:
                await conn.execute("UPDATE users SET mood = GREATEST(mood - 3, 0) WHERE id = $1", ctx.author.id)
                embed = discord.Embed(
                    title="Robbery failed",
                    description=f"Initiator {ctx.author.mention}. Target {target.mention}. Mode {mode}.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Energy", value=f"Decreased by {config['energy']}", inline=True)
                embed.add_field(name="Mood", value="Decreased by three", inline=True)
                embed.add_field(name="Status", value="Target detected intrusion", inline=False)
                return await ctx.reply(content=target.mention, embed=embed)

 
    @commands.hybrid_command(description="Rest to regain energy.")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def rest(self, ctx: commands.Context):
        if ctx.interaction:
            await ctx.defer()
        
        user_id = ctx.author.id
        await ensure_user(self.bot.db, user_id)

        async with self.bot.db.acquire() as conn:
            effect_row = await conn.fetchrow(
                "SELECT icon, name FROM user_effects WHERE id = $1", EffectID.REST
            )
            if not effect_row:
                msg = await tr("Resting effect not found! ERROR", ctx)
                return await ctx.reply(msg)

            await conn.execute("""
                INSERT INTO current_effects (user_id, effect_id, duration, ticks)
                VALUES ($1, $2, $3, $4)
            """, user_id, EffectID.REST, 1000000, 1000000)

            translations = await translate_bulk([
                "Applied",
                "User",
                "Status",
                "Resting",
                "Energy regeneration",
                "Note: Any activity will cancel rest mode"
            ], ctx)
            
            embed = discord.Embed(
                title=f"{effect_row['icon']} {effect_row['name']} {translations[0]}",
                description=f"{translations[1]}: {ctx.author.mention}\n{translations[2]}: {translations[3]}\n{translations[4]}: Active",
                color=discord.Color.blue()
            )
            embed.set_footer(text=translations[5])

            await ctx.reply(embed=embed)

    # =========================
    # Error Handler
    # =========================
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            try:
                user_id = ctx.author.id if ctx.author else 0
                msg = await tr(f"Error: Cooldown active. Retry in {round(error.retry_after, 1)} seconds.", user_id)
                if ctx.interaction and ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(msg, ephemeral=True)
                else:
                    await ctx.reply(msg, ephemeral=True)
            except discord.errors.NotFound:
                pass
            except Exception as e:
                logger.exception("Unhandled error in RPG_MISC", exc_info=e)
            return
        logger.exception("Unhandled error in RPG_MISC", exc_info=error)
    # ---------------- listener: cancel resting on message ----------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # don't react to bots or the bot itself
        if message.author.bot:
            return

        # Track user activity with timestamp
        user_current_guild[message.author.id] = (message.guild.id, datetime.now())
        # skip if message starts with prefix (optional): prevents cancelling when calling prefix commands
        try:
            prefixes = getattr(self.bot, "command_prefix", None)
            if isinstance(prefixes, str) and message.content.startswith(prefixes):
                return
            # if prefix is a list, check any
            if isinstance(prefixes, (list, tuple)):
                for p in prefixes:
                    if isinstance(p, str) and message.content.startswith(p):
                        return
        except Exception:
            # ignore prefix errors
            pass

        user_id = message.author.id
        try:
            async with self.bot.db.acquire() as conn:
                effect_row = await conn.fetchrow(
                    """SELECT ue.icon, ue.name
                       FROM current_effects ce
                       JOIN user_effects ue ON ce.effect_id = ue.id
                       WHERE ce.user_id = $1 AND ce.effect_id = $2""",
                    user_id, EffectID.REST
                )

                if not effect_row:
                    return  # not resting

                await conn.execute("DELETE FROM current_effects WHERE user_id = $1 AND effect_id = $2", user_id, EffectID.REST)

                icon = effect_row.get("icon") or ""
                name = effect_row.get("name") or "Resting"

                translations = await translate_bulk([
                    "Removed",
                    "User",
                    "Status",
                    "Active",
                    "Rest mode",
                    "Cancelled"
                ], user_id)
                
                embed = discord.Embed(
                    title=f"{icon} {name} {translations[0]}",
                    description=f"{translations[1]}: {message.author.mention}\n{translations[2]}: {translations[3]}\n{translations[4]}: {translations[5]}",
                    color=discord.Color.orange()
                )

                # send to the same channel the user typed in
                try:
                    await message.channel.send(embed=embed)
                except Exception:
                    # if channel can't be written to, try DM
                    try:
                        await message.author.send(embed=embed)
                    except Exception:
                        pass

                logger.info("Resting effect removed for user_id=%s", message.author.id)

        except Exception:
            traceback.print_exc()
            # don't raise — keep bot healthy
async def setup(bot):
    await bot.add_cog(RPG_MISC(bot))
