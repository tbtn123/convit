import discord
from discord.ext import commands
from discord import app_commands
import asyncpg
from utils.db_helpers import ensure_user, ensure_inventory
from utils.economy import calculate_multiplier, format_number
class Giftcode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="redeem")
    async def redeem(self, ctx: commands.Context, code: str):
        """Redeem a gift code."""
        user_id = ctx.author.id
        await ensure_user(self.bot.db, user_id)  
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                gift = await conn.fetchrow("SELECT * FROM giftcodes WHERE code = $1", code)
                if not gift:
                    return await ctx.reply("❌ Invalid gift code.")

                # Check if user already redeemed
                exists = await conn.fetchrow(
                    "SELECT 1 FROM giftcode_users WHERE user_id=$1 AND giftcode_id=$2",
                    user_id, gift["id"]
                )
                if exists:
                    return await ctx.reply("❌ You already redeemed this code.")

                # Add reward
                await conn.execute(
                    "UPDATE users SET coins = coins + $1 WHERE id = $2",
                    gift["prize"], user_id
                )

                # Register redemption
                await conn.execute(
                    "INSERT INTO giftcode_users (user_id, giftcode_id) VALUES ($1,$2)",
                    user_id, gift["id"]
                )

                # Decrement uses
                new_uses = gift["uses"] - 1
                if new_uses <= 0:
                    await conn.execute("DELETE FROM giftcodes WHERE id=$1", gift["id"])
                    await conn.execute("DELETE FROM giftcode_users WHERE giftcode_id=$1", gift["id"])
                else:
                    await conn.execute("UPDATE giftcodes SET uses=$1 WHERE id=$2", new_uses, gift["id"])

        await ctx.reply(f"✅ Redeemed `{code}`! You received **{gift['prize']} coins**.")

async def setup(bot):
    await bot.add_cog(Giftcode(bot))
