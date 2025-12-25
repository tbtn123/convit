import discord
from discord.ext import commands


class HelpView(discord.ui.View):
    def __init__(self, pages, author):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0
        self.author = author
        self.update_buttons()

    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        total = len(self.pages)
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index == total - 1

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Help menu closed.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        """Disable all buttons when timeout occurs."""
        for item in self.children:
            item.disabled = True
        self.stop()


class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.per_page = 5

    def get_command_signature(self, command):
        return f"`/{command.qualified_name} {command.signature}`" if hasattr(command, "qualified_name") else f"`{command.name}`"

    def get_category_pages(self, commands, category_name):
        pages = []
        command_list = sorted(commands, key=lambda c: c.name)
        total = len(command_list)

        for i in range(0, total, self.per_page):
            embed = discord.Embed(
                title=f"{category_name} Commands",
                color=discord.Color.blurple(),
                description=f"Showing commands from order {i+1} to {min(i+self.per_page, total)} of {total}.",
            )
            for command in command_list[i:i + self.per_page]:
                signature = self.get_command_signature(command)
                aliases = f"**Aliases:** {', '.join(command.aliases)}\n" if command.aliases else ""
                embed.add_field(
                    name=signature,
                    value=f"{command.help or 'No description available.'}\n{aliases}",
                    inline=False,
                )
            embed.set_footer(text=f"Page {len(pages)+1}/{(total-1)//self.per_page + 1}")
            pages.append(embed)

        return pages

    @commands.hybrid_command(name="help", description="Shows detailed help information.")
    async def help(self, ctx, command_name: str = None):
        if command_name:
            command = self.bot.get_command(command_name)
            if not command:
                await ctx.send("That command doesn't exist.")
                return

            embed = discord.Embed(
                title=f"Command: {command.name}",
                description=command.help or "No description available.",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Usage", value=self.get_command_signature(command), inline=False)
            if command.aliases:
                embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)
            embed.set_footer(text=f"Category: {command.cog_name or 'Uncategorized'}")
            await ctx.send(embed=embed)
            return

        # Group by cogs
        cog_commands = {}
        for cmd in self.bot.commands:
            if not cmd.hidden:
                cog_commands.setdefault(cmd.cog_name or "Uncategorized", []).append(cmd)

        all_pages = []
        for cog_name, cmds in cog_commands.items():
            all_pages.extend(self.get_category_pages(cmds, cog_name))

        if not all_pages:
            await ctx.send("No commands available.")
            return

        view = HelpView(all_pages, ctx.author)
        await ctx.send(embed=all_pages[0], view=view)


async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
