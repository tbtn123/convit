import discord
from discord.ext import commands
from datetime import datetime, timedelta
import random
import traceback
from typing import Optional, Any, Dict

from utils.db_helpers import ensure_inventory, ensure_user
from utils.parser import parse_amount, AmountParseError


class TradeQuestModal(discord.ui.Modal, title="Accept Trade Quest"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

        self.quest_id = discord.ui.TextInput(
            label="Quest ID",
            placeholder="Enter the Quest ID you want to accept (e.g. 123)",
            required=True
        )
        self.add_item(self.quest_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            quest_id = int(self.quest_id.value.strip())
        except ValueError:
            return await interaction.followup.send("Invalid Quest ID.", ephemeral=True)

        result = await self.cog.process_trade_quest(interaction.user.id, quest_id)

        if isinstance(result, str):
            embed = discord.Embed(
                title="Trade Failed ",
                description=result,
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
        else:
            embed = discord.Embed(
                title="Trade Complete ",
                description=result["message"],
                color=discord.Color.green() if result["success"] else discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            if result["success"]:
                embed.add_field(name="Payout", value=f"**{result['payout']}** coins", inline=True)

        embed.set_footer(text=f"Quest #{quest_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)


class TradeQuestView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Accept Quest", style=discord.ButtonStyle.primary)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TradeQuestModal(self.cog))


class TradeQuests(commands.GroupCog, name="trade-quest"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="show", description="Show available trade quests")
    async def show_quests(self, ctx: commands.Context, page: int = 1):
        await ctx.defer()
        if page < 1:
            return await ctx.send("Page must be >= 1.")
        limit = 10
        offset = (page - 1) * limit
        try:
            async with self.bot.db.acquire() as conn:
                total_quests = await conn.fetchval("SELECT COUNT(*) FROM trade_quests WHERE expires_at > NOW()")
                rows = await conn.fetch("""
                    SELECT t.id, t.trust_level, i.name, i.icon, t.item_amount, t.payout, t.expires_at
                    FROM trade_quests t
                    JOIN items i ON i.id = t.item_id
                    WHERE t.expires_at > NOW()
                    ORDER BY t.created_at DESC
                    LIMIT $1 OFFSET $2
                """, limit, offset)

            if not rows:
                return await ctx.send("No active trade quests available.")

            embed = discord.Embed(
                title=f"🛒 Trade Quests (Page {page})",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow(),
                description="NPCs are looking to buy your items! Click **Accept Quest** and enter the Quest ID."
            )

            for row in rows:
                trust_text = self.get_trust_description(row["trust_level"])
                scam_chance = (10 - row["trust_level"]) * 10
                icon = row["icon"] or ":package:"
                embed.add_field(
                    name=f"{icon} {row['name']} x{row['item_amount']}",
                    value=(
                        f"**Quest #{row['id']}**\n"
                        f"Trust: **{trust_text}** ({scam_chance}% scam risk)\n"
                        f"Payout: **{row['payout']}** coins"
                    ),
                    inline=False
                )

            max_page = max(1, (total_quests + limit - 1) // limit)
            embed.set_footer(text=f"Page {page}/{max_page} • Total Active Quests: {total_quests}")
            view = TradeQuestView(self)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await ctx.send(f"Error: {e}")

    def get_trust_description(self, level):
        descriptions = {
            1: "Very Suspicious",
            2: "Suspicious",
            3: "Untrustworthy",
            4: "Dubious",
            5: "Neutral",
            6: "Somewhat Trustworthy",
            7: "Trustworthy",
            8: "Very Trustworthy",
            9: "Extremely Trustworthy"
        }
        return descriptions.get(level, "Unknown")

    @commands.command(name="gen-trade-quests", aliases=['gtq'])
    @commands.is_owner()
    async def generate_quests(self, ctx: commands.Context, count: int = 5):
        await ctx.defer()
        if count < 1 or count > 20:
            return await ctx.send("Count must be between 1 and 20.")

        generated = 0
        failed = 0
        try:
            async with self.bot.db.acquire() as conn:
                total_items = await conn.fetchval("SELECT COUNT(*) FROM items WHERE id > 0")
                if total_items == 0:
                    return await ctx.send("No items found in database!")

                for _ in range(count):
                    result = await self.generate_single_quest()
                    if result:
                        generated += 1
                    else:
                        failed += 1

            await ctx.send(f"Generated {generated} new trade quests. Failed: {failed}. Total items in DB: {total_items}")
        except Exception as e:
            traceback.print_exc()
            await ctx.send(f"Error generating quests: {e}")

    async def generate_single_quest(self):
        try:
            async with self.bot.db.acquire() as conn:
                tradeable_items = await conn.fetch("""
                    SELECT id, name FROM items
                    WHERE id > 0
                    ORDER BY RANDOM() LIMIT 1
                """)

                if not tradeable_items:
                    return False

                item = tradeable_items[0]

                trust_weights = [0.15, 0.15, 0.15, 0.15, 0.15, 0.10, 0.05, 0.03, 0.02]
                trust_level = random.choices(range(1, 10), weights=trust_weights)[0]

                amount = random.randint(1, 5)
                base_value = await self.get_item_base_value(conn, item['id'])
                payout = int(base_value * amount * (0.6 + trust_level * 0.04))

                timeout_minutes = 10 + (trust_level - 1) * 2

                await conn.execute("""
                    INSERT INTO trade_quests (trust_level, item_id, item_amount, payout, expires_at)
                    VALUES ($1, $2, $3, $4, NOW() + INTERVAL '1 minute' * $5)
                """, trust_level, item['id'], amount, payout, timeout_minutes)

                return True
        except Exception:
            return False

    async def get_item_base_value(self, conn, item_id):
        market_prices = await conn.fetch("""
            SELECT AVG(price) as avg_price FROM trades
            WHERE item_id = $1 AND created_at > NOW() - INTERVAL '24 hours'
            GROUP BY item_id
        """, item_id)

        if market_prices:
            return int(market_prices[0]['avg_price'] or 100)

        default_values = {
            3: 50, 10: 80, 15: 120, 18: 25, 19: 30, 26: 500
        }
        return default_values.get(item_id, 100)

    async def process_trade_quest(self, user_id: int, quest_id: int) -> Any:
        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)

        try:
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    quest = await conn.fetchrow("""
                        SELECT * FROM trade_quests
                        WHERE id = $1 AND expires_at > NOW()
                        FOR UPDATE
                    """, quest_id)

                    if not quest:
                        return "Quest not found or expired."

                    inv_quantity = await conn.fetchval("""
                        SELECT quantity FROM inventory
                        WHERE id = $1 AND item_id = $2
                    """, user_id, quest['item_id'])

                    if not inv_quantity or inv_quantity < quest['item_amount']:
                        return "You don't have enough items for this quest."

                    scam_chance = (10 - quest['trust_level']) / 10.0
                    is_scam = random.random() < scam_chance

                    await conn.execute("""
                        UPDATE inventory SET quantity = quantity - $1
                        WHERE id = $2 AND item_id = $3
                    """, quest['item_amount'], user_id, quest['item_id'])

                    await conn.execute("DELETE FROM trade_quests WHERE id = $1", quest_id)

                    if is_scam:
                        return {
                            "success": False,
                            "message": f"SCAM! The NPC took your items and disappeared.\nLost **{quest['item_amount']}x** items.",
                            "payout": 0
                        }
                    else:
                        await conn.execute("UPDATE users SET coins = coins + $1 WHERE id = $2", quest['payout'], user_id)
                        return {
                            "success": True,
                            "message": f"Trade successful! The NPC paid you **{quest['payout']}** coins.",
                            "payout": quest['payout']
                        }

        except Exception as e:
            traceback.print_exc()
            return "An error occurred while processing the trade."


async def setup(bot):
    await bot.add_cog(TradeQuests(bot))
