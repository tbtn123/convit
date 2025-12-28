import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import tempfile
import os
import json
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from utils.db_helpers import *
from utils.translation import translate as tr


logger = logging.getLogger(__name__)

CHILDREN_MAX = 5
PARTNERS_MAX = 2


class MarriageProposalView(discord.ui.View):
    def __init__(self, proposer_id: int, target_id: int, cog):
        super().__init__(timeout=300)
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.cog = cog
        self.accepted = False

    @discord.ui.button(label="Accept ", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(
                await tr("This proposal isn't for you!", interaction), ephemeral=True
            )

        self.accepted = True
        await interaction.response.defer()
        await self.cog._handle_marriage_accept(interaction, self.proposer_id, self.target_id)
        self.stop()

    @discord.ui.button(label="Decline ", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(
                await tr("This proposal isn't for you!", interaction), ephemeral=True
            )

        await interaction.response.edit_message(
            embed=discord.Embed(
                title=await tr("Proposal Declined", interaction),
                description=await tr("The marriage proposal has been declined.", interaction),
                color=discord.Color.red()
            ),
            view=None
        )
        self.stop()


class DivorceConfirmationView(discord.ui.View):
    def __init__(self, user_id: int, partner_id: int, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.partner_id = partner_id
        self.cog = cog

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                await tr("This confirmation is only for the command author.", interaction), ephemeral=True
            )
        await interaction.response.defer()
        await self.cog._handle_divorce_confirm(interaction, self.user_id, self.partner_id)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                await tr("This confirmation is only for the command author.", interaction), ephemeral=True
            )
        await interaction.edit_original_response(
            embed=discord.Embed(
                title=await tr("Cancelled", interaction),
                description=await tr("Divorce cancelled.", interaction),
                color=discord.Color.orange()
            ),
            view=None
        )
        self.stop()


class DisownConfirmationView(discord.ui.View):
    def __init__(self, user_id: int, child_id: int, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.child_id = child_id
        self.cog = cog

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                await tr("This confirmation is only for the command author.", interaction), ephemeral=True
            )
        await interaction.response.defer()
        await self.cog._handle_disown_confirm(interaction, self.user_id, self.child_id)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                await tr("This confirmation is only for the command author.", interaction), ephemeral=True
            )
        await interaction.edit_original_response(
            embed=discord.Embed(
                title=await tr("Cancelled", interaction),
                description=await tr("Disown cancelled.", interaction),
                color=discord.Color.orange()
            ),
            view=None
        )
        self.stop()


class LeaveParentsConfirmationView(discord.ui.View):
    def __init__(self, user_id: int, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.cog = cog

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                await tr("This confirmation is only for the command author.", interaction), ephemeral=True
            )
        await interaction.response.defer()
        await self.cog._handle_leave_parents_confirm(interaction, self.user_id)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                await tr("This confirmation is only for the command author.", interaction), ephemeral=True
            )
        await interaction.edit_original_response(
            embed=discord.Embed(
                title=await tr("Cancelled", interaction),
                description=await tr("Leave parents cancelled.", interaction),
                color=discord.Color.orange()
            ),
            view=None
        )
        self.stop()


class AdoptionProposalView(discord.ui.View):
    def __init__(self, adopter_id: int, target_id: int, cog):
        super().__init__(timeout=300)
        self.adopter_id = adopter_id
        self.target_id = target_id
        self.cog = cog
        self.accepted = False

    @discord.ui.button(label="Accept Adoption ", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(
                await tr("This adoption proposal isn't for you!", interaction), ephemeral=True
            )

        self.accepted = True
        await interaction.response.defer()
        await self.cog._handle_adoption_accept(interaction, self.adopter_id, self.target_id)
        self.stop()

    @discord.ui.button(label="Reject Adoption ", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(
                await tr("This adoption proposal isn't for you!", interaction), ephemeral=True
            )

        await interaction.response.edit_message(
            embed=discord.Embed(
                title=await tr("Adoption Rejected", interaction),
                description=await tr("The adoption proposal has been rejected.", interaction),
                color=discord.Color.red()
            ),
            view=None
        )
        self.stop()


class PartnerSelectView(discord.ui.View):
    def __init__(self, user_id: int, partners: list, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.partners = partners
        self.cog = cog

        options = []
        for partner_id in partners:
            try:
                partner_name = f"User {partner_id}"
                options.append(discord.SelectOption(
                    label=f"Partner {len(options) + 1}",
                    value=str(partner_id),
                    description=f"Select to divorce this partner"
                ))
            except:
                continue

        if options:
            select = PartnerSelect(options[:25])  # Discord limit of 25 options
            self.add_item(select)


class PartnerSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Choose a partner to divorce", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != int(self.view.user_id):
            return await interaction.response.send_message(
                await tr("This selection is not for you!", interaction), ephemeral=True
            )

        partner_id = int(self.values[0])
        await interaction.response.defer()
        try:
            await interaction.edit_original_response(view=None)
        except:
            pass
        await self.view.cog._handle_divorce_confirm(interaction, int(self.view.user_id), partner_id)


class ChildSelectView(discord.ui.View):
    def __init__(self, user_id: int, children: list, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.children = children
        self.cog = cog

        options = []
        for child_id in children:
            try:
                child_name = f"Child {len(options) + 1}"
                options.append(discord.SelectOption(
                    label=f"Child {len(options) + 1}",
                    value=str(child_id),
                    description=f"Select to disown this child"
                ))
            except:
                continue

        if options:
            select = ChildSelect(options[:25])  # Discord limit of 25 options
            self.add_item(select)


class ChildSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Choose a child to disown", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != int(self.view.user_id):
            return await interaction.response.send_message(
                await tr("This selection is not for you!", interaction), ephemeral=True
            )

        child_id = int(self.values[0])
        await interaction.response.defer()
        try:
            await interaction.edit_original_response(view=None)
        except:
            pass
        await self.view.cog._handle_disown_confirm(interaction, int(self.view.user_id), child_id)


class Relationship(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="marry", description="Propose marriage to another user")
    async def marry(self, ctx: commands.Context, target: discord.Member):
        await ctx.defer()

        if target.bot or target.id == ctx.author.id:
            return await ctx.reply(await tr("You cannot marry that user!", ctx))

        await ensure_relationship(self.bot.db, ctx.author.id)
        await ensure_relationship(self.bot.db, target.id)

        proposer_partners = await get_user_partners(self.bot.db, ctx.author.id)
        target_partners = await get_user_partners(self.bot.db, target.id)

        if len(proposer_partners) >= PARTNERS_MAX:
            return await ctx.reply(await tr(f"You can only have {PARTNERS_MAX} partners maximum!", ctx))

        if len(target_partners) >= PARTNERS_MAX:
            return await ctx.reply(await tr(f"Your target can only have {PARTNERS_MAX} partners maximum!", ctx))

        if target.id in proposer_partners:
            return await ctx.reply(await tr("You are already married to this person!", ctx))

        conflict, conflict_msg = await check_relationship_conflicts(self.bot.db, ctx.author.id, target.id)
        if conflict:
            return await ctx.reply(await tr(conflict_msg, ctx))

        embed = discord.Embed(
            title="<Marriage Proposal",
            description=f"{ctx.author.mention} has proposed marriage to {target.mention}!",
            color=discord.Color.pink()
        )
        embed.add_field(name="Proposal", value="Will you accept this marriage proposal?", inline=False)

        view = MarriageProposalView(ctx.author.id, target.id, self)
        await ctx.reply(embed=embed, view=view)

    async def _handle_marriage_accept(self, interaction: discord.Interaction, proposer_id: int, target_id: int):
        try:
            proposer_partners = await get_user_partners(self.bot.db, proposer_id)
            target_partners = await get_user_partners(self.bot.db, target_id)

            if len(proposer_partners) >= PARTNERS_MAX or len(target_partners) >= PARTNERS_MAX:
                return await interaction.followup.send(
                    await tr("One of you already has too many partners!", interaction), ephemeral=True
                )

            if target_id in proposer_partners:
                return await interaction.followup.send(
                    await tr("You are already married to this person!", interaction), ephemeral=True
                )

            conflict, conflict_msg = await check_relationship_conflicts(self.bot.db, proposer_id, target_id)
            if conflict:
                return await interaction.followup.send(
                    await tr(conflict_msg, interaction), ephemeral=True
                )

            marriage_date = datetime.now(timezone.utc)
            await add_partner(self.bot.db, proposer_id, target_id, marriage_date)

            embed = discord.Embed(
                title=":tada: Marriage Complete! :tada:",
                description="Congratulations to the happy couple! :heart:",
                color=discord.Color.gold()
            )

            try:
                proposer = await self.bot.fetch_user(proposer_id)
                target = await self.bot.fetch_user(target_id)
                embed.add_field(
                    name=":ring: Newlyweds :ring:",
                    value=f"{proposer.mention} + {target.mention}",
                    inline=False
                )
            except Exception as e:
                logger.warning(f"User fetch error in marriage completion: {e}")
                embed.add_field(
                    name=":ring: Newlyweds :ring:",
                    value=f"<@{proposer_id}> + <@{target_id}>",
                    inline=False
                )

            embed.add_field(
                name=":calendar: Married On",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=False
            )

            embed.add_field(
                name=":family: Relationship Status",
                value="Now married! Use `/relationships` to view your family tree.",
                inline=False
            )

            await interaction.edit_original_response(embed=embed, view=None)

            try:
                channel = interaction.channel
                celebration_emojis = ["🎉", "🎊", "💝", "🥂", "💍", "❤️"]
                random_emojis = "".join(random.choices(celebration_emojis, k=3))
                
                proposer_mention = f"<@{proposer_id}>"
                target_mention = f"<@{target_id}>"
                
                try:
                    proposer = await self.bot.fetch_user(proposer_id)
                    proposer_mention = proposer.mention
                except:
                    pass
                
                try:
                    target = await self.bot.fetch_user(target_id)
                    target_mention = target.mention
                except:
                    pass
                
                celebration_message = f"{random_emojis} **Marriage Celebration!** {random_emojis}\n"
                celebration_message += f"💍 {proposer_mention} and {target_mention} are now married! 💍"
                
                await channel.send(celebration_message)
            except Exception as e:
                logger.warning(f"Celebration send error: {e}")

        except Exception as e:
            logger.error(f"Marriage processing error: {e}")
            try:
                await interaction.followup.send(
                    await tr("An error occurred during marriage processing.", interaction), ephemeral=True
                )
            except:
                pass

    @commands.hybrid_command(name="adopt", description="Propose to adopt a user as your child")
    async def adopt(self, ctx: commands.Context, target: discord.Member):
        await ctx.defer()

        if target.bot or target.id == ctx.author.id:
            return await ctx.reply(await tr("You cannot adopt that user!", ctx))

        await ensure_relationship(self.bot.db, ctx.author.id)
        await ensure_relationship(self.bot.db, target.id)

        target_data = await get_relationship_data(self.bot.db, target.id)
        if target_data and target_data['father_id']:
            return await ctx.reply(await tr("This user already has a parent!", ctx))

        children = await get_user_children(self.bot.db, ctx.author.id)
        if len(children) >= CHILDREN_MAX:
            return await ctx.reply(await tr(f"You can only have {CHILDREN_MAX} children maximum!", ctx))

        conflict, conflict_msg = await check_relationship_conflicts(self.bot.db, ctx.author.id, target.id)
        if conflict:
            return await ctx.reply(await tr(conflict_msg, ctx))

        conflict, conflict_msg = await check_parent_conflicts(self.bot.db, target.id, ctx.author.id)
        if conflict:
            return await ctx.reply(await tr(conflict_msg, ctx))

        embed = discord.Embed(
            title=":family: Adoption Proposal",
            description=f"{ctx.author.mention} wants to adopt {target.mention} as their child!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Proposal", value=f"{target.mention}, do you accept this adoption?", inline=False)

        view = AdoptionProposalView(ctx.author.id, target.id, self)
        await ctx.reply(embed=embed, view=view)

    async def _handle_adoption_accept(self, interaction: discord.Interaction, adopter_id: int, target_id: int):
        try:
            target_data = await get_relationship_data(self.bot.db, target_id)
            if target_data and target_data['father_id']:
                return await interaction.followup.send(
                    await tr("This user already has a parent!", interaction), ephemeral=True
                )

            children = await get_user_children(self.bot.db, adopter_id)
            if len(children) >= CHILDREN_MAX:
                return await interaction.followup.send(
                    await tr(f"Adopter can only have {CHILDREN_MAX} children maximum!", interaction), ephemeral=True
                )

            conflict, conflict_msg = await check_relationship_conflicts(self.bot.db, adopter_id, target_id)
            if conflict:
                return await interaction.followup.send(
                    await tr(conflict_msg, interaction), ephemeral=True
                )

            conflict, conflict_msg = await check_parent_conflicts(self.bot.db, target_id, adopter_id)
            if conflict:
                return await interaction.followup.send(
                    await tr(conflict_msg, interaction), ephemeral=True
                )

            await add_child(self.bot.db, adopter_id, None, target_id)

            try:
                adopter = await self.bot.fetch_user(adopter_id)
                target = await self.bot.fetch_user(target_id)
                embed = discord.Embed(
                    title=":family: Adoption Complete!",
                    description=f"{adopter.mention} has successfully adopted {target.mention}!",
                    color=discord.Color.green()
                )
            except:
                embed = discord.Embed(
                    title=":family: Adoption Complete!",
                    description=f"<@{adopter_id}> has successfully adopted <@{target_id}>!",
                    color=discord.Color.green()
                )

            embed.add_field(
                name=":calendar: Adopted On",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=False
            )

            embed.add_field(
                name=":house: Family Status",
                value="Welcome to the family! Use `/relationships` to view your new family tree.",
                inline=False
            )

            await interaction.edit_original_response(embed=embed, view=None)

            try:
                channel = interaction.channel
                celebration_emojis = ["🎉", "🎊", "💝", "👨‍👩‍👧‍👦", "🏠", "❤️"]
                random_emojis = "".join(random.choices(celebration_emojis, k=3))
                
                adopter_mention = f"<@{adopter_id}>"
                target_mention = f"<@{target_id}>"
                
                try:
                    adopter = await self.bot.fetch_user(adopter_id)
                    adopter_mention = adopter.mention
                except:
                    pass
                
                try:
                    target = await self.bot.fetch_user(target_id)
                    target_mention = target.mention
                except:
                    pass
                
                celebration_message = f"{random_emojis} **Adoption Celebration!** {random_emojis}\n"
                celebration_message += f"🎉 {adopter_mention} has adopted {target_mention}! 🎉"
                
                await channel.send(celebration_message)
            except Exception as e:
                logger.warning(f"Adoption celebration error: {e}")

        except Exception as e:
            logger.error(f"Adoption processing error: {e}")
            try:
                await interaction.followup.send(
                    await tr("An error occurred during adoption processing.", interaction), ephemeral=True
                )
            except:
                pass

    @commands.hybrid_command(name="divorce", description="Select a partner to divorce from")
    async def divorce(self, ctx: commands.Context):
        await ctx.defer()

        await ensure_relationship(self.bot.db, ctx.author.id)
        partners = await get_user_partners(self.bot.db, ctx.author.id)

        if not partners:
            return await ctx.reply(await tr("You are not married to anyone!", ctx))

        if len(partners) == 1:
            partner_id = partners[0]
            try:
                partner = await self.bot.fetch_user(partner_id)
                embed = discord.Embed(
                    title="Divorce Confirmation",
                    description=f"Are you sure you want to divorce {partner.mention}?",
                    color=discord.Color.red()
                )
            except:
                embed = discord.Embed(
                    title="Divorce Confirmation",
                    description=f"Are you sure you want to divorce <@{partner_id}>?",
                    color=discord.Color.red()
                )

            embed.add_field(
                name="Warning",
                value="This action cannot be undone. Both partners will be removed from each other's relationship records.",
                inline=False
            )

            view = DivorceConfirmationView(ctx.author.id, partner_id, self)
            await ctx.reply(embed=embed, view=view)
        else:
            embed = discord.Embed(
                title="Select Partner to Divorce",
                description="Choose which partner you want to divorce from:",
                color=discord.Color.red()
            )

            view = PartnerSelectView(ctx.author.id, partners, self)
            await ctx.reply(embed=embed, view=view)

    async def _handle_divorce_confirm(self, interaction: discord.Interaction, user_id: int, partner_id: int):
        try:
            logger.info(f"User {user_id} is divorcing partner {partner_id}")
            await remove_partner(self.bot.db, user_id, partner_id)
            logger.info(f"Successfully divorced user {user_id} from partner {partner_id}")

            embed = discord.Embed(
                title=":broken_heart: Divorce Complete",
                description="The marriage has been dissolved.",
                color=discord.Color.red()
            )

            try:
                user = await self.bot.fetch_user(user_id)
                partner = await self.bot.fetch_user(partner_id)
                embed.add_field(
                    name="Former Couple",
                    value=f"{user.mention} ↔ {partner.mention}",
                    inline=False
                )
            except:
                embed.add_field(
                    name="Former Couple",
                    value=f"<@{user_id}> ↔ <@{partner_id}>",
                    inline=False
                )

            embed.add_field(
                name="Divorced On",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Divorce processing error: {e}")
            await interaction.followup.send(
                await tr("An error occurred during divorce processing.", interaction), ephemeral=True
            )

    @commands.hybrid_command(name="disown", description="Select a child to disown")
    async def disown(self, ctx: commands.Context):
        await ctx.defer()

        await ensure_relationship(self.bot.db, ctx.author.id)
        children = await get_user_children(self.bot.db, ctx.author.id)

        if not children:
            return await ctx.reply(await tr("You have no children to disown!", ctx))

        if len(children) == 1:
            child_id = children[0]
            try:
                child = await self.bot.fetch_user(child_id)
                embed = discord.Embed(
                    title="Disown Confirmation",
                    description=f"Are you sure you want to disown {child.mention}?",
                    color=discord.Color.red()
                )
            except:
                embed = discord.Embed(
                    title="Disown Confirmation",
                    description=f"Are you sure you want to disown <@{child_id}>?",
                    color=discord.Color.red()
                )

            embed.add_field(
                name="Warning",
                value="This action cannot be undone. The child will no longer be listed as your child.",
                inline=False
            )

            view = DisownConfirmationView(ctx.author.id, child_id, self)
            await ctx.reply(embed=embed, view=view)
        else:
            embed = discord.Embed(
                title="Select Child to Disown",
                description="Choose which child you want to disown:",
                color=discord.Color.red()
            )

            view = ChildSelectView(ctx.author.id, children, self)
            await ctx.reply(embed=embed, view=view)

    @commands.hybrid_command(name="leave-parents", description="Leave your parents (remove yourself as their child)")
    async def leave_parents(self, ctx: commands.Context):
        await ctx.defer()

        await ensure_relationship(self.bot.db, ctx.author.id)
        
        user_data = await get_relationship_data(self.bot.db, ctx.author.id)
        
        if not user_data or not user_data['father_id']:
            return await ctx.reply(await tr("You have no parent recorded!", ctx))

        parent_info = []
        try:
            parent = await self.bot.fetch_user(user_data['father_id'])
            parent_info.append(f" {parent.name}")
        except:
            parent_info.append(f" <@{user_data['father_id']}>")

        embed = discord.Embed(
            title="Leave Parent Confirmation",
            description=f"Are you sure you want to leave your parent?",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="Your Parent",
            value="\n".join(parent_info),
            inline=False
        )
        
        embed.add_field(
            name="Warning",
            value="This action cannot be undone. You will no longer be listed as their child.",
            inline=False
        )

        view = LeaveParentsConfirmationView(ctx.author.id, self)
        await ctx.reply(embed=embed, view=view)

    async def _handle_disown_confirm(self, interaction: discord.Interaction, user_id: int, child_id: int):
        try:
            logger.info(f"User {user_id} is disowning child {child_id}")
            await remove_child_relationship(self.bot.db, child_id)
            logger.info(f"Successfully disowned child {child_id} from user {user_id}")

            embed = discord.Embed(
                title="Disown Complete",
                description="The child relationship has been severed.",
                color=discord.Color.orange()
            )

            try:
                user = await self.bot.fetch_user(user_id)
                child = await self.bot.fetch_user(child_id)
                embed.add_field(
                    name="Former Parent-Child",
                    value=f"{user.mention} ↔ {child.mention}",
                    inline=False
                )
            except:
                embed.add_field(
                    name="Former Parent-Child",
                    value=f"<@{user_id}> ↔ <@{child_id}>",
                    inline=False
                )

            embed.add_field(
                name="Disowned On",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Disown processing error: {e}")
            await interaction.followup.send(
                await tr("An error occurred during disown processing.", interaction), ephemeral=True
            )

    async def _handle_leave_parents_confirm(self, interaction: discord.Interaction, user_id: int):
        try:
            logger.info(f"User {user_id} is leaving their parents")
            await remove_child_relationship(self.bot.db, user_id)
            logger.info(f"Successfully removed user {user_id} from their parents")

            embed = discord.Embed(
                title="Leave Parents Complete",
                description="You have successfully left your parents.",
                color=discord.Color.green()
            )

            try:
                user = await self.bot.fetch_user(user_id)
                embed.add_field(
                    name="You",
                    value=f"{user.mention}",
                    inline=False
                )
            except:
                embed.add_field(
                    name="You",
                    value=f"<@{user_id}>",
                    inline=False
                )

            embed.add_field(
                name="Left On",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=False
            )

            embed.add_field(
                name="Note",
                value="You are no longer listed as a child of your parent.",
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Leave parents processing error: {e}")
            await interaction.followup.send(
                await tr("An error occurred during leave parents processing.", interaction), ephemeral=True
            )

    @commands.hybrid_command(name="relationships", description="View relationship tree and information")
    async def relationships(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        await ctx.defer()

        if target is None:
            target = ctx.author

        await ensure_relationship(self.bot.db, target.id)

        try:
            data = await get_relationship_data(self.bot.db, target.id)
            partners = await get_user_partners(self.bot.db, target.id)
            children = await get_user_children(self.bot.db, target.id)

            embed = discord.Embed(
                title=f"Relationship Information",
                color=discord.Color.blue()
            )
            embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)

            if partners:
                partner_info = []
                for partner_id in partners:
                    try:
                        partner_user = await self.bot.fetch_user(partner_id)
                        partner_name = partner_user.name
                        marriage_date_obj = await get_marriage_date(self.bot.db, target.id, partner_id)
                        if marriage_date_obj:
                            if isinstance(marriage_date_obj, str):
                                try:
                                    dt = datetime.fromisoformat(marriage_date_obj.replace('Z', '+00:00'))
                                except:
                                    dt = datetime.now(timezone.utc)
                            else:
                                dt = marriage_date_obj
                            marriage_date = f"<t:{int(dt.timestamp())}:D>"
                        else:
                            marriage_date = "Unknown"
                        partner_info.append(f":ring: {partner_name} (since {marriage_date})")
                    except:
                        partner_info.append(f":ring: <@{partner_id}>")

                embed.add_field(
                    name="Partners",
                    value="\n".join(partner_info),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Partners",
                    value="No partners",
                    inline=False
                )

            if children:
                child_info = []
                for child_id in children:
                    try:
                        child_user = await self.bot.fetch_user(child_id)
                        child_info.append(f" {child_user.name}")
                    except:
                        child_info.append(f"<@{child_id}>")

                embed.add_field(
                    name=" Children",
                    value="\n".join(child_info),
                    inline=False
                )
            else:
                embed.add_field(
                    name=" Children",
                    value="No children",
                    inline=False
                )

            if data and data['father_id']:
                parent_info = []
                try:
                    parent_user = await self.bot.fetch_user(data['father_id'])
                    parent_info.append(f" {parent_user.name}")
                except:
                    parent_info.append(f" <@{data['father_id']}>")

                embed.add_field(
                    name=":family: Parent",
                    value="\n".join(parent_info),
                    inline=False
                )
            else:
                embed.add_field(
                    name=":family: Parent",
                    value="No parent recorded",
                    inline=False
                )

            await ctx.reply(embed=embed)

        except Exception as e:
            logger.error(f"Relationships command error: {e}")
            await ctx.reply(await tr("An error occurred retrieving relationship information.", ctx))





async def setup(bot):
    await bot.add_cog(Relationship(bot))
