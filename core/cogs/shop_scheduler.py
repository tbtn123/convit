from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import random

class ShopScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.reset_shop,
            CronTrigger(hour=0, minute=0, timezone="Asia/Bangkok"),  # UTC+7
            name="Daily Shop Reset"
        )
        self.scheduler.start()

    async def reset_shop(self):
        try:
            async with self.bot.db.acquire() as conn:
                # Use transactions for atomicity
                async with conn.transaction():
                    await conn.execute("DELETE FROM global_shop")
                    rows = await conn.fetch("SELECT * FROM shop_pool")
                    chosen = random.sample(rows, k=min(10, len(rows)))

                    # Batch insert to improve efficiency
                    await conn.executemany(
                        """
                        INSERT INTO global_shop (pool_id, price, stock)
                        VALUES ($1, $2, $3)
                        """,
                        [(row['id'], random.randint(row['price_min'], row['price_max']), random.randint(row['stock_min'], row['stock_max'])) for row in chosen]
                    )

        except Exception as e:
            print(f"Error resetting shop: {e}")
            # Optionally log to a file or monitoring service

async def setup(bot):
    await bot.add_cog(ShopScheduler(bot))
