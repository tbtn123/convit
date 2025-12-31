import discord
from discord.ext import commands
from datetime import datetime, timezone
import traceback


class CategorySelect(discord.ui.Select):
    def __init__(self, view):
        self.view_ref = view
        options = view.build_options_for_current_page()
        super().__init__(placeholder="Select a category to view commands...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        # Delegate handling to the view so page state can be managed centrally
        await self.view_ref.handle_selection(interaction, self.values[0])


class HelpView(discord.ui.View):
    def __init__(self, bot, cog_data, author):
        super().__init__(timeout=300)
        self.bot = bot
    def __init__(self, bot, cog_data, author):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.cog_data = cog_data
        # Sorted list of category names
        self.cog_names = sorted(cog_data.keys())
        # Page size for select options (1 slot reserved for 'Home')
        self.page_size = 24
        self.page_index = 0
        self.message = None # Reference to disable buttons on timeout

        self.select = CategorySelect(self)
        self.add_item(self.select)

    def build_options_for_current_page(self):
        """Return a list of SelectOption for the current page. Always includes 'Home' first."""
        options = []
        options.append(discord.SelectOption(label="Home", description="View bot overview and statistics", value="home", default=True))

        start = self.page_index * self.page_size
        end = start + self.page_size
        page_cogs = self.cog_names[start:end]

        for cog_name in page_cogs:
            data = self.cog_data.get(cog_name, {})
            cmd_count = len(data.get('commands', []))
            options.append(discord.SelectOption(
                label=cog_name, 
                description=f"{cmd_count} command{'s' if cmd_count != 1 else ''}", 
                value=cog_name
            ))
        return options

    def create_home_embed(self):
        total_commands = sum(len(data['commands']) for data in self.cog_data.values())
        total_categories = len(self.cog_data)

        uptime_str = "Unknown"
        if hasattr(self.bot, 'start_time') and self.bot.start_time:
            start_time = self.bot.start_time
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            uptime_delta = datetime.now(timezone.utc) - start_time
            hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s"

        description = (
            "Welcome to the help menu! Use the dropdown below to explore different command categories.\n\n"
            f"**Quick Stats**\n"
            f" - Total Commands: {total_commands}\n"
            f" - Categories: {total_categories}\n"
            f" - Uptime: {uptime_str}\n\n"
            "**Categories Available:**\n" +
            ", ".join([f"`{name}`" for name in self.cog_names])
        )

        embed = discord.Embed(title="Bot Help Menu", description=description, color=discord.Color.blue())
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text="Select a category from the dropdown menu below")
        return embed

    def create_category_embed(self, category):
        data = self.cog_data.get(category, {})
        commands_list = data.get('commands', [])
        description = data.get('description') or f"All commands in the {category} category"

        embed = discord.Embed(title=f"{category} Commands", description=description, color=discord.Color.green())
        
        for cmd in sorted(commands_list, key=lambda c: c.name):
            signature = f"/{cmd.qualified_name}"
            if getattr(cmd, 'signature', None):
                signature += f" {cmd.signature}"
            
            cmd_help = cmd.help or getattr(cmd, 'description', None) or "No description available"
            embed.add_field(name=f"`{signature}`", value=cmd_help, inline=False)

        embed.set_footer(text=f"Category: {category} | {len(commands_list)} commands")
        return embed

    async def handle_selection(self, interaction: discord.Interaction, selected: str):
        for option in self.select.options:
            option.default = (option.value == selected)

        embed = self.create_home_embed() if selected == "home" else self.create_category_embed(selected)
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1)
    async def previous_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page_index > 0:
            self.page_index -= 1
            self.select.options = self.build_options_for_current_page()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("You are on the first page.", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_index = (len(self.cog_names) - 1) // self.page_size
        if self.page_index < max_index:
            self.page_index += 1
            self.select.options = self.build_options_for_current_page()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("You are on the last page.", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Help menu closed.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        self.stop()


class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_cog_data(self):
        cog_data = {}
        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ['helpcommand', 'help']:
                continue

            # Fetch commands associated with this cog
            cog_commands = [cmd for cmd in self.bot.walk_commands() 
                           if cmd.cog_name == cog_name and not cmd.hidden and not cmd.parent]
            
            if cog_commands:
                cog_data[cog_name] = {
                    'commands': cog_commands,
                    'description': getattr(cog, 'description', f"Commands for {cog_name}")
                }
        return cog_data

    @commands.hybrid_command(name="help", description="Display the interactive help menu")
    async def help(self, ctx, command_name: str = None):
        try:
            if command_name:
                command = self.bot.get_command(command_name)
                if not command:
                    if getattr(ctx, 'interaction', None):
                        await ctx.interaction.response.send_message(f"Command `{command_name}` not found.", ephemeral=True)
                    else:
                        await ctx.send(f"Command `{command_name}` not found.")
                    return
                
                embed = discord.Embed(title=f"Command: {command.name}", color=discord.Color.gold())
                embed.description = command.help or getattr(command, 'description', None) or "No description available"
                usage = f"/{command.qualified_name}"
                if getattr(command, 'signature', None):
                    usage += f" {command.signature}"
                embed.add_field(name="Usage", value=f"`{usage}`")

                if getattr(ctx, 'interaction', None):
                    await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx.send(embed=embed)
                return

            cog_data = self.get_cog_data()
            if not cog_data:
                if getattr(ctx, 'interaction', None):
                    await ctx.interaction.response.send_message("No commands available.", ephemeral=True)
                else:
                    await ctx.send("No commands available.")
                return

            view = HelpView(self.bot, cog_data, ctx.author)
            embed = view.create_home_embed()
            
            # Send via interaction if available (slash command), otherwise normal message
            if getattr(ctx, 'interaction', None):
                msg = await ctx.send(embed=embed, view=view, ephemeral=True)
            else:
                msg = await ctx.send(embed=embed, view=view)

            # Store message reference for timeout handling
            view.message = msg

        except Exception as e:
            traceback.print_exc()
            if getattr(ctx, 'interaction', None):
                await ctx.interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
            else:
                await ctx.send(f"An error occurred: {str(e)}")


async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
