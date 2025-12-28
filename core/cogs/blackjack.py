import random
import discord
from discord.ext import commands
from discord.ui import View, Button
from utils.db_helpers import *
import logging

logger = logging.getLogger(__name__)

# ====== Card + Deck Helpers ======
suits = ["♠", "♥", "♦", "♣"]
suits_emoji = [":spades:", ":heart:", ":diamonds:", ":clubs:"]
ranks = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5,
    "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 10, "Q": 10, "K": 10
}


def create_deck():
    deck = []
    rank_list = list(ranks.keys())
    for i in range(len(rank_list)):
        rank = rank_list[i]
        for j in range(len(suits)):
            suit = suits[j]
            emoji = suits_emoji[j]
            deck.append((rank, suit, emoji))
    return deck


def card_value(card):
    return ranks[card[0]]


def hand_value(hand):
    value = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value


def format_hand(hand):
    card_line = " ".join([f"`{r}{s}`" for r, s, e in hand])
    return card_line


# ====== Blackjack Gameplay View ======
class BlackjackView(View):
    def __init__(self, bot, ctx, bet, deck, player_hand, dealer_hand):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.bet = bet
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand

    def build_embed(self, result: str | None = None):
        embed = discord.Embed(
            title="Blackjack Game",
            color=discord.Color.blue()
        )

        player_val = hand_value(self.player_hand)
        embed.add_field(
            name=f"User Hand — Total: {player_val}",
            value=format_hand(self.player_hand),
            inline=False
        )

        if result is None:
            # Show dealer's first card only
            dealer_hidden = [(self.dealer_hand[0][0], self.dealer_hand[0][1], self.dealer_hand[0][2])]
            embed.add_field(
                name="Dealer Hand — Status: Hidden",
                value=format_hand(dealer_hidden) + " `??`",
                inline=False
            )
        else:
            dealer_val = hand_value(self.dealer_hand)
            embed.add_field(
                name=f"Dealer Hand — Total: {dealer_val}",
                value=format_hand(self.dealer_hand),
                inline=False
            )

        if result:
            embed.add_field(name="Outcome", value=f"{result}", inline=False)

        embed.set_footer(text="Hit: Draw card • Stand: End turn")
        return embed

    async def update_message(self, interaction):
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    async def end_game(self, interaction, result: str, payout: int = 0):
        user_id = self.ctx.author.id

        if payout > 0:
            async with self.bot.db.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET coins = coins + $1 WHERE id = $2",
                    payout, user_id
                )

        await interaction.edit_original_response(
            embed=self.build_embed(result),
            view=None
        )
        self.stop()

    # -------- Hit --------
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Error: Unauthorized. This game belongs to another user.", ephemeral=True)

        await interaction.response.defer()

        self.player_hand.append(self.deck.pop())
        if hand_value(self.player_hand) > 21:
            await self.end_game(interaction, f"Status: Bust\nOutcome: Loss\nAmount: -{self.bet} coins", payout=0)
        else:
            await self.update_message(interaction)

    # -------- Stand --------
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Error: Unauthorized. This game belongs to another user.", ephemeral=True)

        await interaction.response.defer()

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())

        player_val = hand_value(self.player_hand)
        dealer_val = hand_value(self.dealer_hand)

        if dealer_val > 21 or player_val > dealer_val:
            await self.end_game(interaction, f"Status: Victory\nPayout: +{self.bet} coins\nNet: +{self.bet} coins", payout=self.bet * 2)
        elif dealer_val == player_val:
            await self.end_game(interaction, f"Status: Draw\nPayout: {self.bet} coins returned\nNet: 0 coins", payout=self.bet)
        else:
            await self.end_game(interaction, f"Status: Defeat\nOutcome: Loss\nNet: -{self.bet} coins", payout=0)


# ====== Cog ======
class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="blackjack", description="Play blackjack with coins", aliases = ["bj"])
    async def blackjack(self, ctx: commands.Context, bet: int):
        if bet <= 0:
            return await ctx.reply("Error: Invalid bet amount. Minimum: 1 coin.", ephemeral=True)
        cap = await get_bet_cap(ctx.author.id)
        if( bet > cap):
            return await ctx.send(embed=discord.Embed(title="Error: Bet Limit Exceeded", description=f"Maximum bet: {cap} coins\nNote: Upvote bot to increase limit to 500k coins", color=discord.Color.red()))
        async with self.bot.db.acquire() as conn:
            await ensure_user(self.bot.db, ctx.author.id)
            row = await conn.fetchrow("SELECT coins FROM users WHERE id = $1", ctx.author.id)
            if not row or row["coins"] < bet:
                return await ctx.reply(f"Error: Insufficient funds\nRequired: {bet} coins\nAvailable: {row['coins'] if row else 0} coins", ephemeral=True)

            await log_spending(self.bot.db, bet)
            await conn.execute(
                "UPDATE users SET coins = coins - $1 WHERE id = $2",
                bet, ctx.author.id
            )

        deck = create_deck()
        random.shuffle(deck)
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        view = BlackjackView(self.bot, ctx, bet, deck, player_hand, dealer_hand)
        await ctx.reply(embed=view.build_embed(), view=view)


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
