import discord
from discord.ext import commands
from datetime import datetime, timezone


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
        self.author = author
        self.cog_data = cog_data
        # Sorted list of category names (excluding 'Home')
        self.cog_names = sorted(cog_data.keys())
        # Page size for select options (Home + up to 24 categories = 25 options max)
        self.page_size = 24
        self.page_index = 0

        # Main select (options are built from cog list and limited to Discord's 25-option limit)
        self.select = CategorySelect(self)
        self.add_item(self.select)

        # Navigation buttons to move between pages of categories

    def build_options_for_current_page(self):
        """Return a list of SelectOption for the current page. Always includes 'Home' first."""
        options = []
        # Home option
        options.append(discord.SelectOption(label="Home", description="View bot overview and statistics", value="home", default=True))

        start = self.page_index * self.page_size
        end = start + self.page_size
        page_cogs = self.cog_names[start:end]

        for cog_name in page_cogs:
            data = self.cog_data.get(cog_name, {})
            cmd_count = len(data.get('commands', []))
            options.append(discord.SelectOption(label=cog_name, description=f"{cmd_count} command{'s' if cmd_count != 1 else ''}", value=cog_name))

        return options

    def create_home_embed(self):
        total_commands = sum(len(data['commands']) for data in self.cog_data.values())
        total_categories = len(self.cog_data)

        # Calculate uptime
        try:
            if hasattr(self.bot, 'start_time') and self.bot.start_time:  # ensure attribute exists
                start_time = self.bot.start_time
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                uptime_delta = datetime.now(timezone.utc) - start_time
                hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = f"{hours}h {minutes}m {seconds}s"
            else:
                uptime_str = "Unknown"
        except Exception:
            uptime_str = "Unknown"

        description_lines = [
            "Welcome to the help menu! Use the dropdown below to explore different command categories.",
            "",
            "**Quick Stats**",
            f"Total Commands: {total_commands}",
            f"Categories: {total_categories}",
            f"Uptime: {uptime_str}",
            "",
            "**Categories Available:**",
        ]

        for name, data in sorted(self.cog_data.items()):
            description_lines.append(f"**{name}** - {len(data['commands'])} commands")

        embed = discord.Embed(title="Bot Help Menu", description="\n".join(description_lines), color=discord.Color.blue())
        embed.set_footer(text="Select a category from the dropdown menu below")

        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        return embed

    def create_category_embed(self, category):
        data = self.cog_data.get(category, {})
        commands_list = data.get('commands', [])
        description = data.get('description') or f"All commands in the {category} category"

        embed = discord.Embed(title=f"{category} Commands", description=description, color=discord.Color.green())

        sorted_commands = sorted(commands_list, key=lambda c: c.name)

        for cmd in sorted_commands:
            # Build signature
            if hasattr(cmd, 'qualified_name'):
                signature = f"/{cmd.qualified_name}"
                if getattr(cmd, 'signature', None):
                    signature += f" {cmd.signature}"
            else:
                signature = cmd.name

            cmd_help = getattr(cmd, 'help', None) or getattr(cmd, 'description', None) or "No description available"

            aliases_str = ""
            if hasattr(cmd, 'aliases') and cmd.aliases:
                aliases_str = f"\nAliases: {', '.join(cmd.aliases)}"

            embed.add_field(name=f"`{signature}`", value=f"{cmd_help}{aliases_str}", inline=False)

        embed.set_footer(text=f"Category: {category} | {len(sorted_commands)} commands")
        return embed

    async def handle_selection(self, interaction: discord.Interaction, selected: str):
        # Only allow the user who invoked the help menu to interact
        if interaction.user != self.author:
            await interaction.response.send_message("This help menu is not for you! Use /help to get your own.", ephemeral=True)
            return

        # Update default selection
        for option in self.select.options:
            option.default = (option.value == selected)

        if selected == "home":
            embed = self.create_home_embed()
        else:
            embed = self.create_category_embed(selected)

        # Edit message with new embed and updated view
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("This help menu is not for you! Use /help to get your own.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous Page", style=discord.ButtonStyle.secondary, custom_id="help_prev", row=1)
    async def previous_page_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Move to previous page if possible
        if self.page_index > 0:
            self.page_index -= 1
            # rebuild select options
            self.select.options = self.build_options_for_current_page()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("You're already on the first page.", ephemeral=True)

    @discord.ui.button(label="Next Page", style=discord.ButtonStyle.secondary, custom_id="help_next", row=1)
    async def next_page_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        max_index = (len(self.cog_names) - 1) // self.page_size
        if self.page_index < max_index:
            self.page_index += 1
            self.select.options = self.build_options_for_current_page()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("You're already on the last page.", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="help_close", row=1)
    async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Help menu closed.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        # try to edit the message to disable the view; ignore failures
        try:
            # attempt to find the original message and edit it; when the view times out it's usually fine to just stop
            pass
        finally:
            self.stop()


class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_cog_data(self):
        cog_data = {}
        for cog_name, cog in self.bot.cogs.items():
            # skip this help cog to avoid recursive listing
            if cog_name == self.__class__.__name__ or cog_name.lower() == 'help':
                continue

            cog_commands = [cmd for cmd in self.bot.commands if cmd.cog_name == cog_name and not cmd.hidden]
            if cog_commands:
                cog_data[cog_name] = {
                    'commands': cog_commands,
                    'description': self.get_cog_description(cog_name, cog)
                }
        return cog_data

    def get_cog_description(self, cog_name, cog):
        if hasattr(cog, 'description') and cog.description:
            return cog.description

        descriptions = {
            'Admin': 'Administrative commands for server management',
            'Economy': 'Manage your virtual economy and currency',
            'Mining': 'Mine resources and upgrade your equipment',
            'Shop': 'Buy and sell items in the marketplace',
            'Items': 'View and manage your inventory',
            'Farm': 'Grow crops and manage your farm',
            'Crafting': 'Craft items from resources',
            'Market': 'Trade items with other players',
            'Blackjack': 'Play blackjack and gamble your coins',
            'Relationships': 'Build relationships with other players',
            'RpgAdventure': 'Embark on RPG adventures',
            'RpgMisc': 'Miscellaneous RPG commands',
            'TradeQuests': 'Complete trade quests for rewards',
            'Giftcode': 'Redeem gift codes for rewards',
            'Misc': 'Miscellaneous utility commands',
            'Custom': 'Custom server commands',
            'Locale': 'Change language and localization settings'
        }

        return descriptions.get(cog_name, f'Commands for {cog_name}')

    @commands.hybrid_command(name="help", description="Display the help menu with all available commands")
    async def help(self, ctx, command_name: str = None):
        """Display an interactive help menu with dropdown category selection."""
        try:
            # If specific command requested, show single command help
            if command_name:
                command = self.bot.get_command(command_name)
                if not command:
                    if getattr(ctx, 'interaction', None):
                        await ctx.interaction.response.send_message(f"Command `{command_name}` not found.", ephemeral=True)
                    else:
                        await ctx.send(f"Command `{command_name}` not found.")
                    return

                if hasattr(command, 'qualified_name'):
                    signature = f"/{command.qualified_name}"
                    if getattr(command, 'signature', None):
                        signature += f" {command.signature}"
                else:
                    signature = command.name

                embed = discord.Embed(title=f"Command: {command.name}", description=command.help or getattr(command, 'description', None) or "No description available", color=discord.Color.gold())
                embed.add_field(name="Usage", value=f"`{signature}`", inline=False)
                if hasattr(command, 'aliases') and command.aliases:
                    embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)
                embed.set_footer(text=f"Category: {command.cog_name or 'Uncategorized'}")

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
            home_embed = view.create_home_embed()

            # Send via interaction if available (slash command), otherwise normal message
            if getattr(ctx, 'interaction', None):
                await ctx.interaction.response.send_message(embed=home_embed, view=view, ephemeral=True)
            else:
                await ctx.send(embed=home_embed, view=view)

        except Exception as e:
            # Print traceback server-side and send a simple error message to user
            import traceback
            traceback.print_exc()
            if getattr(ctx, 'interaction', None):
                await ctx.interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
            else:
                await ctx.send(f"An error occurred: {str(e)}")


async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
