import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DB_URL")

db = None 

async def init_db_pool():
    global db
    db = await asyncpg.create_pool(dsn=db_url, max_size=2, min_size=1)
    print("Database pool created.")

async def get_total_connections():
    async with db.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM pg_stat_activity;")
    return total
