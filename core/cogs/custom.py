import discord
from discord.ext import commands
import urllib.parse
import matplotlib.pyplot as plt
import io
class Custom(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bulk-rename")
    @commands.has_permissions(administrator=True)
    async def bulk_name_edit(self, ctx: commands.Context, *, message: str):
        try:
            result = {}
            current_channel_id = ctx.channel.id
            later_rename = {}
            lines = message.strip().splitlines()

            for line in lines:
                if "=" not in line:
                    continue

                left, right = line.split("=", 1)
                left = left.strip()
                right = right.strip().replace(" ", "-")  # Replace spaces with hyphens

                if left.startswith("<#") and left.endswith(">"):
                    channel_id_str = left[2:-1]
                    try:
                        channel_id = int(channel_id_str)
                        channel = self.bot.get_channel(channel_id)

                        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                            if channel_id == current_channel_id:
                                later_rename[channel_id] = right
                            else:
                                result[channel_id] = right
                    except ValueError:
                        continue

            if not result and not later_rename:
                return await ctx.send("No valid channels or names were found.")

            renamed = []

            for channel_id, new_name in result.items():
                channel = self.bot.get_channel(channel_id)
                try:
                    await channel.edit(name=new_name)
                    renamed.append(f"<#{channel_id}> changed to `{new_name}` ✅")
                except Exception as e:
                    renamed.append(f"<#{channel_id}> can't be changed: `{e}` 🥀")

            summary = "\n".join(renamed) or "No channels were renamed yet."
            await ctx.send(f"Renamed. Result:\n{summary}")

            for channel_id, new_name in later_rename.items():
                channel = self.bot.get_channel(channel_id)
                try:
                    await channel.edit(name=new_name)
                    await ctx.send(f"<#{channel_id}> (current channel) changed to `{new_name}` ✅")
                except Exception as e:
                    await ctx.send(f"<#{channel_id}> (current) can't be changed: `{e}` 🥀")

        except Exception as e:
            await ctx.send(f"Error = {e}")

        print("Bulk rename completed.")

    @commands.command(name="latex")
    async def latex(self, ctx: commands.Context, *, expression: str):
        """Render LaTeX expression and return as image."""
        try:
            buf = io.BytesIO()
            plt.figure(figsize=(0.1, 0.1))
            plt.text(0.5, 0.5, f"${expression}$", fontsize=24, ha='center', va='center')
            plt.axis('off')
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=300)
            buf.seek(0)
            plt.close()

            file = discord.File(buf, filename="latex.png")
            await ctx.send(file=file)

        except Exception as e:
            await ctx.send(f"Failed to render LaTeX: `{e}`")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You must be an administrator to use this command.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if "clap" in message.content.lower():
            await message.channel.send("https://media.tenor.com/9j35QUJQEUsAAAAM/seal-clapping-property-of-mello.gif")

async def setup(bot):
    await bot.add_cog(Custom(bot))
