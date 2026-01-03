import discord
from discord.ext import commands
from datetime import datetime, timezone
import traceback


class CategorySelect(discord.ui.Select):
    def __init__(self, bot, cog_data, author):
        self.bot = bot
        self.cog_data = cog_data
        self.author = author
        
        # Create options list with Home + all categories
        options = [
            discord.SelectOption(
                label="Home",
                description="View bot overview and statistics",
                value="home",
                default=True
            )
        ]
        
        # Add category options
        for cog_name, data in sorted(cog_data.items()):
            cmd_count = len(data['commands'])
            options.append(
                discord.SelectOption(
                    label=cog_name,
                    description=f"{cmd_count} command{'s' if cmd_count != 1 else ''} available",
                    value=cog_name
                )
            )
        
        super().__init__(
            placeholder="Select a category to view commands...",
            options=options,
            row=0
        )
    
    def create_home_embed(self):
        """Creates the home page embed with bot statistics."""
        total_commands = sum(len(data['commands']) for data in self.cog_data.values())
        total_categories = len(self.cog_data)
        
        # Calculate uptime
        try:
            if hasattr(self.bot, 'start_time'):
                start_time = self.bot.start_time
                # Make sure both datetimes are timezone-aware
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                
                uptime_delta = datetime.now(timezone.utc) - start_time
                hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = f"{hours}h {minutes}m {seconds}s"
            else:
                uptime_str = "Unknown"
        except Exception as e:
            print(f"Error calculating uptime: {e}")
            uptime_str = "Unknown"
        
        embed = discord.Embed(
            title="Bot Help Menu",
            description=(
                "Welcome to the help menu! Use the dropdown below to explore different command categories.\n\n"
                "**Quick Stats**\n"
                f"Total Commands: {total_commands}\n"
                f"Categories: {total_categories}\n"
                f"Uptime: {uptime_str}\n\n"
                "**Categories Available:**\n"
                + "\n".join(f"**{name}** - {len(data['commands'])} commands" 
                          for name, data in sorted(self.cog_data.items()))
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Select a category from the dropdown menu below")
        
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        return embed
    
    def create_category_embed(self, category):
        """Creates an embed for a specific category."""
        data = self.cog_data[category]
        commands_list = data['commands']
        description = data['description']
        
        embed = discord.Embed(
            title=f"{category} Commands",
            description=description or f"All commands in the {category} category",
            color=discord.Color.green()
        )
        
        # Sort commands alphabetically
        sorted_commands = sorted(commands_list, key=lambda c: c.name)
        
        # Add each command as a field
        for cmd in sorted_commands:
            # Get command signature
            if hasattr(cmd, 'qualified_name'):
                signature = f"/{cmd.qualified_name}"
                if cmd.signature:
                    signature += f" {cmd.signature}"
            else:
                signature = f"{cmd.name}"
            
            # Get command description
            cmd_help = cmd.help or cmd.description or "No description available"
            
            # Add aliases if available
            aliases_str = ""
            if hasattr(cmd, 'aliases') and cmd.aliases:
                aliases_str = f"\nAliases: {', '.join(cmd.aliases)}"
            
            embed.add_field(
                name=f"`{signature}`",
                value=f"{cmd_help}{aliases_str}",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category} | {len(sorted_commands)} commands")
        return embed
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message(
                "This help menu is not for you! Use /help to get your own.",
                ephemeral=True
            )
            return
        
        selected = self.values[0]
        
        # Update default selection in dropdown
        for option in self.options:
            option.default = (option.value == selected)
        
        # Create appropriate embed
        if selected == "home":
            embed = self.create_home_embed()
        else:
            embed = self.create_category_embed(selected)
        
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot, cog_data, author):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.add_item(CategorySelect(bot, cog_data, author))
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message(
                "This help menu is not for you! Use /help to get your own.",
                ephemeral=True
            )
            return False
        return True
    
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
        """Gather all cogs and their commands."""
        cog_data = {}
        
        for cog_name, cog in self.bot.cogs.items():
            # Skip help cog itself
            if cog_name == "HelpCommand":
                continue
            
            # Get all commands from this cog
            cog_commands = [
                cmd for cmd in self.bot.commands 
                if cmd.cog_name == cog_name and not cmd.hidden
            ]
            
            if cog_commands:
                cog_data[cog_name] = {
                    'commands': cog_commands,
                    'description': getattr(cog, 'description', f"Commands for {cog_name}")
                }
        
        return cog_data
    
    def get_cog_description(self, cog_name, cog):
        """Get description for a cog."""
        if hasattr(cog, 'description') and cog.description:
            return cog.description
        
        # Default descriptions for common cogs
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
        try:
            if command_name:
                command = self.bot.get_command(command_name)
                if not command:
                    await ctx.send(f"Command `{command_name}` not found.", ephemeral=True)
                    return
                
                # Create single command embed
                if hasattr(command, 'qualified_name'):
                    signature = f"/{command.qualified_name}"
                    if command.signature:
                        signature += f" {command.signature}"
                else:
                    signature = command.name
                
                embed = discord.Embed(
                    title=f"Command: {command.name}",
                    description=command.help or command.description or "No description available",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Usage", value=f"`{signature}`", inline=False)
                
                if hasattr(command, 'aliases') and command.aliases:
                    embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)
                
                embed.set_footer(text=f"Category: {command.cog_name or 'Uncategorized'}")
                
                await ctx.send(embed=embed)
                return
            
            # Get all cog data
            cog_data = self.get_cog_data()
            
            if not cog_data:
                await ctx.send("No commands available.", ephemeral=True)
                return
            
            # Create view with dropdown
            view = HelpView(self.bot, cog_data, ctx.author)
            
            # Create and send home embed
            select = view.children[0]
            home_embed = select.create_home_embed()
            
            await ctx.send(embed=home_embed, view=view)
        except Exception as e:
            print(f"Error in help command: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
