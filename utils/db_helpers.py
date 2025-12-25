from datetime import datetime, timezone
import random
from warnings import deprecated
import logging
import discord
from discord.ext import commands

from utils.economy import format_number
import os

import aiohttp

TOPGG_BOT_LINK = os.getenv("TOPGG_INVITE")
TOPGG_API_TOKEN = os.getenv("TOPGG_TOKEN")
TOPGG_BOT_ID = os.getenv("BOT_ID")
logger = logging.getLogger(__name__)


# Ensure user record exists with default stats
async def ensure_user(db, user_id: int):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_config (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id)

        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if not row:
            await conn.execute("""
                INSERT INTO users (id, coins, energy, energy_max, mood, mood_max)
                VALUES ($1, 0, 100, 100, 100, 100)
            """, user_id)


# Insert all items into user's inventory with quantity = 0 if not already present
async def ensure_inventory(db, user_id: int):
    """
    Optimized: Only ensures commonly-used items exist in inventory.
    Other items are added on-demand using ON CONFLICT.
    """
    # Only pre-populate essential items that are frequently checked
    essential_items = [
        6,   # Pickaxe (for mining)
        26,  # Toolbelt (for work bonus)
    ]
    
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO inventory (id, item_id, quantity)
            SELECT $1, unnest($2::int[]), 0
            ON CONFLICT (id, item_id) DO NOTHING
        """, user_id, essential_items)


async def is_item_req_valid(db, user_id: int, item_id: int, amount: int = 1):
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 1 FROM inventory
            WHERE id = $1 AND item_id = $2 AND quantity >= $3
        """, user_id, item_id, amount)
        return row is not None


async def add_item(db, user_id: int, item_id: int, amount: int = 1):
    async with db.acquire() as conn:
        await conn.execute("""
            UPDATE inventory SET quantity = quantity + $3
            WHERE id = $1 AND item_id = $2
        """, user_id, item_id, amount)


# Insert guilds default data
async def ensure_guild(db, guild_id: int):
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM guilds WHERE id = $1", guild_id)
        if not row:
            await conn.execute("""
                INSERT INTO guilds (id)
                VALUES ($1)
            """, guild_id)


# Global fund functions removed - gambling now uses coin appearance/disappearance model

async def check_has_user_upvoted(user_id):
    try:
        url = f"https://top.gg/api/bots/{TOPGG_BOT_ID}/check?userId={user_id}"
        headers = {"Authorization": TOPGG_API_TOKEN}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"Top.gg API error [db helper]: status {resp.status}")
                    return False
                data = await resp.json()
                return bool(data.get("voted", 0))
    except Exception as e:
        print(e)


async def get_active_effects(db, user_id: int):
    async with db.acquire() as conn:
        now = datetime.now(timezone.utc)
        rows = await conn.fetch("""
            SELECT effect_type, value, expires_at
            FROM effects
            WHERE user_id = $1 AND expires_at > $2
        """, user_id, now)
        return rows



async def ensure_guild_cfg(pool, guild_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT guild_id FROM guild_config WHERE guild_id = $1", guild_id)
        if row is None:
            await conn.execute("""
                INSERT INTO guild_config (guild_id, allow_post, allow_crosspost)
                VALUES ($1, TRUE, FALSE)
            """, guild_id)


# Log hourly spending
async def log_spending(db, amount: int):
    now = datetime.now(timezone.utc)
    day = now.date()
    hour = now.hour
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO spending_hourly (day, hour, total_spent)
            VALUES ($1, $2, $3)
            ON CONFLICT (day, hour)
            DO UPDATE SET total_spent = spending_hourly.total_spent + EXCLUDED.total_spent
        """, day, hour, amount)


# Ensure mining data for guild
async def ensure_mine(db, guild_id: int):
    try:
        async with db.acquire() as conn:
            rows = await conn.fetch("SELECT item_id FROM global_mining_config")
            for row in rows:
                item_id = row["item_id"]
                await conn.execute("""
                    INSERT INTO mine (server_id, item_id, remaining)
                    VALUES ($1, $2, FLOOR(RANDOM() * (10000000 - 100000 + 1) + 100000)::BIGINT)
                    ON CONFLICT (server_id, item_id) DO NOTHING
                """, guild_id, item_id)
    except Exception as e:
        print(f"[DB ERROR] ensure_mine: {e}")


async def get_bet_cap(user_id):
    try:
        cap = 250000 if not await check_has_user_upvoted(user_id) else 500000
        return cap
    except Exception as e:
        print(e)

