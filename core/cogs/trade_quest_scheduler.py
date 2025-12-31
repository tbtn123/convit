from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import random

class TradeQuestScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        # Run daily at 0:00 UTC+7 (Asia/Bangkok timezone)
        self.scheduler.add_job(
            self.generate_trade_quests,
            CronTrigger(hour=0, minute=0, timezone='Asia/Bangkok'),
            name="Trade Quest Generation"
        )
        self.scheduler.start()

    async def generate_trade_quests(self):
        try:
            async with self.bot.db.acquire() as conn:
                # Reset: Remove all existing trade quests
                await conn.execute("DELETE FROM trade_quests")

                # Generate exactly 5 new quests
                quests_to_generate = 5

                generated = 0
                for _ in range(quests_to_generate):
                    if await self.generate_single_quest(conn):
                        generated += 1

                print(f"Reset trade quests and generated {generated} new quests")

        except Exception as e:
            print(f"Error generating trade quests: {e}")

    async def generate_single_quest(self, conn):
        try:
            tradeable_items = await conn.fetch("""
                SELECT id, name FROM items
                WHERE id > 2
                ORDER BY RANDOM() LIMIT 1
            """)

            if not tradeable_items:
                return False

            item = tradeable_items[0]

            trust_weights = [0.15, 0.15, 0.15, 0.15, 0.15, 0.10, 0.05, 0.03, 0.02]
            trust_level = random.choices(range(1, 10), weights=trust_weights)[0]

            amount = random.randint(1, 5)
            base_value = await self.get_item_base_value(conn, item['id'])
            payout = int(base_value * amount * (0.6 + trust_level * 0.04))

            timeout_days = 7

            await conn.execute("""
                INSERT INTO trade_quests (trust_level, item_id, item_amount, payout, expires_at)
                VALUES ($1, $2, $3, $4, NOW() + INTERVAL '${5} days')
            """, trust_level, item['id'], amount, payout, timeout_days)

            return True
        except Exception:
            return False

    async def get_item_base_value(self, conn, item_id):
        market_prices = await conn.fetch("""
            SELECT AVG(price) as avg_price FROM trades
            WHERE item_id = $1 AND created_at > NOW() - INTERVAL '24 hours'
            GROUP BY item_id
        """, item_id)

        if market_prices:
            return int(market_prices[0]['avg_price'] or 100)

        default_values = {
            3: 50, 10: 80, 15: 120, 18: 25, 19: 30, 26: 500
        }
        return default_values.get(item_id, 100)


async def setup(bot):
    await bot.add_cog(TradeQuestScheduler(bot))
