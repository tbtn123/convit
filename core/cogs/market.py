import discord
from discord.ext import commands
from datetime import datetime
import traceback
from typing import Optional, Any, Dict

from utils.db_helpers import ensure_inventory, ensure_user
from utils.parser import parse_amount, AmountParseError  # Added for flexible amount parsing


# -------------------- BUY MODAL --------------------
class BuyModal(discord.ui.Modal, title="Buy from Trade"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

        self.trade_id = discord.ui.TextInput(
            label="Trade ID",
            placeholder="Enter the Trade ID you want to buy from (e.g. 123)",
            required=True
        )
        self.amount = discord.ui.TextInput(
            label="Amount",
            placeholder="Enter amount (e.g. 1, all, 50%, !5)",
            required=True
        )
        self.add_item(self.trade_id)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        # defer as ephemeral (this is a user-only confirmation)
        await interaction.response.defer(ephemeral=True)

        try:
            trade_id = int(self.trade_id.value.strip())
            amount_str = self.amount.value.strip()
            
            # Get trade info to determine max available
            async with self.cog.bot.db.acquire() as conn:
                trade = await conn.fetchrow("SELECT quantity FROM trades WHERE id = $1", trade_id)
                if not trade:
                    return await interaction.followup.send("Trade not found.", ephemeral=True)
                
                # Parse amount using parser utility (supports 'all', '50%', etc.)
                try:
                    parsed_amount = parse_amount(amount_str, trade['quantity'])
                except AmountParseError as e:
                    return await interaction.followup.send(f"Invalid amount: {e}", ephemeral=True)
                
                if parsed_amount <= 0:
                    return await interaction.followup.send("Amount must be a positive integer.", ephemeral=True)
        except ValueError:
            return await interaction.followup.send("Invalid input. Trade ID must be a number.", ephemeral=True)

        result = await self.cog.process_buy(interaction.user.id, trade_id, parsed_amount)

        # process_buy returns str on error, or dict on success
        if isinstance(result, str):
            return await interaction.followup.send(result, ephemeral=True)

        # success: show a compact ephemeral embed
        embed = discord.Embed(
            title="Purchase Successful ✅",
            description=f"You bought **{result['amount']}x {result['item_name']}** for **{result['total_cost']}** coins.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        seller = interaction.client.get_user(result["seller_id"])
        embed.add_field(name="Seller", value=seller.mention if seller else str(result["seller_id"]), inline=True)
        embed.set_footer(text=f"Trade #{trade_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)


# -------------------- WITHDRAW MODAL --------------------
class WithdrawModal(discord.ui.Modal, title="Withdraw Trade"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

        self.trade_id = discord.ui.TextInput(
            label="Trade ID",
            placeholder="Enter the Trade ID you want to withdraw (e.g. 123)",
            required=True
        )
        self.add_item(self.trade_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            trade_id = int(self.trade_id.value.strip())
        except ValueError:
            return await interaction.followup.send("Invalid Trade ID.", ephemeral=True)

        result = await self.cog.process_withdraw(interaction.user.id, trade_id)
        if isinstance(result, str):
            return await interaction.followup.send(result, ephemeral=True)

        embed = discord.Embed(
            title="Trade Withdrawn 🧾",
            description=f"Returned **{result}x** items back to your inventory.",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Trade #{trade_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)


# -------------------- VIEW WITH GLOBAL BUTTONS --------------------
class MarketView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.primary)
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuyModal(self.cog))

    @discord.ui.button(label="Withdraw", style=discord.ButtonStyle.danger)
    async def withdraw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WithdrawModal(self.cog))


# -------------------- MARKET --------------------
class Market(commands.GroupCog, name="market"):
    def __init__(self, bot):
        self.bot = bot

    # ---------- LIST ----------
    @commands.hybrid_command(name="list", description="Show current trades")
    async def list_trades(self, ctx: commands.Context, page: int = 1):
        await ctx.defer()
        if page < 1:
            return await ctx.send("Page must be >= 1.")
        limit = 20
        offset = (page - 1) * limit
        try:
            async with self.bot.db.acquire() as conn:
                total_trades = await conn.fetchval("SELECT COUNT(*) FROM trades")
                rows = await conn.fetch("""
                    SELECT t.id, t.offerer_id, i.name, t.price, t.quantity, t.created_at
                    FROM trades t
                    JOIN items i ON i.id = t.item_id
                    ORDER BY t.created_at DESC
                    LIMIT $1 OFFSET $2
                """, limit, offset)

            if not rows:
                return await ctx.send("No trades available on this page.")

            embed = discord.Embed(
                title=f"📜 Market Trades (Page {page})",
                color=discord.Color.blurple(),
                timestamp=datetime.utcnow(),
                description="Click **Buy** and enter the Trade ID shown below to purchase."
            )

            for row in rows:
                seller = self.bot.get_user(row["offerer_id"])
                seller_name = seller.name if seller else str(row["offerer_id"])
                embed.add_field(
                    name=f"Trade #{row['id']} — {row['name']}",
                    value=(
                        f"Price: **{row['price']}** each • In Stock: **{row['quantity']}**\n"
                        f"Seller: {seller_name}"
                    ),
                    inline=False
                )

            max_page = max(1, (total_trades + limit - 1) // limit)
            embed.set_footer(text=f"Page {page}/{max_page} • Total Trades: {total_trades}")
            view = MarketView(self)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await ctx.send(f"Error: {e}")

    # ---------- SELL ----------
    @commands.hybrid_command(name="sell", description="List an item for sale")
    async def sell_item(self, ctx: commands.Context, item_name: str, quantity: int, price: int):
        await ctx.defer()
        user_id = ctx.author.id
        if quantity <= 0 or price <= 0:
            return await ctx.send("Quantity and price must be > 0.")

        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)

        try:
            async with self.bot.db.acquire() as conn:
                # Use a transaction and lock the inventory row to avoid race conditions
                async with conn.transaction():
                    item_row = await conn.fetchrow("SELECT id, name FROM items WHERE name ILIKE $1", item_name)
                    if not item_row:
                        return await ctx.send("That item does not exist.")

                    inv_row = await conn.fetchrow(
                        "SELECT quantity FROM inventory WHERE id = $1 AND item_id = $2 FOR UPDATE",
                        user_id, item_row["id"]
                    )
                    if not inv_row or inv_row["quantity"] < quantity:
                        return await ctx.send("You don't have enough of that item.")

                    # subtract from inventory and create trade (returning id)
                    await conn.execute(
                        "UPDATE inventory SET quantity = quantity - $1 WHERE id = $2 AND item_id = $3",
                        quantity, user_id, item_row["id"]
                    )

                    # insert trade and return id
                    trade_row = await conn.fetchrow("""
                        INSERT INTO trades (offerer_id, item_id, quantity, price, created_at)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id
                    """, user_id, item_row["id"], quantity, price, datetime.utcnow())

                    trade_id = trade_row["id"]

            # outside transaction
            embed = discord.Embed(
                title="Trade Created ",
                description=f"Listed **{quantity}x {item_row['name']}** for **{price}** coins each.",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Trade ID: {trade_id} — Use that ID to buy or withdraw.")
            await ctx.send(embed=embed)

        except Exception as e:
            traceback.print_exc()
            await ctx.send(f"Error: {e}")

    # ---------- PROCESS BUY ----------
    async def process_buy(self, buyer_id: int, trade_id: int, amount: int) -> Any:
        """
        Returns dict on success:
            { item_id, item_name, amount, total_cost, seller_id }
        Returns str on error.
        """
        if amount <= 0:
            return "Amount must be positive."

        await ensure_user(self.bot.db, buyer_id)
        await ensure_inventory(self.bot.db, buyer_id)

        try:
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    # lock the trade row
                    trade = await conn.fetchrow("SELECT * FROM trades WHERE id = $1 FOR UPDATE", trade_id)
                    if not trade:
                        return "Trade not found."

                    if trade["quantity"] < amount:
                        return "Not enough stock available."

                    if trade["offerer_id"] == buyer_id:
                        return "You cannot buy your own trade."

                    total_cost = trade["price"] * amount

                    # lock buyer row
                    buyer = await conn.fetchrow("SELECT coins FROM users WHERE id = $1 FOR UPDATE", buyer_id)
                    if not buyer:
                        return "Buyer not found."

                    if buyer["coins"] < total_cost:
                        return "You don't have enough coins."

                    # lock seller row (for safety)
                    seller = await conn.fetchrow("SELECT coins FROM users WHERE id = $1 FOR UPDATE", trade["offerer_id"])
                    if not seller:
                        return "Seller not found."

                    # transfer coins
                    await conn.execute("UPDATE users SET coins = coins - $1 WHERE id = $2", total_cost, buyer_id)
                    await conn.execute("UPDATE users SET coins = coins + $1 WHERE id = $2", total_cost, trade["offerer_id"])

                    # update or delete trade
                    new_quantity = trade["quantity"] - amount
                    if new_quantity <= 0:
                        await conn.execute("DELETE FROM trades WHERE id = $1", trade_id)
                    else:
                        await conn.execute("UPDATE trades SET quantity = $1 WHERE id = $2", new_quantity, trade_id)

                    # add items to buyer inventory
                    await conn.execute("""
                        INSERT INTO inventory (id, item_id, quantity)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $3
                    """, buyer_id, trade["item_id"], amount)

                    item_row = await conn.fetchrow("SELECT name FROM items WHERE id = $1", trade["item_id"])

                    return {
                        "item_id": trade["item_id"],
                        "item_name": item_row["name"] if item_row else str(trade["item_id"]),
                        "amount": amount,
                        "total_cost": total_cost,
                        "seller_id": trade["offerer_id"]
                    }

        except Exception as e:
            traceback.print_exc()
            return "An internal error occurred while processing the purchase."

    # ---------- PROCESS WITHDRAW ----------
    async def process_withdraw(self, user_id: int, trade_id: int) -> Any:
        """
        Returns integer (quantity returned) on success, or str error.
        """
        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)

        try:
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    trade = await conn.fetchrow("SELECT * FROM trades WHERE id = $1 FOR UPDATE", trade_id)
                    if not trade:
                        return "Trade not found."

                    if trade["offerer_id"] != user_id:
                        return "You don't own this trade."

                    qty = trade["quantity"]

                    # return items to user's inventory
                    await conn.execute("""
                        INSERT INTO inventory (id, item_id, quantity)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $3
                    """, user_id, trade["item_id"], qty)

                    # delete the trade
                    await conn.execute("DELETE FROM trades WHERE id = $1", trade_id)

                    return qty

        except Exception as e:
            traceback.print_exc()
            return "An internal error occurred while withdrawing the trade."


# -------------------- SETUP --------------------
async def setup(bot):
    await bot.add_cog(Market(bot))
