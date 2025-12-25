import discord
from discord.ext import commands
import datetime
import random

from utils.db_helpers import is_item_req_valid, add_item, check_has_user_upvoted
from utils.singleton import BASE_TICK

MAX_FARM_SLOTS = 5


def make_bar(percent: float, length: int = 20) -> str:
    filled = int(length * percent)
    empty = length - filled
    return "[" + "█" * filled + "░" * empty + "]"


class Farm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="farm", invoke_without_command=True)
    async def farm(self, ctx, member: discord.Member = None):
        user = member or ctx.author
        async with self.bot.db.acquire() as conn:
            farms = await conn.fetch(
                "SELECT * FROM farm_sessions WHERE user_id = $1 ORDER BY session_id", user.id
            )
            if not farms:
                embed = discord.Embed(
                    title="Farm Info",
                    description=("You have no active farms." if user == ctx.author else f"{user.display_name} has no active farms."),
                    color=discord.Color.red(),
                )
                return await ctx.send(embed=embed)

            embed = discord.Embed(title=f"{user.display_name}'s Farm", color=discord.Color.green())
            for farm in farms:
                farm_rewards = await conn.fetch("SELECT * FROM farm_info WHERE farm_id = $1", farm["farm_id"])
                input_item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", farm_rewards[0]["input_id"])

                end_time = farm["finished_at"]
                start_time = farm["created_at"]
                duration = farm["duration"]

                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=datetime.timezone.utc)
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=datetime.timezone.utc)

                

                now = datetime.datetime.now(datetime.timezone.utc)
                total = (end_time - start_time).total_seconds()
                elapsed = (now - start_time).total_seconds()
                percent = max(0, min(elapsed / total, 1))


                bar = make_bar(percent)
                remaining = int((end_time - now).total_seconds()) if end_time > now else 0

                rewards_str = " + ".join([
                    f"{await self._get_item_name_icon(conn, reward['output_id'])}"
                    for reward in farm_rewards
                ])

                desc = (
                    f"{input_item['name']} => {rewards_str}\n"
                    f"Progress: {bar} ({int(percent * 100)}%)\n"
                    + (f"Finishes <t:{int(end_time.timestamp())}:R>" if remaining > 0 else "Ready to collect")
                )

                embed.add_field(name=f"Farm #{farm['session_id']}", value=desc, inline=False)

            await ctx.send(embed=embed)

    async def _get_item_name_icon(self, conn, item_id):
        item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
        if not item:
            return f"Unknown({item_id})"
        return f"{item.get('icon', '')} {item['name']}"

    @farm.command(name="harvest", aliases=["collect"])
    async def farm_harvest(self, ctx):
        async with self.bot.db.acquire() as conn:
            farms = await conn.fetch(
                "SELECT * FROM farm_sessions WHERE user_id = $1 ORDER BY session_id", ctx.author.id
            )
            if not farms:
                embed = discord.Embed(
                    title="No Active Farms",
                    description="You don't have any active farms.",
                    color=discord.Color.red(),
                )
                return await ctx.send(embed=embed)

            now = datetime.datetime.now(datetime.timezone.utc)
            finished = [
                f for f in farms
                if (f["finished_at"].replace(tzinfo=datetime.timezone.utc)
                    if f["finished_at"].tzinfo is None else f["finished_at"]) <= now
            ]

            if not finished:
                embed = discord.Embed(
                    title="Not Ready",
                    description="No farms are ready to harvest yet.",
                    color=discord.Color.orange(),
                )
                return await ctx.send(embed=embed)

            total_collected = []
            for farm in finished:
                farm_rewards = await conn.fetch("SELECT * FROM farm_info WHERE farm_id = $1", farm["farm_id"])
                for reward in farm_rewards:
                    amount = random.randint(max(1, reward["output_amount"] // 2), reward["output_amount"])
                    await add_item(self.bot.db, ctx.author.id, reward["output_id"], amount)
                    item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", reward["output_id"])
                    total_collected.append(f"{amount} x {item.get('icon', '')} {item['name']}")
                await conn.execute("DELETE FROM farm_sessions WHERE session_id = $1", farm["session_id"])

            embed = discord.Embed(
                title=" Harvest Complete",
                description="**You collected:**\n" + "\n".join(total_collected),
                color=discord.Color.gold(),
            )
            await ctx.send(embed=embed)


    @farm.command(name="plant")
    async def farm_plant(self, ctx, *, item_query: str):
        try:
            async with self.bot.db.acquire() as conn:
                current_farms = await conn.fetchval(
                    "SELECT COUNT(*) FROM farm_sessions WHERE user_id = $1", ctx.author.id
                )

                is_user_upvoted = await check_has_user_upvoted(ctx.author.id)
                max_slots = 10 if  is_user_upvoted else MAX_FARM_SLOTS

                if current_farms >= max_slots:
                    embed = discord.Embed(
                        title="Farm Slots Full",
                        description=f"You already have {max_slots} active farms.",
                        color=discord.Color.orange(),
                    )
                    return await ctx.send(embed=embed)

                item = await conn.fetchrow("SELECT * FROM items WHERE name ILIKE $1", f"%{item_query}%")
                if not item:
                    embed = discord.Embed(
                        title="Item Not Found",
                        description=f"No item matches '{item_query}'.",
                        color=discord.Color.red(),
                    )
                    return await ctx.send(embed=embed)

                farm_info = await conn.fetchrow("SELECT * FROM farm_info WHERE input_id = $1", item["id"])
                if not farm_info:
                    embed = discord.Embed(
                        title="Not Plantable",
                        description=f"You cannot plant {item['name']}.",
                        color=discord.Color.red(),
                    )
                    return await ctx.send(embed=embed)

                valid = await is_item_req_valid(self.bot.db, ctx.author.id, item["id"], 1)
                if not valid:
                    embed = discord.Embed(
                        title="Insufficient Items",
                        description=f"You don't have any {item['name']} to plant.",
                        color=discord.Color.red(),
                    )
                    return await ctx.send(embed=embed)

                duration = farm_info["duration"]
                start_time = datetime.datetime.now(datetime.timezone.utc)
                end_time = start_time + datetime.timedelta(seconds=duration * BASE_TICK)

                await conn.execute(
                    """
                    INSERT INTO farm_sessions (user_id, farm_id, created_at, duration, finished_at)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    ctx.author.id,
                    farm_info["farm_id"],
                    start_time,
                    duration,
                    end_time,
                )

                await add_item(self.bot.db, ctx.author.id, item["id"], -1)

                embed = discord.Embed(
                    title="\U0001F331 Seed Planted",
                    description=f"You planted **{item['name']}**!\nIt will finish <t:{int(end_time.timestamp())}:R>.",
                    color=discord.Color.green(),
                )
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()))


async def setup(bot):
    await bot.add_cog(Farm(bot))
