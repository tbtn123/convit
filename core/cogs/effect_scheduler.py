from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.db_helpers import *
from datetime import datetime
from utils.singleton import BASE_TICK, EffectID

class EffectScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

        self.scheduler.add_job(
            self.reset_shop_at_midnight,
            name="Effect scheduler"
        )
        self.scheduler.start()

        self.check_and_apply_effects.start()

    def cog_unload(self):
        self.check_and_apply_effects.cancel()

    @tasks.loop(seconds=BASE_TICK)
    async def check_and_apply_effects(self):
        async with self.bot.db.acquire() as conn:
            await conn.fetch("""
    DELETE
    FROM current_effects
    WHERE EXTRACT(EPOCH FROM applied_at) + (duration * $1) <= EXTRACT(EPOCH FROM clock_timestamp())
""", BASE_TICK)
            effect_rows = await conn.fetch("""
    SELECT user_id, effect_id, applied_at, duration
    FROM current_effects
    WHERE EXTRACT(EPOCH FROM applied_at) + (duration * $1) > EXTRACT(EPOCH FROM clock_timestamp())
""", BASE_TICK)


            for effect in effect_rows:
                user_id = effect['user_id']
                effect_id = effect['effect_id']
                applied_at = effect['applied_at'].timestamp()
                duration = effect['duration'] * BASE_TICK

                end_time = applied_at + duration
                current_timestamp = datetime.now().timestamp()

                if end_time < datetime.now().timestamp():
                    
                    await conn.execute("""
                        DELETE FROM current_effects
                        WHERE user_id = $1 AND effect_id = $2
                    """, user_id, effect_id)
                    print(f"Effect {effect_id} for user {user_id} has expired and was removed.")
                else:
                    await ensure_user(self.bot.db, user_id)
                    if effect_id == EffectID.REST:
                        data = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                        add = min(data['energy']+1, data['energy_max'])
                        await conn.execute("UPDATE users SET energy = $1 WHERE id = $2", add, user_id)
                    
                    elif effect_id == EffectID.REPLENISHED:
                        data = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                        add = min(data['energy']+2, data['energy_max'])
                        await conn.execute("UPDATE users SET energy = $1 WHERE id = $2", add, user_id)
                    
                    elif effect_id == EffectID.EXHAUSTED:
                        data = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                        drain = max(data['energy']-1, 0)
                        await conn.execute("UPDATE users SET energy = $1 WHERE id = $2", drain, user_id)
                    
                    elif effect_id == EffectID.GAMBLING_ADDICT:
                        data = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                        drain = max(data['mood']-1, 0)
                        await conn.execute("UPDATE users SET mood = $1 WHERE id = $2", drain, user_id)

    async def reset_shop_at_midnight(self):
        print("Shop reset triggered!")

async def setup(bot):
    await bot.add_cog(EffectScheduler(bot))
