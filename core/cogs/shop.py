import discord
from discord.ext import commands
from discord import app_commands
from utils.db_helpers import ensure_user, ensure_inventory, log_spending
import traceback
import logging
from utils.parser import parse_amount, AmountParseError  # Added for flexible amount parsing

logger = logging.getLogger(__name__)

BASE_COMM = 0.05
class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --------- AUTOCOMPLETE ---------
    async def shop_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        async with self.bot.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT i.name FROM global_shop gs
                JOIN shop_pool sp ON gs.pool_id = sp.id
                JOIN items i ON sp.item_id = i.id
                WHERE i.name ILIKE $1
                LIMIT 20
            """, f"%{current}%")
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]

    # --------- /shop ---------
    @app_commands.command(name="shop", description="Browse today's shop")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = discord.Embed(
            title="Today's Item Shop",
            description="Use `/buy <item>` to purchase.\nItems reset daily at 0:00 UTC+7.",
            color=discord.Color.gold()
        )

        try:
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT gs.pool_id, gs.price, gs.stock,
                           i.name, i.icon, i.description
                    FROM global_shop gs
                    JOIN shop_pool sp ON gs.pool_id = sp.id
                    JOIN items i ON sp.item_id = i.id
                """)
                if not rows:
                    embed.description = "Shop is empty. Try again later."
                    return await interaction.followup.send(embed=embed)

                for row in rows:
                    name = row["name"].title()
                    price = row["price"]
                    stock = row["stock"]
                    icon = row["icon"] or ""
                    desc = row["description"] or ""
                    stock_display = f"{stock} " if stock > 0 else "**[SOLD OUT]**"
                    embed.add_field(
                        name=f"{icon} {name} - {price} coins",
                        value=f"{desc}\n**Stock:** {stock_display}",
                        inline=False
                    )

                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"Error fetching shop: `{type(e).__name__}` - {e}", ephemeral=True)
            traceback.print_exc()

    # --------- /buy ---------
    @app_commands.command(name="buy", description="Buy an item from the shop (supports 'all', '50%', etc.)")
    @app_commands.describe(item="Select an item to buy", amount="Quantity to buy (supports 'all', '50%', etc.)")
    @app_commands.autocomplete(item=shop_autocomplete)
    async def buy(self, interaction: discord.Interaction, item: str, amount: str = "1"):
        await interaction.response.defer()
        user_id = interaction.user.id

        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)

        try:
            async with self.bot.db.acquire() as conn:
                # Get the item from today's shop
                row = await conn.fetchrow("""
                    SELECT gs.pool_id, gs.price, gs.stock, i.id AS item_id, i.name
                    FROM global_shop gs
                    JOIN shop_pool sp ON gs.pool_id = sp.id
                    JOIN items i ON sp.item_id = i.id
                    WHERE i.name ILIKE $1
                """, item)

                if not row:
                    return await interaction.followup.send("That item is not available in the shop.", ephemeral=True)

                item_id = row["item_id"]
                stock = row["stock"]
                price = row["price"]
                pool_id = row["pool_id"]

                if stock <= 0:
                    return await interaction.followup.send(" This item is sold out.", ephemeral=True)
                
                # Parse amount using parser utility (supports 'all', '50%', etc.)
                try:
                    parsed_amount = parse_amount(amount, stock)
                except AmountParseError as e:
                    return await interaction.followup.send(f"Invalid amount: {e}", ephemeral=True)
                
                if parsed_amount < 1:
                    return await interaction.followup.send("Invalid amount.", ephemeral=True)
                
                if parsed_amount > stock:
                    parsed_amount = stock  # Cap at available stock

                total_price = price * parsed_amount

                # Check user's coin balance
                coins = await conn.fetchval("SELECT coins FROM users WHERE id = $1", user_id)
                if coins is None or coins < total_price:
                    return await interaction.followup.send(" You don't have enough coins.", ephemeral=True)

                # Deduct coins from user
                await conn.execute("UPDATE users SET coins = coins - $1 WHERE id = $2", total_price, user_id)
                await log_spending(self.bot.db, total_price)
                # Update inventory (use parsed_amount)
                await conn.execute("""
                    INSERT INTO inventory (id, item_id, quantity) VALUES ($1, $2, $3)
                    ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $3
                """, user_id, item_id, parsed_amount)

                # Update stock (use parsed_amount)
                await conn.execute("UPDATE global_shop SET stock = stock - $1 WHERE pool_id = $2", parsed_amount, pool_id)

                embed = discord.Embed(
                    title=" Purchase Successful",
                    description=f"You bought **{parsed_amount}x {item.title()}** for **{total_price} coins**!",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed)

                logger.info(f"User {user_id} bought {parsed_amount} of {item} for {total_price}") # log the purchase


        except Exception as e:
            await interaction.followup.send(f" Error during purchase: `{type(e).__name__}` - {e}", ephemeral=True)
            traceback.print_exc()

    # --------- !shop-restock (OWNER ONLY) ---------
    @commands.command(name="shop-restock")
    @commands.is_owner()
    async def shop_restock(self, ctx: commands.Context):
        try:
            await self.bot.get_cog("ShopScheduler").reset_shop()
            await ctx.send("Shop has been restocked.")
        except Exception as e:
            await ctx.send(f" Failed to restock: `{type(e).__name__}` - {e}")
            traceback.print_exc()


# --- SETUP ---
async def setup(bot):
    await bot.add_cog(Shop(bot))
