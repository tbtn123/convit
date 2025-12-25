from deep_translator import GoogleTranslator
import logging
import discord

_bot_instance = None
_translator_cache = {}

TRANSLATION_OVERRIDES = {
    "vi": {
        "Source Language": "Ngôn ngữ gốc",
        "Target Language": "Ngôn ngữ đích",
        "Source Lang": "Ngôn ngữ gốc",
        "Target Lang": "Ngôn ngữ đích",
        "Action": "Hành động",
        "Initiator": "Người khởi xướng",
        "Target": "Mục tiêu",
        "Mood": "Tâm trạng",
        "Status": "Trạng thái",
        "Social Interaction Complete": "Hoàn thành tương tác xã hội",
        "Interaction logged": "Đã ghi nhận tương tác",
        "Hostile action logged": "Đã ghi nhận hành động thù địch",
        "Respect acknowledged": "Đã ghi nhận sự tôn trọng",
    }
}

def init_translation(bot):
    global _bot_instance
    _bot_instance = bot

def _get_translator(locale):
    if locale not in _translator_cache:
        _translator_cache[locale] = GoogleTranslator(target=locale)
    return _translator_cache[locale]

async def translate(text, user_or_ctx, guild_id=None):
    try:
        if hasattr(user_or_ctx, 'author'):
            user_id = user_or_ctx.author.id
            guild_id = user_or_ctx.guild.id if user_or_ctx.guild else None
        elif hasattr(user_or_ctx, 'user'):
            user_id = user_or_ctx.user.id
            guild_id = user_or_ctx.guild_id
        elif hasattr(user_or_ctx, 'guild'):
            user_id = user_or_ctx.id
            guild_id = user_or_ctx.guild.id if user_or_ctx.guild else None
        else:
            user_id = user_or_ctx
        
        locale = await getUserLocale(user_id, guild_id)
        if locale == "en":
            return text
        
        if locale in TRANSLATION_OVERRIDES and text in TRANSLATION_OVERRIDES[locale]:
            return TRANSLATION_OVERRIDES[locale][text]
        
        translator = _get_translator(locale)
        return translator.translate(text)
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return text

async def translate_bulk(texts, user_or_ctx, guild_id=None):
    try:
        if hasattr(user_or_ctx, 'author'):
            user_id = user_or_ctx.author.id
            guild_id = user_or_ctx.guild.id if user_or_ctx.guild else None
        elif hasattr(user_or_ctx, 'user'):
            user_id = user_or_ctx.user.id
            guild_id = user_or_ctx.guild_id
        elif hasattr(user_or_ctx, 'guild'):
            user_id = user_or_ctx.id
            guild_id = user_or_ctx.guild.id if user_or_ctx.guild else None
        else:
            user_id = user_or_ctx
        
        locale = await getUserLocale(user_id, guild_id)
        if locale == "en":
            return texts
        
        translator = _get_translator(locale)
        results = []
        for text in texts:
            if locale in TRANSLATION_OVERRIDES and text in TRANSLATION_OVERRIDES[locale]:
                results.append(TRANSLATION_OVERRIDES[locale][text])
            else:
                try:
                    results.append(translator.translate(text))
                except Exception:
                    results.append(text)
        return results
    except Exception as e:
        logging.error(f"Bulk translation error: {e}")
        return texts

async def getUserLocale(user_id, guild_id=None):
    if not _bot_instance:
        return "en"
    
    async with _bot_instance.db.acquire() as conn:
        try:
            if guild_id:
                guild_locale = await conn.fetchval("SELECT locale FROM guild_config WHERE guild_id = $1", guild_id)
                if guild_locale:
                    return guild_locale
            
            locale = await conn.fetchval("SELECT locale FROM user_config WHERE user_id = $1", user_id)
            if locale:
                return locale
            await conn.execute("INSERT INTO user_config(user_id, locale) VALUES($1, $2) ON CONFLICT DO NOTHING", user_id, "en")
            return "en"
        except Exception as e:
            logging.error(f"Locale fetch error: {e}")
            return "en"
            