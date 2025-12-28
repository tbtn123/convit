from datetime import datetime, timezone
import random
from warnings import deprecated
import logging
import discord
from discord.ext import commands
import json

from utils.economy import format_number
from utils.datetime_helpers import utc_now, ensure_utc
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
        now = utc_now()
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


async def log_spending(db, amount: int):
    now = utc_now()
    day = now.date()
    hour = now.hour
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO spending_hourly (day, hour, total_spent)
            VALUES ($1, $2, $3)
            ON CONFLICT (day, hour)
            DO UPDATE SET total_spent = spending_hourly.total_spent + EXCLUDED.total_spent
        """, day, hour, amount)



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


async def ensure_relationship(db, user_id: int):
    pass


async def get_relationship_data(db, user_id: int):
    async with db.acquire() as conn:
        parent_row = await conn.fetchrow("""
            SELECT parent_id FROM parents
            WHERE child_id = $1
        """, user_id)
        return {'father_id': parent_row['parent_id'] if parent_row else None, 'mother_id': None}


async def get_user_partners(db, user_id: int):
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT partner_id, created_at
            FROM marriages
            WHERE user_id = $1
            UNION
            SELECT user_id as partner_id, created_at
            FROM marriages
            WHERE partner_id = $1
        """, user_id)
        return [row['partner_id'] for row in rows]


async def get_marriage_date(db, user1_id: int, user2_id: int):
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT created_at FROM marriages
            WHERE (user_id = $1 AND partner_id = $2) OR (user_id = $2 AND partner_id = $1)
        """, user1_id, user2_id)
        return row['created_at'] if row else None


async def get_user_children(db, user_id: int):
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT child_id FROM parents
            WHERE parent_id = $1
        """, user_id)
        return [row['child_id'] for row in rows]


async def add_partner(db, user_id: int, partner_id: int, marriage_date=None):
    async with db.acquire() as conn:
        existing = await conn.fetchrow("""
            SELECT 1 FROM marriages
            WHERE (user_id = $1 AND partner_id = $2) OR (user_id = $2 AND partner_id = $1)
        """, user_id, partner_id)
        if existing:
            return False
        
        if marriage_date is None:
            await conn.execute("""
                INSERT INTO marriages (user_id, partner_id)
                VALUES ($1, $2)
            """, user_id, partner_id)
        else:
            await conn.execute("""
                INSERT INTO marriages (user_id, partner_id, created_at)
                VALUES ($1, $2, $3)
            """, user_id, partner_id, marriage_date)
        return True


async def remove_partner(db, user_id: int, partner_id: int):
    async with db.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM marriages
            WHERE (user_id = $1 AND partner_id = $2) OR (user_id = $2 AND partner_id = $1)
        """, user_id, partner_id)
        return result != "DELETE 0"


async def add_child(db, father_id: int, mother_id: int, child_id: int):
    parent_id = father_id if father_id else mother_id
    if parent_id:
        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO parents (child_id, parent_id)
                VALUES ($1, $2)
                ON CONFLICT (child_id, guild_id) DO UPDATE SET parent_id = $2
            """, child_id, parent_id)


async def remove_child_relationship(db, child_id: int):
    async with db.acquire() as conn:
        await conn.execute("""
            DELETE FROM parents
            WHERE child_id = $1
        """, child_id)


async def is_parent_child(db, user_id: int, other_id: int, max_depth: int = 20):
    if user_id == other_id:
        return False
    
    async with db.acquire() as conn:
        parent_row = await conn.fetchrow("""
            SELECT parent_id FROM parents WHERE child_id = $1
        """, user_id)
        if parent_row and parent_row['parent_id'] == other_id:
            return True
        
        child_rows = await conn.fetch("""
            SELECT child_id FROM parents WHERE parent_id = $1
        """, user_id)
        for row in child_rows:
            if row['child_id'] == other_id:
                return True
    
    return False


async def is_sibling(db, user_id: int, other_id: int):
    async with db.acquire() as conn:
        parent1_row = await conn.fetchrow("""
            SELECT parent_id FROM parents WHERE child_id = $1
        """, user_id)
        parent2_row = await conn.fetchrow("""
            SELECT parent_id FROM parents WHERE child_id = $1
        """, other_id)
        
        if parent1_row and parent2_row:
            return parent1_row['parent_id'] == parent2_row['parent_id']
    
    return False


async def check_relationship_conflicts(db, user_id: int, target_id: int):
    if user_id == target_id:
        return True, "Cannot form relationship with yourself"
    
    if await is_parent_child(db, user_id, target_id):
        return True, "Cannot marry someone who is your parent or child"
    
    if await is_sibling(db, user_id, target_id):
        return True, "Cannot marry your sibling"
    
    return False, ""


async def check_parent_conflicts(db, child_id: int, father_id: int = None, mother_id: int = None):
    parent_id = father_id if father_id else mother_id
    
    if child_id == parent_id:
        return True, "Cannot be your own parent"
    
    async with db.acquire() as conn:
        existing_parent = await conn.fetchrow("""
            SELECT parent_id FROM parents WHERE child_id = $1
        """, child_id)
        if existing_parent:
            return True, "Already has a parent"
    
    return False, ""


async def get_all_family_members(db, user_id: int):
    async with db.acquire() as conn:
        family_data = []
        
        partners = await get_user_partners(db, user_id)
        children = await get_user_children(db, user_id)
        
        parent_row = await conn.fetchrow("""
            SELECT parent_id FROM parents WHERE child_id = $1
        """, user_id)
        parent_id = parent_row['parent_id'] if parent_row else None
        
        family_data.append({
            'id': user_id,
            'father_id': parent_id,
            'mother_id': None,
            'partners': partners,
            'generation': 0
        })
        
        if parent_id:
            parent_partners = await get_user_partners(db, parent_id)
            parent_children = await get_user_children(db, parent_id)
            family_data.append({
                'id': parent_id,
                'father_id': None,
                'mother_id': None,
                'partners': parent_partners,
                'generation': -1
            })
        
        for child_id in children:
            child_partners = await get_user_partners(db, child_id)
            child_children = await get_user_children(db, child_id)
            family_data.append({
                'id': child_id,
                'father_id': user_id,
                'mother_id': None,
                'partners': child_partners,
                'generation': 1
            })
        
        family_data.sort(key=lambda x: (x['generation'], x['id']))
        return family_data
