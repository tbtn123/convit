from datetime import datetime, timezone
import random
import logging
import discord
from discord.ext import commands
import json
import os
import aiohttp
import asyncpg

from utils.economy import format_number
from utils.datetime_helpers import utc_now, ensure_utc

TOPGG_BOT_LINK = os.getenv("TOPGG_INVITE")
TOPGG_API_TOKEN = os.getenv("TOPGG_TOKEN")
TOPGG_BOT_ID = os.getenv("BOT_ID")
logger = logging.getLogger(__name__)

CHILDREN_MAX = 5
PARTNERS_MAX = 2

async def ensure_user(db, user_id: int):
    logger.debug("ensure_user: user_id=%s", user_id)
    async with db.acquire() as conn:
        try:
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
                logger.info("ensure_user: created users row for %s", user_id)
        except Exception as e:
            logger.exception("ensure_user failed for %s", user_id)
            raise

async def ensure_inventory(db, user_id: int):
    logger.debug("ensure_inventory: user_id=%s", user_id)
   
    async with db.acquire() as conn:
        try:
            await conn.execute("""
            INSERT INTO inventory (id, item_id, quantity)
            SELECT $1, items.id, 0
            FROM items
            ON CONFLICT (id, item_id) DO NOTHING
        """, user_id)
            logger.info("ensure_inventory: ensured inventory for %s", user_id)
        except Exception:
            logger.exception("ensure_inventory failed for %s", user_id)
            raise

async def is_item_req_valid(db, user_id: int, item_id: int, amount: int = 1):
    try:

        async with db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 1 FROM inventory
                WHERE id = $1 AND item_id = $2 AND quantity >= $3
            """, user_id, item_id, amount)
            return row is not None
    except Exception as e:
        logging.exception(e)

async def add_item(db, user_id: int, item_id: int, amount: int = 1):
    
    logger.debug("add_item: user_id=%s item_id=%s amount=%s", user_id, item_id, amount)
    async with db.acquire() as conn:
        try:
            await conn.execute("""
                UPDATE inventory SET quantity = quantity + $3
                WHERE id = $1 AND item_id = $2
            """, user_id, item_id, amount)
            logger.info("add_item: updated inventory for %s item %s by %s", user_id, item_id, amount)
        except Exception:
            logger.exception("add_item failed for user=%s item=%s", user_id, item_id)
            raise

async def ensure_guild(db, guild_id: int):
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM guilds WHERE id = $1", guild_id)
        if not row:
            await conn.execute("INSERT INTO guilds (id) VALUES ($1)", guild_id)

async def check_has_user_upvoted(user_id):
    try:
        url = f"https://top.gg/api/bots/{TOPGG_BOT_ID}/check?userId={user_id}"
        headers = {"Authorization": TOPGG_API_TOKEN}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200: return False
                data = await resp.json()
                return bool(data.get("voted", 0))
    except: return False

async def get_active_effects(db, user_id: int):
    async with db.acquire() as conn:
        now = utc_now()
        return await conn.fetch("""
            SELECT effect_type, value, expires_at
            FROM effects
            WHERE user_id = $1 AND expires_at > $2
        """, user_id, now)

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
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO spending_hourly (day, hour, total_spent)
            VALUES ($1, $2, $3)
            ON CONFLICT (day, hour)
            DO UPDATE SET total_spent = spending_hourly.total_spent + EXCLUDED.total_spent
        """, now.date(), now.hour, amount)

async def ensure_mine(db, guild_id: int):
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT item_id FROM global_mining_config")
        for row in rows:
            await conn.execute("""
                INSERT INTO mine (server_id, item_id, remaining)
                VALUES ($1, $2, FLOOR(RANDOM() * 9900001 + 100000)::BIGINT)
                ON CONFLICT (server_id, item_id) DO NOTHING
            """, guild_id, row["item_id"])

async def get_bet_cap(user_id):
    return 500000 if await check_has_user_upvoted(user_id) else 250000

def canonical_pair(a: int, b: int):
    return (a, b) if a < b else (b, a)

async def get_parents(db, user_id: int):
    """Get all parents of a user (supports multiple parents)"""
    logger.debug("get_parents: user_id=%s", user_id)
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT parent_id FROM parents WHERE child_id = $1",
            user_id
        )
        parents = [r["parent_id"] for r in rows]
        logger.debug("get_parents: user=%s parents=%s", user_id, parents)
        return parents

async def get_parent(db, user_id: int):
    """Get first parent of a user (for backward compatibility)"""
    parents = await get_parents(db, user_id)
    return parents[0] if parents else None

async def add_child(db, parent_id: int, child_id: int):
    logger.debug("add_child: parent=%s child=%s", parent_id, child_id)
    async with db.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO parents (child_id, parent_id) VALUES ($1, $2)",
                child_id, parent_id
            )
            logger.info("add_child: relationship added parent=%s -> child=%s", parent_id, child_id)
        except Exception:
            logger.exception("add_child failed parent=%s child=%s", parent_id, child_id)
            raise

async def remove_child_relationship(db, child_id: int):
    logger.debug("remove_child_relationship: child=%s", child_id)
    async with db.acquire() as conn:
        try:
            await conn.execute(
                "DELETE FROM parents WHERE child_id = $1",
                child_id
            )
            logger.info("remove_child_relationship: removed all parents for child=%s", child_id)
        except Exception:
            logger.exception("remove_child_relationship failed for child=%s", child_id)
            raise

async def try_add_parent(db, child_id: int, parent_id: int):
    logger.debug("try_add_parent: child=%s parent=%s", child_id, parent_id)
    try:
        await add_child(db, parent_id, child_id)
        return False, None
    except asyncpg.PostgresError as e:
        logger.warning("try_add_parent postgres error child=%s parent=%s err=%s", child_id, parent_id, e)
        return True, str(e)

async def get_user_children(db, user_id: int):
    logger.debug("get_user_children: user_id=%s", user_id)
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT child_id FROM parents WHERE parent_id = $1",
            user_id
        )
        children = [r["child_id"] for r in rows]
        logger.debug("get_user_children: user=%s children=%s", user_id, children)
        return children

async def get_user_partners(db, user_id: int):
    logger.debug("get_user_partners: user_id=%s", user_id)
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT spouse_a, spouse_b
            FROM marriages
            WHERE spouse_a = $1 OR spouse_b = $1
            """,
            user_id
        )

    partners = []
    for a, b in rows:
        partners.append(b if a == user_id else a)
    logger.debug("get_user_partners: user=%s partners=%s", user_id, partners)
    return partners

async def get_marriage_date(db, user1_id: int, user2_id: int):
    a, b = canonical_pair(user1_id, user2_id)
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT created_at FROM marriages WHERE spouse_a = $1 AND spouse_b = $2",
            a, b
        )
        return row["created_at"] if row else None

async def add_partner(db, user_id: int, partner_id: int, marriage_date=None):
    logger.debug("add_partner: user=%s partner=%s marriage_date=%s", user_id, partner_id, marriage_date)
    a, b = canonical_pair(user_id, partner_id)
    async with db.acquire() as conn:
        try:
            if marriage_date:
                await conn.execute(
                    """
                    INSERT INTO marriages (spouse_a, spouse_b, created_at)
                    VALUES ($1, $2, $3)
                    """,
                    a, b, marriage_date
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO marriages (spouse_a, spouse_b)
                    VALUES ($1, $2)
                    """,
                    a, b
                )
            logger.info("add_partner: added marriage %s-%s", a, b)
        except Exception:
            logger.exception("add_partner failed for %s-%s", a, b)
            raise

async def remove_partner(db, user_id: int, partner_id: int):
    logger.debug("remove_partner: user=%s partner=%s", user_id, partner_id)
    a, b = canonical_pair(user_id, partner_id)
    async with db.acquire() as conn:
        try:
            res = await conn.execute(
                "DELETE FROM marriages WHERE spouse_a = $1 AND spouse_b = $2",
                a, b
            )
            logger.info("remove_partner: removed marriage %s-%s result=%s", a, b, res)
            return res != "DELETE 0"
        except Exception:
            logger.exception("remove_partner failed for %s-%s", a, b)
            raise

async def try_add_partner(db, user_id: int, partner_id: int):
    logger.debug("try_add_partner: user=%s partner=%s", user_id, partner_id)
    try:
        await add_partner(db, user_id, partner_id)
        return False, None
    except asyncpg.PostgresError as e:
        logger.warning("try_add_partner postgres error user=%s partner=%s err=%s", user_id, partner_id, e)
        return True, str(e)

async def get_relationship_data(db, user_id: int):
    """Get basic relationship data for a user"""
    async with db.acquire() as conn:
        # This is a placeholder function that returns basic user data
        # The relationships.py code expects this but doesn't actually use the return value
        return {"user_id": user_id}

async def check_relationship_conflicts(db, user1_id: int, user2_id: int):
    """Check if two users can have a relationship (marriage/adoption)"""
    try:
        # Check if they're already partners
        partners = await get_user_partners(db, user1_id)
        if user2_id in partners:
            return True, "already_married"
        
        # Check if they're too closely related (within 3 generations)
        if await is_too_closely_related(db, user1_id, user2_id, depth=3):
            return True, "too_closely_related"
        
        return False, ""
    except Exception as e:
        return True, str(e)

async def check_parent_conflicts(db, child_id: int, parent_id: int):
    """Check if a parent-child relationship can be established"""
    try:
        # Check if they're already partners
        partners = await get_user_partners(db, child_id)
        if parent_id in partners:
            return True, "cannot_adopt_spouse"
        
        # Use the robust can_adopt function
        if not await can_adopt(db, parent_id, child_id):
            return True, "would_create_genealogical_loop"
        
        return False, ""
    except Exception as e:
        return True, str(e)

async def can_adopt(db, parent_id: int, child_id: int):
    """
    Check if parent_id can adopt child_id using recursive CTE.
    Ensures parent is not already a descendant of the child.
    """
    logger.debug("can_adopt: parent=%s child=%s", parent_id, child_id)
    async with db.acquire() as conn:
        try:
            result = await conn.fetchval("""
                WITH RECURSIVE descendants(id) AS (
                    -- Direct children of the child
                    SELECT child_id
                    FROM parents
                    WHERE parent_id = $1

                    UNION

                    -- Recursive descendants of the child
                    SELECT p.child_id
                    FROM parents p
                    JOIN descendants d ON p.parent_id = d.id
                )
                SELECT EXISTS(SELECT 1 FROM descendants WHERE id = $2)
            """, child_id, parent_id)
            logger.debug("can_adopt: descendant_check result=%s", result)
            return not result  # Return True if parent is NOT a descendant
        except Exception:
            logger.exception("can_adopt query failed parent=%s child=%s", parent_id, child_id)
            raise

async def is_too_closely_related(db, user_a: int, user_b: int, depth: int = 3):
    """
    Check if two users are too closely related (share common ancestor within depth generations).
    Returns True if they share a common ancestor within the specified depth.
    """
    logger.debug("is_too_closely_related: a=%s b=%s depth=%s", user_a, user_b, depth)
    async with db.acquire() as conn:
        try:
            result = await conn.fetchval("""
                WITH RECURSIVE 
                ancestors_a(ancestor_id, generation) AS (
                    -- Direct parents of user_a
                    SELECT parent_id, 1
                    FROM parents
                    WHERE child_id = $1

                    UNION

                    -- Recursive ancestors of user_a up to depth
                    SELECT p.parent_id, a.generation + 1
                    FROM parents p
                    JOIN ancestors_a a ON p.child_id = a.ancestor_id
                    WHERE a.generation < $3
                ),
                ancestors_b(ancestor_id, generation) AS (
                    -- Direct parents of user_b
                    SELECT parent_id, 1
                    FROM parents
                    WHERE child_id = $2

                    UNION

                    -- Recursive ancestors of user_b up to depth
                    SELECT p.parent_id, b.generation + 1
                    FROM parents p
                    JOIN ancestors_b b ON p.child_id = b.ancestor_id
                    WHERE b.generation < $3
                )
                SELECT EXISTS(
                    SELECT 1 FROM ancestors_a a
                    JOIN ancestors_b b ON a.ancestor_id = b.ancestor_id
                )
            """, user_a, user_b, depth)
            logger.debug("is_too_closely_related: result=%s", result)
            return result
        except Exception:
            logger.exception("is_too_closely_related query failed for %s vs %s", user_a, user_b)
            raise

async def get_all_family_members(db, user_id: int, max_generations: int = 5):
    logger.debug("get_all_family_members: user_id=%s max_generations=%s", user_id, max_generations)
    family = {}
    visited = set()

    async def walk(uid: int, gen: int):
        if uid in visited or abs(gen) > max_generations:
            return

        visited.add(uid)

        parents = await get_parents(db, uid)  # Support multiple parents
        partners = await get_user_partners(db, uid)
        children = await get_user_children(db, uid)

        family[uid] = {
            "id": uid,
            "parents": parents,  # Changed from parent_id to parents (list)
            "partners": partners,
            "generation": gen
        }

        for p in partners:
            await walk(p, gen)
        for c in children:
            await walk(c, gen + 1)
        for parent in parents:  # Walk through all parents
            await walk(parent, gen - 1)

    await walk(user_id, 0)
    logger.debug("get_all_family_members: visited_count=%s", len(visited))
    return sorted(family.values(), key=lambda x: (x["generation"], x["id"]))
