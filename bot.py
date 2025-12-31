import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncpg
import uvicorn
from datetime import datetime, timezone

from utils.misc import get_system_info
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

load_dotenv()
db_url = os.getenv("DB_URL")
token = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.all()

async def get_prefix(bot, message):
    if not message.guild:
        return "."
    guild_id = message.guild.id
    async with bot.db.acquire() as conn:
        prefix = await conn.fetchval(
            "SELECT prefix FROM guild_config WHERE guild_id = $1", guild_id
        )
    return prefix if prefix else "."

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
bot.start_time = datetime.now(timezone.utc)

work_cache = {}
gambling_cache = {}
work_failures_cache = {}
mining_events_cache = {}
async def add_guild_to_db(guild_id):
    """Adds a guild to the database if it doesn't exist."""
    try:
        async with bot.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_config (guild_id, allow_rob)
                VALUES ($1, TRUE)
                ON CONFLICT (guild_id) DO NOTHING;
                """,
                guild_id,
            )
        logger.info(f"Added guild {guild_id} to database.")
    except Exception as e:
        logger.error(f"Error adding guild {guild_id} to database: {e}")


async def remove_guild_from_db(guild_id):
    """Removes a guild from the database."""
    try:
        async with bot.db.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM guild_config WHERE guild_id = $1;
                """,
                guild_id,
            )
        logger.info(f"Removed guild {guild_id} from database.")
    except Exception as e:
        logger.error(f"Error removing guild {guild_id} from database: {e}")

@bot.event
async def on_guild_join(guild):
    await add_guild_to_db(guild.id)

@bot.event
async def on_guild_remove(guild):
    await remove_guild_from_db(guild.id)

async def set_prefix(guild_id, new_prefix):
    async with bot.db.acquire() as conn:
        await conn.execute(
            "UPDATE guild_config SET prefix = $1 WHERE guild_id = $2", new_prefix, guild_id
        )



async def terminate_idle_connections():
    async with bot.db.acquire() as conn:
        await conn.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE state = 'idle' AND pid <> pg_backend_pid();
        """)

async def get_total_connections():
    async with bot.db.acquire() as conn:
        total_connections = await conn.fetchval("""
            SELECT count(*) FROM pg_stat_activity;
        """)
    return total_connections

def cleanup_activity_caches():
    """Clean up old entries from activity tracking caches"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    five_mins_ago = now - timedelta(minutes=5)
    one_day_ago = now - timedelta(days=1)
    
    for user_id in list(work_cache.keys()):
        work_cache[user_id] = [ts for ts in work_cache[user_id] if ts > five_mins_ago]
        if not work_cache[user_id]:
            del work_cache[user_id]
    
    for key in list(gambling_cache.keys()):
        if '_' in key:
            try:
                date_str = key.split('_')[1]
                cache_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if cache_date < one_day_ago.date():
                    del gambling_cache[key]
            except:
                pass
    
    today = now.date()
    for user_id in list(work_failures_cache.keys()):
        if 'last_reset' in work_failures_cache[user_id]:
            last_reset = work_failures_cache[user_id]['last_reset']
            if last_reset < today:
                work_failures_cache[user_id] = {'count': 0, 'last_reset': today}

async def create_db_pool():
    bot.db = await asyncpg.create_pool(dsn=db_url, max_size=2, min_size=1)
    
    from utils.translation import init_translation
    init_translation(bot)

# Removed update_guild_data

async def load_cogs():
    cog_dirs = []
    if os.path.exists("./core/cogs"):
        cog_dirs.append("./core/cogs")
    if os.path.exists("./advanced/cogs"):
        cog_dirs.append("./advanced/cogs")

    loaded_cogs = 0
    failed_cogs = 0

    for cog_dir in cog_dirs:
        for filename in os.listdir(cog_dir):
            if filename.endswith(".py"):
                if "core" in cog_dir:
                    module_path = f"core.cogs.{filename[:-3]}"
                elif "advanced" in cog_dir:
                    module_path = f"advanced.cogs.{filename[:-3]}"
                else:
                    continue

                try:
                    await bot.load_extension(module_path)
                    print(f"[+] Loaded cog: {filename}")
                    loaded_cogs += 1
                except Exception as e:
                    print(f"[!] Failed to load cog '{filename}': {e}")
                    failed_cogs += 1

    print(f"Cogs loaded: {loaded_cogs} loaded, {failed_cogs} failed")

async def periodic_cache_cleanup():
    """Run cache cleanup every hour"""
    while True:
        await asyncio.sleep(3600)
        cleanup_activity_caches()
        logger.info("Cache cleanup completed")

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} app commands.")
        print(f"Synced {len(synced)} app commands.")
        print("Bot's servers :", len(bot.guilds))

        for guild in bot.guilds:
            await add_guild_to_db(guild.id)
        
        asyncio.create_task(periodic_cache_cleanup())
        logger.info("Started periodic cache cleanup task")

    except Exception as e:
        logger.error(f"[ERR] Sync failed: {e}")
        print(f"[ERR] Sync failed: {e}")

async def main():
    if not token:
        raise RuntimeError("DISCORD_TOKEN missing from .env!")
    await create_db_pool()
    logger.info("Database pool created.")
    print(" Database pool created.")
    active_connections = await get_total_connections()
    logger.info(f"Total database connections: {active_connections}")
    print(f"Total database connections: {active_connections}")
    await load_cogs()
    logger.info("Cogs loaded.")
    print(" Cogs loaded.")
   
    await bot.start(token)

if __name__ == "__main__":
    get_system_info()
    asyncio.run(main())
