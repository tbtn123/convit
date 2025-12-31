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
import graphviz
import graphviz_static
from utils.db_helpers import *
from utils.translation import translate as tr
from utils.datetime_helpers import utc_now, ensure_utc, format_discord_timestamp


logger = logging.getLogger(__name__)


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

        logger.info(
            "Marriage accepted",
            extra={"proposer": self.proposer_id, "target": self.target_id}
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

        logger.info(
            "Marriage declined",
            extra={"proposer": self.proposer_id, "target": self.target_id}
        )

        await interaction.response.edit_message(
            embed=discord.Embed(
                title=await tr("Proposal Declined", interaction),
                description=await tr(
                    "The marriage proposal has been declined.",
                    interaction
                ),
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

        logger.info(f"User {self.target_id} accepted adoption proposal from {self.adopter_id}")
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

        logger.info(f"User {self.target_id} rejected adoption proposal from {self.adopter_id}")
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
    def __init__(self, user_id: int, partners: list, cog, bot):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.partners = partners
        self.cog = cog
        self.bot = bot

    async def create_options(self):
        options = []
        for i, partner_id in enumerate(self.partners):
            try:
                partner = await self.bot.fetch_user(partner_id)
                partner_name = partner.name[:20]
                options.append(discord.SelectOption(
                    label=f"{partner_name}",
                    value=str(partner_id),
                    description=f"Married - Click to divorce"
                ))
            except:
                options.append(discord.SelectOption(
                    label=f"User {partner_id}",
                    value=str(partner_id),
                    description=f"Click to divorce"
                ))

        if options:
            select = PartnerSelect(options[:25])
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
    def __init__(self, user_id: int, children: list, cog, bot):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.child_ids = children
        self.cog = cog
        self.bot = bot

    async def create_options(self):
        options = []
        for i, child_id in enumerate(self.child_ids):
            try:
                child = await self.bot.fetch_user(child_id)
                child_name = child.name[:20]  # Truncate long names
                options.append(discord.SelectOption(
                    label=f"{child_name}",
                    value=str(child_id),
                    description=f"Child - Click to disown"
                ))
            except:
                options.append(discord.SelectOption(
                    label=f"Child {i + 1}",
                    value=str(child_id),
                    description=f"Click to disown"
                ))

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

    def _get_user_friendly_error(self, error_msg: str) -> str:
        """Convert database error messages to user-friendly messages"""
        error_mappings = {
            'self_marriage_prohibited': "You cannot marry yourself!",
            'already_married': "You are already married to this person!",
            'siblings_prohibited': "You cannot marry your sibling!",
            'incest_prohibited': "You cannot marry a family member!",
            'too_closely_related': "You are too closely related to marry!",
            'self_parenting_prohibited': "You cannot adopt yourself!",
            'spouse_parenting_prohibited': "You cannot adopt your spouse!",
            'genealogical_paradox': "This adoption would create a family tree paradox!",
            'cannot_adopt_spouse': "You cannot adopt your spouse!",
            'would_create_genealogical_loop': "This adoption would create a family tree loop!"
        }
        
        # Extract the actual error from PostgreSQL exception format
        if ':' in error_msg:
            error_key = error_msg.split(':')[-1].strip()
        else:
            error_key = error_msg.strip()
            
        return error_mappings.get(error_key, f"Database error: {error_key}")

    @commands.hybrid_command(name="marry", description="Propose marriage to another user")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def marry(self, ctx: commands.Context, target: discord.Member):
        await ctx.defer()

        logger.info(f"User {ctx.author.id} ({ctx.author.name}) attempting to marry user {target.id} ({target.name}) in guild {ctx.guild.id}")

        if target.bot or target.id == ctx.author.id:
            logger.warning(f"Invalid marriage target: bot={target.bot}, self={target.id == ctx.author.id}")
            return await ctx.reply(await tr("You cannot marry that user!", ctx))

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        proposer_partners = await get_user_partners(self.bot.db, ctx.author.id)
        target_partners = await get_user_partners(self.bot.db, target.id)

        if len(proposer_partners) >= PARTNERS_MAX:
            logger.warning(f"User {ctx.author.id} has too many partners ({len(proposer_partners)}/{PARTNERS_MAX})")
            return await ctx.reply(await tr(f"You can only have {PARTNERS_MAX} partners maximum!", ctx))

        if len(target_partners) >= PARTNERS_MAX:
            logger.warning(f"Target {target.id} has too many partners ({len(target_partners)}/{PARTNERS_MAX})")
            return await ctx.reply(await tr(f"Your target can only have {PARTNERS_MAX} partners maximum!", ctx))

        if target.id in proposer_partners:
            logger.warning(f"Users {ctx.author.id} and {target.id} are already married")
            return await ctx.reply(await tr("You are already married to this person!", ctx))

        # Pre-check for relationship conflicts
        try:
            conflict, conflict_msg = await check_relationship_conflicts(self.bot.db, ctx.author.id, target.id)
            if conflict:
                user_friendly_msg = self._get_user_friendly_error(conflict_msg)
                return await ctx.reply(await tr(user_friendly_msg, ctx))
        except Exception as e:
            logger.error(f"Error checking relationship conflicts: {e}")
            return await ctx.reply(await tr("An error occurred while checking relationship compatibility.", ctx))

        logger.info(f"Marriage proposal sent from {ctx.author.id} to {target.id}")
        embed = discord.Embed(
            title="💍 Marriage Proposal",
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

            try:
                await add_partner(self.bot.db, proposer_id, target_id)
            except asyncpg.PostgresError as e:
                error_msg = self._get_user_friendly_error(str(e))
                return await interaction.followup.send(
                    await tr(f"Cannot complete marriage: {error_msg}", interaction), ephemeral=True
                )
            except Exception as e:
                logger.error(f"Unexpected error during marriage: {e}")
                return await interaction.followup.send(
                    await tr("An unexpected error occurred during marriage processing.", interaction), ephemeral=True
                )

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
                value=format_discord_timestamp(utc_now()),
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
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def adopt(self, ctx: commands.Context, target: discord.Member):
        await ctx.defer()

        logger.info(f"User {ctx.author.id} ({ctx.author.name}) attempting to adopt user {target.id} ({target.name}) in guild {ctx.guild.id}")

        if target.bot or target.id == ctx.author.id:
            logger.warning(f"Invalid adoption target: bot={target.bot}, self={target.id == ctx.author.id}")
            return await ctx.reply(await tr("You cannot adopt that user!", ctx))

        await ensure_user(self.bot.db, ctx.author.id)
        await ensure_user(self.bot.db, target.id)

        # Check if child already has maximum parents (2)
        target_parents = await get_parents(self.bot.db, target.id)
        if len(target_parents) >= 2:  # Allow up to 2 parents
            return await ctx.reply(await tr("This user already has the maximum number of parents (2)!", ctx))

        children = await get_user_children(self.bot.db, ctx.author.id)
        if len(children) >= CHILDREN_MAX:
            logger.warning(f"User {ctx.author.id} has too many children ({len(children)}/{CHILDREN_MAX})")
            return await ctx.reply(await tr(f"You can only have {CHILDREN_MAX} children maximum!", ctx))

        # Pre-check for adoption conflicts
        try:
            conflict, conflict_msg = await check_parent_conflicts(self.bot.db, target.id, ctx.author.id)
            if conflict:
                user_friendly_msg = self._get_user_friendly_error(conflict_msg)
                return await ctx.reply(await tr(user_friendly_msg, ctx))
        except Exception as e:
            logger.error(f"Error checking parent conflicts: {e}")
            return await ctx.reply(await tr("An error occurred while checking adoption compatibility.", ctx))

        logger.info(f"Adoption proposal sent from {ctx.author.id} to {target.id}")
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
            children = await get_user_children(self.bot.db, adopter_id)
            if len(children) >= CHILDREN_MAX:
                return await interaction.followup.send(
                    await tr(f"Adopter can only have {CHILDREN_MAX} children maximum!", interaction), ephemeral=True
                )

            # Check if child already has maximum parents
            target_parents = await get_parents(self.bot.db, target_id)
            if len(target_parents) >= 2:
                return await interaction.followup.send(
                    await tr("This user already has the maximum number of parents (2)!", interaction), ephemeral=True
                )

            try:
                await add_child(self.bot.db, adopter_id, target_id)
            except asyncpg.PostgresError as e:
                error_msg = self._get_user_friendly_error(str(e))
                return await interaction.followup.send(
                    await tr(f"Cannot complete adoption: {error_msg}", interaction), ephemeral=True
                )
            except Exception as e:
                logger.error(f"Unexpected error during adoption: {e}")
                return await interaction.followup.send(
                    await tr("An unexpected error occurred during adoption processing.", interaction), ephemeral=True
                )

            logger.info(f"Adoption completed between adopter {adopter_id} and child {target_id}")

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
                value=format_discord_timestamp(utc_now()),
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
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def divorce(self, ctx: commands.Context):
        await ctx.defer()

        logger.info(f"User {ctx.author.id} ({ctx.author.name}) initiating divorce in guild {ctx.guild.id}")
        await ensure_user(self.bot.db, ctx.author.id)
        partners = await get_user_partners(self.bot.db, ctx.author.id)

        if not partners:
            logger.info(f"User {ctx.author.id} has no partners to divorce")
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

            view = PartnerSelectView(ctx.author.id, partners, self, self.bot)
            await view.create_options()
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
                value=format_discord_timestamp(utc_now()),
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Divorce processing error: {e}")
            await interaction.followup.send(
                await tr("An error occurred during divorce processing.", interaction), ephemeral=True
            )

    @commands.hybrid_command(name="disown", description="Select a child to disown")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def disown(self, ctx: commands.Context):
        await ctx.defer()

        logger.info(f"User {ctx.author.id} ({ctx.author.name}) initiating disown in guild {ctx.guild.id}")
        await ensure_user(self.bot.db, ctx.author.id)
        children = await get_user_children(self.bot.db, ctx.author.id)

        if not children:
            logger.info(f"User {ctx.author.id} has no children to disown")
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

            view = ChildSelectView(ctx.author.id, children, self, self.bot)
            await view.create_options()
            await ctx.reply(embed=embed, view=view)

    @commands.hybrid_command(name="leave-parents", description="Leave your parents (remove yourself as their child)")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def leave_parents(self, ctx: commands.Context):
        await ctx.defer()

        logger.info(f"User {ctx.author.id} ({ctx.author.name}) attempting to leave parents in guild {ctx.guild.id}")
        await ensure_user(self.bot.db, ctx.author.id)

        parent_id = await get_parent(self.bot.db, ctx.author.id)
        if not parent_id:
            return await ctx.reply(await tr("You have no parent recorded!", ctx))

        parent_info = []
        try:
            parent = await self.bot.fetch_user(parent_id)
            parent_info.append(f" {parent.name}")
        except:
            parent_info.append(f" <@{parent_id}>")

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
                value=format_discord_timestamp(utc_now()),
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
                value=format_discord_timestamp(utc_now()),
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

        await ensure_user(self.bot.db, target.id)

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
                        marriage_date = format_discord_timestamp(ensure_utc(marriage_date_obj), "D")
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

            parent_ids = await get_parents(self.bot.db, target.id)
            if parent_ids:
                parent_info = []
                for parent_id in parent_ids:
                    try:
                        parent_user = await self.bot.fetch_user(parent_id)
                        parent_info.append(f"👨‍👩‍👧‍👦 {parent_user.name}")
                    except:
                        parent_info.append(f"👨‍👩‍👧‍👦 <@{parent_id}>")

                embed.add_field(
                    name=":family: Parents",
                    value="\n".join(parent_info),
                    inline=False
                )
            else:
                embed.add_field(
                    name=":family: Parents",
                    value="No parents recorded",
                    inline=False
                )

            await ctx.reply(embed=embed)

        except Exception as e:
            logger.error(f"Relationships command error: {e}")
            await ctx.reply(await tr("An error occurred retrieving relationship information.", ctx))

    @commands.hybrid_command(name="family-tree", description="View your family tree as a visual graph")
    async def family_tree(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        await ctx.defer()

        if target is None:
            target = ctx.author

        await ensure_user(self.bot.db, target.id)

        try:
            family_data = await get_all_family_members(self.bot.db, target.id, max_generations=5)

            if not family_data:
                return await ctx.reply(await tr("No family data found.", ctx))

            dot = graphviz.Digraph(comment='Family Tree', format='png')
            dot.attr(rankdir='TB', size='10,10')

            user_names = {}
            for member in family_data:
                try:
                    user = await self.bot.fetch_user(member['id'])
                    user_names[member['id']] = user.name[:20]
                except:
                    user_names[member['id']] = f"User {member['id']}"

            # Group members by generation for rank constraints
            generations = {}
            for member in family_data:
                gen = member['generation']
                if gen not in generations:
                    generations[gen] = []
                generations[gen].append(member['id'])

            # Create nodes
            for member in family_data:
                user_id = member['id']
                user_name = user_names[user_id]

                if member['generation'] == 0:
                    dot.node(str(user_id), user_name, shape='box', style='filled', fillcolor='lightblue')
                elif member['generation'] < 0:
                    dot.node(str(user_id), user_name, shape='ellipse', style='filled', fillcolor='lightgreen')
                else:
                    dot.node(str(user_id), user_name, shape='ellipse', style='filled', fillcolor='lightyellow')

            # Add rank constraints to keep generations at same level
            for gen, member_ids in generations.items():
                if len(member_ids) > 1:
                    with dot.subgraph() as s:
                        s.attr(rank='same')
                        for member_id in member_ids:
                            s.node(str(member_id))

            # Add parent-child edges
            for member in family_data:
                for parent_id in member['parents']:  # Handle multiple parents
                    if parent_id:
                        dot.edge(str(parent_id), str(member['id']))

            # Add marriage edges
            for member in family_data:
                for partner_id in member['partners']:
                    if partner_id > member['id']:  # Only add edge once per couple
                        dot.edge(str(member['id']), str(partner_id), style='dashed', color='red', arrowhead='none', label='Married')

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_file_path = os.path.join(tmp_dir, 'family_tree.png')
                try:
                    dot.render(tmp_file_path.replace('.png', ''), format='png', cleanup=True)

                    embed = discord.Embed(
                        title=f"Family Tree for {target.display_name}",
                        color=discord.Color.blue()
                    )
                    embed.set_image(url="attachment://family_tree.png")

                    file = discord.File(tmp_file_path, filename="family_tree.png")
                    await ctx.reply(embed=embed, file=file)
                finally:
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)

        except Exception as e:
            logger.error(f"Family tree command error: {e}")
            await ctx.reply(await tr("An error occurred generating the family tree.", ctx))



    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            try:
                msg = await tr(f"Please wait {round(error.retry_after, 1)} seconds before using this relationship command again.", ctx)
                if ctx.interaction and ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(msg, ephemeral=True)
                else:
                    await ctx.reply(msg, ephemeral=True)
            except discord.errors.NotFound:
                pass
            except Exception as e:
                logger.error(f"Failed to send cooldown message: {e}")
            return
        logger.error(f"Relationship command error: {type(error).__name__}: {error}")


async def setup(bot):
    await bot.add_cog(Relationship(bot))
