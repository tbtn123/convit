from datetime import timedelta
import discord
from discord.ext import commands
from discord import app_commands
from utils.db_helpers import ensure_inventory, ensure_user
import traceback
from utils.singleton import EffectID
import math
from utils.parser import parse_amount, AmountParseError  # Added for flexible amount parsing

# Pagination View for Inventory
class InventoryPaginationView(discord.ui.View):
    def __init__(self, user_id, pages):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pages = pages
        self.current_page = 0
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

# -------------------- INVENTORY PENALTY HELPERS --------------------
async def get_inventory_total(conn, user_id: int) -> int:
    """Get total quantity of all items in inventory"""
    result = await conn.fetchval("""
        SELECT COALESCE(SUM(quantity), 0) 
        FROM inventory 
        WHERE id = $1
    """, user_id)
    return result or 0

def get_inventory_penalty(total_items: int) -> float:
    """Calculate penalty for item effectiveness based on inventory size"""
    if total_items < 100:
        return 0.0
    elif total_items < 200:
        return 0.2
    elif total_items < 400:
        return 0.5
    else:
        return 0.8

def get_inventory_warning(total_items: int) -> str:
    """Get inventory warning message based on total items"""
    if total_items >= 400:
        return "Warning: Critical inventory overload. Performance severely degraded."
    elif total_items >= 200:
        return "Alert: Inventory significantly overloaded. Effectiveness reduced."
    elif total_items >= 150:
        return "Recommendation: Inventory load high. Consider selling excess items."
    elif total_items >= 100:
        return "Alert: Inventory threshold reached. Performance impact detected."
    return None

class Items(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -------------------- AUTOCOMPLETE --------------------
    async def item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT i.name
                    FROM inventory t
                    JOIN items i ON i.id = t.item_id
                    WHERE t.id = $1 AND t.quantity > 0 AND i.name ILIKE $2 
                    LIMIT 20
                """, interaction.user.id, f"%{current}%")
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]
        except Exception as e:
            print(f"[ERROR] Autocomplete failed: {e}")
            return []

    async def all_items_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT name
                    FROM items
                    WHERE name ILIKE $1
                    ORDER BY name
                    LIMIT 25
                """, f"%{current}%")
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]
        except Exception as e:
            print(f"[ERROR] All items autocomplete failed: {e}")
            return []

    # -------------------- INVENTORY COMMAND --------------------
    @commands.hybrid_command(name="inventory", aliases = ['inv'], description="Check your inventory")
    async def inventory(self, ctx: commands.Context):
        await ctx.defer()

        user_id = ctx.author.id
        await ensure_inventory(self.bot.db, user_id)
        await ensure_user(self.bot.db, user_id)

        try:
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT i.name, i.description, i.icon, t.quantity
                    FROM inventory t
                    INNER JOIN items i ON t.item_id = i.id
                    WHERE t.id = $1 AND t.quantity > 0
                    ORDER BY i.name
                """, user_id)
                
                total_items = await get_inventory_total(conn, user_id)

            # Filter items with quantity > 0
            items_data = []
            for item in rows:
                name = item["name"] or "Unknown"
                desc = item["description"] or "No description"
                icon = item["icon"] or ":package:"
                quantity = item["quantity"]
                items_data.append({
                    'name': f"{icon} {name} x {quantity}",
                    'value': desc
                })
            
            if not items_data:
                embed = discord.Embed(
                    title=f"{ctx.author.display_name}'s Inventory",
                    description="Inventory Status: Empty",
                    color=discord.Color.dark_blue()
                )
                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                embed.set_footer(text="Load: 0 items | Status: Optimal")
                return await ctx.send(embed=embed)
            
            # Calculate footer text
            inv_penalty = get_inventory_penalty(total_items)
            if inv_penalty > 0:
                penalty_pct = int(inv_penalty * 100)
                next_threshold = 200 if total_items < 200 else 400 if total_items < 400 else None
                if next_threshold:
                    items_until_next = next_threshold - total_items
                    footer_text = f"Load: {total_items} items | Penalty: -{penalty_pct}% | {items_until_next} items until next threshold"
                else:
                    footer_text = f"Load: {total_items} items | Penalty: -{penalty_pct}% | Maximum penalty reached"
            else:
                items_until_penalty = 100 - total_items
                footer_text = f"Load: {total_items} items | Status: Optimal | {items_until_penalty} items until penalty"
            
            # Create pages (10 items per page)
            items_per_page = 10
            total_pages = math.ceil(len(items_data) / items_per_page)
            pages = []
            
            for page_num in range(total_pages):
                embed = discord.Embed(
                    title=f"{ctx.author.display_name}'s Inventory",
                    color=discord.Color.dark_blue()
                )
                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                
                start_idx = page_num * items_per_page
                end_idx = min(start_idx + items_per_page, len(items_data))
                
                for item_data in items_data[start_idx:end_idx]:
                    embed.add_field(
                        name=item_data['name'],
                        value=item_data['value'],
                        inline=False
                    )
                
                page_footer = f"Page {page_num + 1}/{total_pages} | {footer_text}"
                embed.set_footer(text=page_footer)
                pages.append(embed)
            
            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                view = InventoryPaginationView(ctx.author.id, pages)
                await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            await ctx.send(f"Inventory error: `{e}`")
            traceback.print_exc()

    # -------------------- USE ITEM COMMAND --------------------
    @app_commands.command(name="use", description="Use an item (supports 'all', '50%', '!5', etc.)")
    @app_commands.describe(item="Select item to use", amount="How many to use (supports 'all', '50%', etc.)")
    @app_commands.autocomplete(item=item_autocomplete)
    async def use_item(self, interaction: discord.Interaction, item: str, amount: str = "1"):
        await interaction.response.defer()
        user_id = interaction.user.id
        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)
        
       
        try:
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch("""
                SELECT inv.id, inv.quantity, inv.item_id,
                    eff.name AS effect_name,
                    eff.value,
                    ite.is_usable,
                    eff.type AS effect_type,
                    ite.name AS item_name,
                    users.energy,
                    users.energy_max
                FROM inventory inv
                INNER JOIN items ite ON inv.item_id = ite.id
                INNER JOIN users ON inv.id = users.id
                LEFT JOIN item_effects eff ON eff.item_id = ite.id
                WHERE inv.id = $1 AND ite.name ILIKE $2
            """, user_id, item)

                if not rows:
                    return await interaction.followup.send("You don't have that item.")

                row = rows[0]
                if not row["is_usable"]:
                    return await interaction.followup.send(f"You can't use *{row['item_name']}* , it's not a usable item.")
                quantity = row["quantity"]
                
                # Parse amount using parser utility (supports 'all', '50%', '!5', etc.)
                try:
                    parsed_amount = parse_amount(amount, quantity)
                except AmountParseError as e:
                    return await interaction.followup.send(f"Invalid amount: {e}")
                
                if quantity < parsed_amount:
                    return await interaction.followup.send(f"You only have `{quantity}` of that item.")

                current_energy = row["energy"]
                energy_max = row["energy_max"]
                item_id = row["item_id"]
                item_name = row["item_name"]
                
                # Use parsed_amount for calculations
                penalty = int(parsed_amount * 0.25) if parsed_amount > 1 else 0
                if current_energy < penalty:
                    return await interaction.followup.send("You don't have enough energy to use this item.")

                followup_msg = ""
                restore_total = 0
                energy_max_inc = 0
                used_effects = []

                for r in rows:
                    
                    effect_name = r["effect_name"]
                    value = r["value"]
                    effect_type = r["effect_type"]

                    if effect_type == "int":
                        try:
                            value = int(value)
                        except ValueError:
                            continue
                    if effect_name == "unstackable" and parsed_amount > 1:
                        return await interaction.followup.send(f"You can only use `{item_name}` one at a time.")
                    if effect_name == "add_energy":
                        restore_total += value * parsed_amount
                    if effect_name == "add_energy_max":
                        energy_max_inc += value * parsed_amount
                
                # Apply inventory penalty to energy restoration
                if restore_total > 0:
                    total_items = await get_inventory_total(conn, user_id)
                    inv_penalty = get_inventory_penalty(total_items)
                    
                    if inv_penalty > 0:
                        original_restore = restore_total
                        restore_total = int(restore_total * (1 - inv_penalty))
                        penalty_pct = int(inv_penalty * 100)
                        used_effects.append(f"Alert: Inventory overload detected. Item effectiveness reduced: -{penalty_pct}% ({original_restore} → {restore_total})")
                    if effect_name == "rob_protection":
                        effect_value = await conn.fetchval("""
                            SELECT value FROM item_effects
                            WHERE item_id = $1 AND name = $2
                            """, item_id , "rob_protection" )
                        effect_value = int(effect_value)
                        effect_row = await conn.fetchrow("""
                            SELECT icon, name 
                            FROM user_effects
                            WHERE id = $1
                        """, EffectID.ROB_PROTECT)

                        current_effect = await conn.fetchrow("""
                        SELECT * FROM current_effects WHERE user_id = $1 AND effect_id = $2 
""", interaction.user.id, EffectID.ROB_PROTECT)
                        
                        if current_effect is not None:
                            return await interaction.followup.send("You cant use the lock while it is active bruh")
                        if not effect_row:
                            return await interaction.followup.send("Rob data effect not found!")


                        icon = effect_row['icon']
                        effect_name = effect_row['name']

                        
                        await conn.execute("""
                            INSERT INTO current_effects (user_id, effect_id, duration, ticks)
                            VALUES ($1, $2, $3, $4)
                        """, user_id, EffectID.ROB_PROTECT, effect_value, effect_value)
                    if effect_name == "lottery_ticket":
                        # Use parsed_amount for lottery tickets
                        for _ in range(parsed_amount):
                            await conn.execute("INSERT INTO lottery (user_id) VALUES ($1)", user_id)

                    if effect_name == "message":
                        followup_msg += value + "\n"

                # Apply energy restore
                new_energy = min(current_energy - penalty + restore_total, energy_max)
                new_energy_max = energy_max + energy_max_inc
                await conn.execute("UPDATE users SET energy = $1 WHERE id = $2", new_energy, user_id)
                await conn.execute("UPDATE users SET energy_max = $1 WHERE id = $2", new_energy_max, user_id)
                
                # Trigger Replenished effect if energy reaches max
                if new_energy >= energy_max:
                    await conn.execute("""
                        INSERT INTO current_effects (user_id, effect_id, duration, ticks, applied_at)
                        VALUES ($1, $2, $3, $3, NOW())
                        ON CONFLICT (user_id, effect_id) DO UPDATE
                        SET duration = $3, ticks = $3, applied_at = NOW()
                    """, user_id, EffectID.REPLENISHED, 120)
                if restore_total:
                    used_effects.append(f"⚡ Restored `{restore_total}` energy")
                if energy_max_inc:
                    used_effects.append(f" 🔋 Increased `{energy_max_inc}` energy")
                if penalty > 0:
                    used_effects.append(f"⚡ Lost `{penalty}` energy for using multiple items")

                # Update inventory (use parsed_amount)
                if quantity == parsed_amount:
                    await conn.execute("DELETE FROM inventory WHERE id = $1 AND item_id = $2", user_id, item_id)
                else:
                    await conn.execute("UPDATE inventory SET quantity = quantity - $1 WHERE id = $2 AND item_id = $3", parsed_amount, user_id, item_id)

                if len(used_effects) > 20:
                    used_effects = ["Multiple items used."]
                
                # Handle image URLs from item effects
                image_urls = []
                for r in rows:
                    effect_name = r["effect_name"]
                    value = r["value"]
                    if effect_name == "image_url" and value:
                        image_urls.append(value)
                
                embed = discord.Embed(
                    title=f" {interaction.user.display_name} used: {item_name} x {parsed_amount}",
                    description="\n".join(used_effects) or "*But nothing happened...*",
                    color=discord.Color.brand_green()
                )
                embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
                
                # Set first image as embed image, others as thumbnails
                if image_urls:
                    embed.set_image(url=image_urls[0])
                    if len(image_urls) > 1:
                        embed.set_thumbnail(url=image_urls[1])
                
                await interaction.followup.send(embed=embed)
                
                
                if followup_msg:
                    await interaction.followup.send(followup_msg)

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"An error occurred: `{type(e).__name__}` - `{e}`\nContact the bot developer."
            try:
                await interaction.followup.send(error_msg)
            except:
                await interaction.channel.send(error_msg)

    @app_commands.command(name="item-wiki", description="View detailed information about an item")
    @app_commands.describe(item="Item name to look up")
    @app_commands.autocomplete(item=all_items_autocomplete)
    async def item_wiki(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer()

        try:
            async with self.bot.db.acquire() as conn:
                item_data = await conn.fetchrow("""
                    SELECT id, name, description, icon, is_usable
                    FROM items
                    WHERE LOWER(name) = LOWER($1)
                """, item)

                if not item_data:
                    return await interaction.followup.send(embed=discord.Embed(
                        title="Item Not Found",
                        description=f"No item found with the name: **{item}**",
                        color=discord.Color.red()
                    ))

                item_id = item_data['id']
                item_name = item_data['name']
                description = item_data['description'] or "No description available."
                icon = item_data['icon'] or ":package:"
                is_usable = item_data['is_usable']
                

                effects = await conn.fetch("""
                    SELECT name, value, type
                    FROM item_effects
                    WHERE item_id = $1
                """, item_id)

                embed = discord.Embed(
                    title=f"{icon} {item_name}",
                    description=description,
                    color=discord.Color.blue()
                )
                embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)

                embed.add_field(name="Usable", value="✅ Yes" if is_usable else "❌ No", inline=True)
                

                if effects:
                    effect_list = []
                    for eff in effects:
                        eff_name = eff['name']
                        eff_value = eff['value']
                        
                        if eff_name == "add_energy":
                            effect_list.append(f"⚡ Restores **{eff_value}** energy")
                        elif eff_name == "add_energy_max":
                            effect_list.append(f"🔋 Increases max energy by **{eff_value}**")
                        elif eff_name == "rob_protection":
                            effect_list.append(f"🔒 Rob protection for **{eff_value}** ticks")
                        elif eff_name == "lottery_ticket":
                            effect_list.append(f"🎟️ Lottery ticket entry")
                        elif eff_name == "unstackable":
                            effect_list.append(f"⚠️ Can only use one at a time")
                        elif eff_name == "message":
                            effect_list.append(f"💬 {eff_value}")
                        else:
                            effect_list.append(f" {eff_name}: {eff_value}")
                    
                    embed.add_field(
                        name="Effects",
                        value="\n".join(effect_list),
                        inline=False
                    )
                else:
                    embed.add_field(name="Effects", value="*No special effects*", inline=False)

                await interaction.followup.send(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"An error occurred: `{type(e).__name__}` - `{e}`")

    @app_commands.command(name="give-items", description="Give items to target (supports 'all', '50%', '!5', etc.)")
    @app_commands.autocomplete(item=item_autocomplete)
    async def give_item(self, interaction: discord.Interaction, target: discord.User, item: str, amount: str = "1"):
        await interaction.response.defer()

        await ensure_user(self.bot.db, interaction.user.id)
        await ensure_inventory(self.bot.db, interaction.user.id)
        await ensure_user(self.bot.db, target.id)
        await ensure_inventory(self.bot.db, target.id)

        if target.id == interaction.user.id:
            return await interaction.followup.send(embed=discord.Embed(
                title="Invalid Action",
                description="You cannot give items to yourself.",
                color=discord.Color.red()
            ))

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                author_info = await conn.fetchrow("""
                    SELECT inv.id, inv.item_id, inv.quantity, ite.name
                    FROM inventory inv
                    INNER JOIN items ite ON ite.id = inv.item_id
                    WHERE inv.id = $1 AND LOWER(ite.name) = LOWER($2)
                """, interaction.user.id, item)

                if not author_info:
                    return await interaction.followup.send(embed=discord.Embed(
                        title="Item Not Found",
                        description="You do not own this item.",
                        color=discord.Color.red()
                    ))

                # Parse amount using parser utility (supports 'all', '50%', '!5', etc.)
                try:
                    parsed_amount = parse_amount(amount, author_info['quantity'])
                except AmountParseError as e:
                    return await interaction.followup.send(embed=discord.Embed(
                        title="Invalid Amount",
                        description=str(e),
                        color=discord.Color.red()
                    ))

                if author_info['quantity'] < parsed_amount or parsed_amount <= 0:
                    return await interaction.followup.send(embed=discord.Embed(
                        title="Insufficient Quantity",
                        description=f"You only have {author_info['quantity']} of this item.",
                        color=discord.Color.red()
                    ))

                target_info = await conn.fetchrow("""
                    SELECT inv.id, inv.item_id, inv.quantity, ite.name
                    FROM inventory inv
                    INNER JOIN items ite ON ite.id = inv.item_id
                    WHERE inv.id = $1 AND LOWER(ite.name) = LOWER($2)
                """, target.id, item)

                item_id = author_info['item_id']
                remain = author_info['quantity'] - parsed_amount  # Use parsed_amount
                if remain < 0:
                    return await interaction.followup.send(embed=discord.Embed(
                        title="remain < 0",
                        description="this is somehow a edge case. reverted action",
                        color=discord.Color.red()
                    ))

                await conn.execute("""
                    UPDATE inventory SET quantity = $1
                    WHERE id = $2 AND item_id = $3
                """, remain, interaction.user.id, item_id)

                # Add to target inventory (use parsed_amount)
                await conn.execute("""
                    INSERT INTO inventory (id, item_id, quantity)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $3
                """, target.id, item_id, parsed_amount)

        await interaction.followup.send(embed=discord.Embed(
            title="Item Transfer Successful",
            description=f"Gave {parsed_amount}x {author_info['name']} to {target.mention}.",
            color=discord.Color.green()
        ))


# --- SETUP ---
async def setup(bot):
    await bot.add_cog(Items(bot))
