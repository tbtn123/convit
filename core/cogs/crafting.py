import discord
from discord.ext import commands
from discord import app_commands
from utils.db_helpers import ensure_user, ensure_inventory
import math
from utils.parser import parse_amount, AmountParseError  # Added for flexible amount parsing

# Pagination View for Recipes
class RecipesPaginationView(discord.ui.View):
    def __init__(self, user_id, pages, total_items):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pages = pages
        self.current_page = 0
        self.total_items = total_items
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

# Recipe Selection View
class RecipeSelectView(discord.ui.View):
    def __init__(self, cog, user_id, item_name, recipes_data, amount):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.item_name = item_name
        self.recipes_data = recipes_data
        self.amount = amount
        
        # Add dropdown
        options = []
        for recipe in recipes_data:
            # Format ingredients for label
            ingredients = ", ".join([f"{r['qty']}x {r['name']}" for r in recipe['requirements'][:3]])
            if len(recipe['requirements']) > 3:
                ingredients += "..."
            
            options.append(discord.SelectOption(
                label=f"{recipe['recipe_name']}",
                description=ingredients[:100],
                value=str(recipe['recipe_id'])
            ))
        
        self.select = discord.ui.Select(
            placeholder="Choose a recipe...",
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
    
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your crafting menu.", ephemeral=True)
        
        recipe_id = int(self.select.values[0])
        await interaction.response.defer()
        
        # Find selected recipe
        selected_recipe = next((r for r in self.recipes_data if r['recipe_id'] == recipe_id), None)
        if not selected_recipe:
            return await interaction.followup.send("Recipe not found.", ephemeral=True)
        
        await self.cog.perform_craft(interaction, self.user_id, selected_recipe, self.amount)
        self.stop()

class Crafting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    # -------------------- AUTOCOMPLETE --------------------
    async def item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for craftable items"""
        try:
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT i.name
                    FROM recipe_results rr
                    JOIN items i ON rr.item_id = i.id
                    WHERE i.name ILIKE $1
                    ORDER BY i.name
                    LIMIT 25
                """, f"%{current}%")
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]
        except Exception as e:
            print(f"[ERROR] Item autocomplete failed: {e}")
            return []
    
    @commands.hybrid_command(name="craft", description="Craft items (supports 'all', '50%', etc. based on materials)")
    @app_commands.describe(item="Item you want to craft", amount="How many to craft (or 'max' for maximum possible)")
    @app_commands.autocomplete(item=item_autocomplete)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def craft(self, ctx: commands.Context, item: str, amount: str = "1"):
        await ctx.defer()
        
        user_id = ctx.author.id
        await ensure_user(self.bot.db, user_id)
        await ensure_inventory(self.bot.db, user_id)
        
        async with self.bot.db.acquire() as conn:
            # 1. Find all recipes that produce this item
            recipes = await conn.fetch("""
                SELECT DISTINCT r.id as recipe_id, r.name as recipe_name, r.description
                FROM recipes r
                JOIN recipe_results rr ON r.id = rr.recipe_id
                JOIN items i ON rr.item_id = i.id
                WHERE LOWER(i.name) = LOWER($1)
            """, item)
            
            if not recipes:
                embed = discord.Embed(
                    title="Error. Item not craftable",
                    description=f"No recipes found for '{item}'.\nUse `/recipes` to view available recipes.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
            
            # 2. Get requirements for each recipe
            recipes_data = []
            for recipe in recipes:
                requirements = await conn.fetch("""
                    SELECT i.name, i.id as item_id, rri.quantity as qty, rri.is_consumed
                    FROM recipe_require_items rri
                    JOIN items i ON rri.item_id = i.id
                    WHERE rri.recipe_id = $1
                """, recipe['recipe_id'])
                
                recipes_data.append({
                    'recipe_id': recipe['recipe_id'],
                    'recipe_name': recipe['recipe_name'],
                    'description': recipe['description'],
                    'requirements': [dict(r) for r in requirements]
                })
            
            # 3. If only one recipe, craft directly
            if len(recipes_data) == 1:
                # For crafting, we'll parse amount as a simple integer or 'max'
                # 'max' will be calculated based on available materials in perform_craft
                await self.perform_craft(ctx, user_id, recipes_data[0], amount)
            else:
                # 4. Multiple recipes - show dropdown
                embed = discord.Embed(
                    title="Recipe Selection",
                    description=f"Multiple recipes found for {item}. Select one below.",
                    color=discord.Color.blue()
                )
                view = RecipeSelectView(self, user_id, item, recipes_data, amount)
                await ctx.send(embed=embed, view=view)
    
    async def perform_craft(self, ctx_or_interaction, user_id, recipe_data, amount):
        """Actually perform the crafting"""
        async with self.bot.db.acquire() as conn:
            recipe_id = recipe_data['recipe_id']
            requirements = recipe_data['requirements']
            
            # Calculate max craftable if amount is 'max' or similar
            if amount.lower() in ['max', 'all']:
                # Calculate maximum craftable based on available materials
                max_craftable = float('inf')
                for req in requirements:
                    if req['is_consumed']:  # Only check consumed items
                        user_qty = await conn.fetchval("""
                            SELECT quantity FROM inventory
                            WHERE id = $1 AND item_id = $2
                        """, user_id, req['item_id'])
                        if not user_qty:
                            max_craftable = 0
                            break
                        max_craftable = min(max_craftable, user_qty // req['qty'])
                
                if max_craftable == float('inf') or max_craftable <= 0:
                    max_craftable = 0
                
                parsed_amount = int(max_craftable)
            else:
                # Parse as integer
                try:
                    parsed_amount = int(amount)
                except ValueError:
                    embed = discord.Embed(
                        title="Error. Invalid amount",
                        description="Amount must be a number or 'max'.",
                        color=discord.Color.red()
                    )
                    if hasattr(ctx_or_interaction, 'followup'):
                        return await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        return await ctx_or_interaction.send(embed=embed)
            
            if parsed_amount < 1:
                embed = discord.Embed(
                    title="Error. Invalid amount",
                    description="Amount must be at least 1.",
                    color=discord.Color.red()
                )
                if hasattr(ctx_or_interaction, 'followup'):
                    return await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    return await ctx_or_interaction.send(embed=embed)
            
            # Check if user has all required items (use parsed_amount)
            missing = []
            for req in requirements:
                user_qty = await conn.fetchval("""
                    SELECT quantity FROM inventory
                    WHERE id = $1 AND item_id = $2
                """, user_id, req['item_id'])
                
                needed = req['qty'] * parsed_amount
                if not user_qty or user_qty < needed:
                    missing.append(f"{needed}x {req['name']} (available {user_qty or 0})")
            
            if missing:
                embed = discord.Embed(
                    title="Error. Insufficient resources",
                    description="Required materials not available.\n\n" + "\n".join(missing),
                    color=discord.Color.red()
                )
                embed.add_field(name="Status", value="Fabrication denied", inline=False)
                
                if hasattr(ctx_or_interaction, 'followup'):
                    return await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    return await ctx_or_interaction.send(embed=embed)
            
            # Consume materials (except non-consumed like furnace) - use parsed_amount
            for req in requirements:
                if req['is_consumed']:
                    needed = req['qty'] * parsed_amount
                    await conn.execute("""
                        UPDATE inventory 
                        SET quantity = quantity - $1
                        WHERE id = $2 AND item_id = $3
                    """, needed, user_id, req['item_id'])
                    
                    # Remove if quantity reaches 0
                    await conn.execute("""
                        DELETE FROM inventory
                        WHERE id = $1 AND item_id = $2 AND quantity <= 0
                    """, user_id, req['item_id'])
            
            # Give result items (use parsed_amount)
            results = await conn.fetch("""
                SELECT item_id, quantity
                FROM recipe_results
                WHERE recipe_id = $1
            """, recipe_id)
            
            result_text = []
            for result in results:
                result_qty = result['quantity'] * parsed_amount
                
                # Add to inventory
                await conn.execute("""
                    INSERT INTO inventory (id, item_id, quantity)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (id, item_id) DO UPDATE SET quantity = inventory.quantity + $3
                """, user_id, result['item_id'], result_qty)
                
                item_name = await conn.fetchval("SELECT name FROM items WHERE id = $1", result['item_id'])
                result_text.append(f"{result_qty}x {item_name}")
            
            # Success message (use parsed_amount)
            embed = discord.Embed(
                title="Fabrication complete",
                description=f"Recipe {recipe_data['recipe_name']}. Quantity {parsed_amount}.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Output", value="\n".join(result_text), inline=False)
            embed.add_field(name="Status", value="Operational", inline=False)
            
            if hasattr(ctx_or_interaction, 'followup'):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
    
    @commands.hybrid_command(name="recipes", description="View all crafting recipes")
    async def recipes(self, ctx: commands.Context):
        await ctx.defer()
        
        async with self.bot.db.acquire() as conn:
            # Get all craftable items
            craftable_items = await conn.fetch("""
                SELECT DISTINCT i.id, i.name, i.icon
                FROM items i
                JOIN recipe_results rr ON i.id = rr.item_id
                ORDER BY i.name
            """)
            
            if not craftable_items:
                embed = discord.Embed(
                    title="Recipe Database",
                    description="No recipes available in database.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
            
            # Build all recipe data
            all_recipe_data = []
            for item in craftable_items:
                recipes = await conn.fetch("""
                    SELECT r.id, r.name
                    FROM recipes r
                    JOIN recipe_results rr ON r.id = rr.recipe_id
                    WHERE rr.item_id = $1
                """, item['id'])
                
                recipe_list = []
                for recipe in recipes:
                    reqs = await conn.fetch("""
                        SELECT i.name, rri.quantity, rri.is_consumed
                        FROM recipe_require_items rri
                        JOIN items i ON rri.item_id = i.id
                        WHERE rri.recipe_id = $1
                    """, recipe['id'])
                    
                    req_text = []
                    for req in reqs:
                        consumed = "" if req['is_consumed'] else " (reusable)"
                        req_text.append(f"{req['quantity']}x {req['name']}{consumed}")
                    
                    recipe_list.append(f"**{recipe['name']}:** {', '.join(req_text)}")
                
                icon = item['icon'] or "📦"
                all_recipe_data.append({
                    'name': f"{icon} {item['name']}",
                    'value': "\n".join(recipe_list)
                })
            
            # Create pages (6 items per page)
            items_per_page = 6
            total_pages = math.ceil(len(all_recipe_data) / items_per_page)
            pages = []
            
            for page_num in range(total_pages):
                embed = discord.Embed(
                    title="Recipe Database",
                    description="Available fabrication recipes. Use `/craft <item_name>` to initiate fabrication.",
                    color=discord.Color.blue()
                )
                
                start_idx = page_num * items_per_page
                end_idx = min(start_idx + items_per_page, len(all_recipe_data))
                
                for recipe_data in all_recipe_data[start_idx:end_idx]:
                    embed.add_field(
                        name=recipe_data['name'],
                        value=recipe_data['value'],
                        inline=False
                    )
                
                embed.set_footer(text=f"Page {page_num + 1}/{total_pages} | {len(craftable_items)} craftable items")
                pages.append(embed)
            
            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                view = RecipesPaginationView(ctx.author.id, pages, len(craftable_items))
                await ctx.send(embed=pages[0], view=view)

async def setup(bot):
    await bot.add_cog(Crafting(bot))
