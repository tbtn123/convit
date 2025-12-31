import discord
from discord.ext import commands
import datetime
import random

from utils.db_helpers import is_item_req_valid, ensure_inventory, add_item, check_has_user_upvoted
from utils.singleton import BASE_TICK

MAX_FARM_SLOTS = 5


def make_bar(percent: float, length: int = 20) -> str:
    filled = int(length * percent)
    empty = length - filled
    return "[" + "█" * filled + "░" * empty + "]"


class Farm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="farm", with_app_command=True, description="Farm commands")
    async def farm(self, ctx, member: discord.Member = None):
        user = member or ctx.author
        async with self.bot.db.acquire() as conn:
            farms = await conn.fetch(
                "SELECT * FROM farm_sessions WHERE user_id = $1 ORDER BY session_id", user.id
            )

            # If no farms, show a friendly message
            if not farms:
                embed = discord.Embed(
                    title="Farm Info",
                    description=("You have no active farms." if user == ctx.author else f"{user.display_name} has no active farms."),
                    color=discord.Color.red(),
                )
                return await ctx.send(embed=embed)

            # Build paginated pages (4 farms per page)
            pages = []
            per_page = 4
            for i in range(0, len(farms), per_page):
                chunk = farms[i:i+per_page]
                embed = discord.Embed(title=f"{user.display_name}'s Farm ({i//per_page + 1}/{(len(farms)-1)//per_page + 1})", color=discord.Color.green())
                for farm in chunk:
                    farm_rewards = await conn.fetch("SELECT * FROM farm_info WHERE farm_id = $1", farm["farm_id"])
                    input_item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", farm_rewards[0]["input_id"]) if farm_rewards else None

                    end_time = farm["finished_at"]
                    start_time = farm["created_at"]

                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=datetime.timezone.utc)
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=datetime.timezone.utc)

                    now = datetime.datetime.now(datetime.timezone.utc)
                    total = (end_time - start_time).total_seconds()
                    elapsed = (now - start_time).total_seconds()
                    percent = max(0, min(elapsed / total, 1)) if total > 0 else 1

                    bar = make_bar(percent)
                    remaining = int((end_time - now).total_seconds()) if end_time > now else 0

                    rewards_str = " + ".join([
                        f"{await self._get_item_name_icon(conn, reward['output_id'])}"
                        for reward in farm_rewards
                    ]) if farm_rewards else ""

                    desc = (
                        f"{input_item['name'] if input_item else 'Unknown'} => {rewards_str}\n"
                        f"Progress: {bar} ({int(percent * 100)}%)\n"
                        + (f"Finishes <t:{int(end_time.timestamp())}:R>" if remaining > 0 else "Ready to collect")
                    )

                    embed.add_field(name=f"Farm #{farm['session_id']}", value=desc, inline=False)

                pages.append(embed)

            
            if user == ctx.author:
                current_farms = await conn.fetchval("SELECT COUNT(*) FROM farm_sessions WHERE user_id = $1", user.id)
                is_user_upvoted = await check_has_user_upvoted(user.id)
                max_slots = 10 if is_user_upvoted else MAX_FARM_SLOTS
                pages[0].set_footer(text=f"Slots: {current_farms}/{max_slots}")

       
            if len(pages) == 1:
                view = InfoActionView(self, user.id, show_plant=True)
                await ctx.send(embed=pages[0], view=view)
                return

            view = FarmPagesView(self, user.id, pages)
            await ctx.send(embed=pages[0], view=view)

    @farm.command(name="info")
    async def info(self, ctx):
        
        async with self.bot.db.acquire() as conn:
            await ensure_inventory(self.bot.db, ctx.author.id)
            current_farms = await conn.fetchval("SELECT COUNT(*) FROM farm_sessions WHERE user_id = $1", ctx.author.id)
            is_user_upvoted = await check_has_user_upvoted(ctx.author.id)
            max_slots = 10 if is_user_upvoted else MAX_FARM_SLOTS

        desc = (
            f"Slots: {current_farms}/{max_slots}\n\n"
            ".farm - View your active farms and progress\n"
            "/farm info - Show this help message (also available as prefix)\n"
            ".farm plant <item> - Plant an item/seed (consumes 1)\n"
            ".farm harvest - Harvest all ready farms and collect rewards\n"
            
        )

        embed = discord.Embed(title="Farm Commands", description=desc, color=discord.Color.green())
        view = InfoActionView(self, ctx.author.id, show_plant=True)
        await ctx.send(embed=embed, view=view)

    async def _get_item_name_icon(self, conn, item_id):
        item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
        if not item:
            return f"Unknown({item_id})"
        return f"{item.get('icon', '')} {item['name']}"

    async def _collect_finished_for_user(self, conn, user_id: int):
     
        now = datetime.datetime.now(datetime.timezone.utc)
        farms = await conn.fetch("SELECT * FROM farm_sessions WHERE user_id = $1 ORDER BY session_id", user_id)
        finished = [
            f for f in farms
            if (f["finished_at"].replace(tzinfo=datetime.timezone.utc)
                if f["finished_at"].tzinfo is None else f["finished_at"]) <= now
        ]

        if not finished:
            return []

        totals = {}
        labels = {}
        for farm in finished:
            farm_rewards = await conn.fetch("SELECT * FROM farm_info WHERE farm_id = $1", farm["farm_id"])
            for reward in farm_rewards:
                amount = random.randint(max(1, reward["output_amount"] // 2), reward["output_amount"])
                await add_item(self.bot.db, user_id, reward["output_id"], amount)
                item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", reward["output_id"])
                oid = reward["output_id"]
                totals[oid] = totals.get(oid, 0) + amount
                labels[oid] = f"{item.get('icon', '')} {item['name']}"
            await conn.execute("DELETE FROM farm_sessions WHERE session_id = $1", farm["session_id"])

        total_collected = [f"{totals[oid]} x {labels[oid]}" for oid in sorted(totals.keys(), key=lambda k: labels[k])]
        return total_collected

    @farm.command(name="harvest", aliases=["collect"])
    async def farm_harvest(self, ctx):
        await ensure_inventory(self.bot.db, ctx.author.id)
        async with self.bot.db.acquire() as conn:
            collected = await self._collect_finished_for_user(conn, ctx.author.id)

        if not collected:
            embed = discord.Embed(title="Not Ready", description="No farms are ready to harvest yet.", color=discord.Color.orange())
            return await ctx.send(embed=embed)

        embed = discord.Embed(title="Harvest Complete", description=("**You collected:**\n" + "\n".join(collected)), color=discord.Color.gold())
        await ctx.send(embed=embed)


    @farm.command(name="plant")
    async def farm_plant(self, ctx, *, item_query: str):
        """Plant an item (prefix or slash)."""
        try:
            async with self.bot.db.acquire() as conn:
                current_farms = await conn.fetchval(
                    "SELECT COUNT(*) FROM farm_sessions WHERE user_id = $1", ctx.author.id
                )

                is_user_upvoted = await check_has_user_upvoted(ctx.author.id)
                max_slots = 10 if is_user_upvoted else MAX_FARM_SLOTS

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
                    title="Seed Planted",
                    description=f"You planted **{item['name']}**!\nIt will finish <t:{int(end_time.timestamp())}:R>.",
                    color=discord.Color.green(),
                )
                return await ctx.send(embed=embed)
        except Exception as e:
            return await ctx.send(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()))

    @farm.command(name="wiki", description="List plantable items and their possible outputs")
    async def farm_wiki(self, ctx):
        """Show list of plantable items and their outputs in a paginated embed."""
        async with self.bot.db.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM farm_info ORDER BY farm_id")

            if not rows:
                return await ctx.send(embed=discord.Embed(title="Farm Wiki", description="No farm data available.", color=discord.Color.red()))

       
            groups = {}
            for r in rows:
                groups.setdefault(r['farm_id'], []).append(r)

            pages = []
            for farm_id, rewards in groups.items():
                input_item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", rewards[0]['input_id'])
                lines = []
                for reward in rewards:
                    out_item = await conn.fetchrow("SELECT * FROM items WHERE id = $1", reward['output_id'])
                    lines.append(f"{reward['output_amount']} x {out_item.get('icon','')} {out_item['name']}")

                embed = discord.Embed(title=f"Farm ID {farm_id}: {input_item.get('icon','')} {input_item['name']}", description="\n".join(lines), color=discord.Color.blurple())
                pages.append(embed)

            if not pages:
                return await ctx.send(embed=discord.Embed(title="Farm Wiki", description="No farm info found.", color=discord.Color.red()))

            if len(pages) == 1:
                return await ctx.send(embed=pages[0])

            view = FarmPagesView(self, ctx.author.id, pages)
            await ctx.send(embed=pages[0], view=view)



class FarmPagesView(discord.ui.View):
    def __init__(self, cog, user_id: int, pages: list):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.pages = pages
        self.index = 0

        self.prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This pager is not for you.", ephemeral=True)
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This pager is not for you.", ephemeral=True)
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)


class InfoActionView(discord.ui.View):
    def __init__(self, cog, user_id: int, show_plant: bool = True):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.show_plant = show_plant

        self.harvest_button = discord.ui.Button(label="Harvest", style=discord.ButtonStyle.primary)
        self.harvest_button.callback = self.on_harvest
        self.add_item(self.harvest_button)

        if self.show_plant:
            self.plant_button = discord.ui.Button(label="Plant", style=discord.ButtonStyle.secondary)
            self.plant_button.callback = self.on_plant
            self.add_item(self.plant_button)

    async def on_harvest(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This action is not for you.", ephemeral=True)
        await interaction.response.defer()
        async with self.cog.bot.db.acquire() as conn:
            collected = await self.cog._collect_finished_for_user(conn, interaction.user.id)
        if not collected:
            return await interaction.followup.send(embed=discord.Embed(title="Not Ready", description="No farms are ready to harvest yet.", color=discord.Color.orange()), ephemeral=True)
        return await interaction.followup.send(embed=discord.Embed(title="Harvest Complete", description=("**You collected:**\n" + "\n".join(collected)), color=discord.Color.gold()), ephemeral=True)

    async def on_plant(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This action is not for you.", ephemeral=True)
        # Open a simple modal to get item name
        await interaction.response.send_modal(PlantModal(self.cog))


class PlantModal(discord.ui.Modal, title="Plant Seed"):
    item_name = discord.ui.TextInput(label="Item to plant", placeholder="Enter item name or partial", required=True, max_length=100)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        item_query = self.item_name.value.strip()
        await interaction.response.defer()
       
        try:
            async with self.cog.bot.db.acquire() as conn:
    
                current_farms = await conn.fetchval("SELECT COUNT(*) FROM farm_sessions WHERE user_id = $1", interaction.user.id)
                is_user_upvoted = await check_has_user_upvoted(interaction.user.id)
                max_slots = 10 if is_user_upvoted else MAX_FARM_SLOTS

                if current_farms >= max_slots:
                    return await interaction.followup.send(embed=discord.Embed(title="Farm Slots Full", description=f"You already have {max_slots} active farms.", color=discord.Color.orange()), ephemeral=True)

                item = await conn.fetchrow("SELECT * FROM items WHERE name ILIKE $1", f"%{item_query}%")
                if not item:
                    return await interaction.followup.send(embed=discord.Embed(title="Item Not Found", description=f"No item matches '{item_query}'.", color=discord.Color.red()), ephemeral=True)

                farm_info = await conn.fetchrow("SELECT * FROM farm_info WHERE input_id = $1", item["id"])
                if not farm_info:
                    return await interaction.followup.send(embed=discord.Embed(title="Not Plantable", description=f"You cannot plant {item['name']}.", color=discord.Color.red()), ephemeral=True)

                valid = await is_item_req_valid(self.cog.bot.db, interaction.user.id, item["id"], 1)
                if not valid:
                    return await interaction.followup.send(embed=discord.Embed(title="Insufficient Items", description=f"You don't have any {item['name']} to plant.", color=discord.Color.red()), ephemeral=True)

                duration = farm_info["duration"]
                start_time = datetime.datetime.now(datetime.timezone.utc)
                end_time = start_time + datetime.timedelta(seconds=duration * BASE_TICK)

                await conn.execute(
                    """
                    INSERT INTO farm_sessions (user_id, farm_id, created_at, duration, finished_at)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    interaction.user.id,
                    farm_info["farm_id"],
                    start_time,
                    duration,
                    end_time,
                )

                await add_item(self.cog.bot.db, interaction.user.id, item["id"], -1)

                return await interaction.followup.send(embed=discord.Embed(title="Seed Planted", description=f"You planted **{item['name']}**!\nIt will finish <t:{int(end_time.timestamp())}:R>.", color=discord.Color.green()), ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Farm(bot))
