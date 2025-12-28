import discord
from discord.ext import commands
from discord import app_commands

class Config(commands.Cog, name="config"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="public-opt-in",
        description="Opt in or out of the global listings."
    )
    
    async def public_opt_in(self, ctx: commands.Context, opt_in: bool):
        user_id = ctx.author.id

        try:
            async with self.bot.db.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_config (user_id, public_opt_in)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET public_opt_in = $2
                """, user_id, opt_in)

            status = "Turned On" if opt_in else "Turned Off"
            embed = discord.Embed(
                title="Leaderboard Opt-In Updated",
                description=f"You have **{status}** the global sharing.",
                color=discord.Color.green()
            )
            await ctx.reply(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description="There was a problem updating your settings. Please try again later.",
                color=discord.Color.red()
            )
            await ctx.reply(embed=embed)
            raise e  

# --- SETUP ---
async def setup(bot):
    await bot.add_cog(Config(bot))
