# cogs/ping.py
from datetime import timedelta, timezone
from dotenv import load_dotenv
import datetime
import os
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from deep_translator import GoogleTranslator
import aiohttp
import pycountry
from rapidfuzz import process, fuzz
from utils.translation import translate as tr, translate_bulk
from utils.db_helpers import ensure_user
temp_store = {}

load_dotenv()
OWM_API_KEY = os.getenv("OWM_API_KEY")

# --------- Cache: simple TTL cache (5 minutes) ---------
_weather_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_get(key):
    entry = _weather_cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if (datetime.datetime.utcnow() - ts).total_seconds() > CACHE_TTL_SECONDS:
        del _weather_cache[key]
        return None
    return value


def _cache_set(key, value):
    _weather_cache[key] = (datetime.datetime.utcnow(), value)


# --------- Fuzzy country lookup to tolerate typos ----------
def fuzzy_country_lookup(name):
    countries = [c.name for c in pycountry.countries]
    # process.extractOne returns tuple (match, score, idx)
    match = process.extractOne(name, countries, scorer=fuzz.WRatio)
    if not match:
        return None
    matched_name, score, _ = match
    if score > 70:
        return matched_name
    return None


# --------- Fetch weather / geocode ----------
async def fetch_weather_data(session, query, lang="en"):
    """
    Returns (resolved_name, weather_json, aqi_data) or None.
    Steps:
    1) Try direct geocode (city or "City, Country")
    2) If no result: fuzzy-match as country -> map to capital -> geocode
    3) Call current weather endpoint with lat/lon
    4) Call air pollution endpoint for AQI data
    """
    cache_key = (query.lower().strip(), lang)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    params_geo = {"q": query, "limit": 1, "appid": OWM_API_KEY}

    async with session.get(geo_url, params=params_geo, timeout=20) as resp:
        if resp.status != 200:
            # treat as no result
            data = []
        else:
            data = await resp.json()

    if not data:
        # try fuzzy country then capital fallback
        fixed = fuzzy_country_lookup(query)
        if not fixed:
            return None
        try:
            country = pycountry.countries.lookup(fixed)
            country_code = country.alpha_2
        except LookupError:
            return None

        # A minimal capitals mapping (extend as desired)
        capitals = {
            "VN": "Hanoi",
            "US": "Washington",
            "IN": "New Delhi",
            "JP": "Tokyo",
            "KR": "Seoul",
            "CN": "Beijing",
            "FR": "Paris",
            "GB": "London",
            "DE": "Berlin",
            "CA": "Ottawa",
            "AU": "Canberra",
            # add more if you like
        }
        capital = capitals.get(country_code)
        if not capital:
            return None
        params_geo["q"] = capital
        async with session.get(geo_url, params=params_geo, timeout=20) as resp2:
            if resp2.status != 200:
                return None
            data = await resp2.json()
            if not data:
                return None

    lat = data[0].get("lat")
    lon = data[0].get("lon")
    resolved_name = data[0].get("name", query)

    # current weather endpoint
    weather_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OWM_API_KEY,
        "units": "metric",
        "lang": lang
    }

    async with session.get(weather_url, params=params, timeout=20) as resp_w:
        if resp_w.status != 200:
            return None
        weather_data = await resp_w.json()

    # Fetch AQI data
    aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution"
    aqi_params = {
        "lat": lat,
        "lon": lon,
        "appid": OWM_API_KEY
    }
    
    aqi_data = None
    try:
        async with session.get(aqi_url, params=aqi_params, timeout=20) as resp_aqi:
            if resp_aqi.status == 200:
                aqi_data = await resp_aqi.json()
    except Exception:
        pass  # AQI is optional, don't fail if unavailable

    result = (resolved_name, weather_data, aqi_data)
    _cache_set(cache_key, result)
    return result


# --------- Build embed for current weather ----------
def build_weather_embed(city_name, data, aqi_data=None, lang="en"):
    # Defensive access
    weather_list = data.get("weather", [{}])
    desc = weather_list[0].get("description", "No description").capitalize()
    main = data.get("main", {})
    temp = main.get("temp", "N/A")
    feels = main.get("feels_like", "N/A")
    humidity = main.get("humidity", "N/A")
    wind = data.get("wind", {}).get("speed", "N/A")
    clouds = data.get("clouds", {}).get("all", "N/A")
    sunrise_ts = data.get("sys", {}).get("sunrise")
    sunset_ts = data.get("sys", {}).get("sunset")

    # translate description/title if needed
    title = f"Weather in {city_name}"
    if lang.lower() != "en":
        try:
            desc = GoogleTranslator(source="auto", target=lang).translate(desc)
            title = GoogleTranslator(source="auto", target=lang).translate(title)
        except Exception:
            pass

    embed = discord.Embed(
        title=f"{title}",
        description=desc,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )

    embed.add_field(name="Temperature", value=f"{temp}°C", inline=True)
    embed.add_field(name="Human feels", value=f"{feels}°C", inline=True)
    embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
    embed.add_field(name="Wind", value=f"{wind} m/s", inline=True)
    embed.add_field(name="Clouds", value=f"{clouds}%", inline=True)

    # Add AQI information if available
    if aqi_data and "list" in aqi_data and len(aqi_data["list"]) > 0:
        aqi_info = aqi_data["list"][0]
        aqi_index = aqi_info.get("main", {}).get("aqi", 0)
        
        # AQI levels: 1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor
        aqi_labels = {
            1: "Good",
            2: "Fair", 
            3: "Moderate",
            4: "Poor",
            5: "Very Poor"
        }
        aqi_label = aqi_labels.get(aqi_index, "Unknown")
        
        # Get pollutant concentrations
        components = aqi_info.get("components", {})
        pm25 = components.get("pm2_5", "N/A")
        pm10 = components.get("pm10", "N/A")
        
        aqi_value = f"{aqi_label}\nPM2.5: {pm25} microgram/cubic meter\nPM10: {pm10} microgram/cubic meter"
        embed.add_field(name="Air Quality", value=aqi_value, inline=True)

    extra = []
    if sunrise_ts:
        extra.append(f"Sunrise: {datetime.datetime.utcfromtimestamp(sunrise_ts).strftime('%H:%M UTC')}")
    if sunset_ts:
        extra.append(f"Sunset: {datetime.datetime.utcfromtimestamp(sunset_ts).strftime('%H:%M UTC')}")
    if extra:
        embed.set_footer(text=" - ".join(extra) + f" -  OWM {datetime.datetime.utcnow().strftime('%H:%M UTC')}")
    else:
        embed.set_footer(text=f"OWM data - {datetime.datetime.utcnow().strftime('%H:%M UTC')}")

    return embed


# --------- Build alerts embed (from One Call alerts) ----------
def build_alerts_embeds(location_name, alerts_list, lang="en"):
    embeds = []
    for alert in alerts_list:
        event = alert.get("event", "Weather Alert")
        desc = alert.get("description", "No description")
        sender = alert.get("sender_name", "Unknown")
        start = alert.get("start")
        end = alert.get("end")

        if lang.lower() != "en" and desc:
            try:
                desc = GoogleTranslator(source="auto", target=lang).translate(desc)
                event = GoogleTranslator(source="auto", target=lang).translate(event)
            except Exception:
                pass

        embed = discord.Embed(
            title=f" {event}",
            description=desc,
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Source", value=sender, inline=True)
        if start:
            embed.add_field(name="Start", value=datetime.datetime.utcfromtimestamp(start).strftime("%Y-%m-%d %H:%M UTC"), inline=True)
        if end:
            embed.add_field(name="End", value=datetime.datetime.utcfromtimestamp(end).strftime("%Y-%m-%d %H:%M UTC"), inline=True)
        embeds.append(embed)
    return embeds


SUPPORT_DYNAMIC_LINK = "https://dsc.gg/convit"


# ============ Cog & commands ============
class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Bot latency")
    async def ping(self, interaction: discord.Interaction):
        # keep your non-emoji formatting approach
        await interaction.channel.send(self.bot.get_emoji("<:resting:1414593441593299014>"))
        await interaction.response.send_message(f"{round(self.bot.latency * 1000)} ms")

    @commands.command(name="translate", aliases=['trans', 'tr'])
    async def translate(self, ctx: commands.Context, *args):
        if not ctx.message.reference:
            return await ctx.send(await tr("Run the command when you are replying to someone's message lol", ctx))

        if len(args) == 1:
            source_lang = "auto"
            target_lang = args[0]
        elif len(args) == 2:
            target_lang = args[1]
            source_lang = args[0]
        else:
            source_lang = "auto"
            target_lang = "en"

        try:
            original_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except discord.NotFound:
            return await ctx.send(await tr("Cant fetch the message. Is the message ur replying deleted??", ctx))

        text_to_translate = original_msg.content

        try:
            trans_mes = GoogleTranslator(source=source_lang, target=target_lang).translate(text_to_translate)
        except Exception as e:
            return await ctx.send(await tr(f"Translation failed: {e}", ctx))

        translations = await translate_bulk(["Translation", "Source Language", "Target Language"], ctx)
        
        embed = discord.Embed(
            title=translations[0],
            description=f"{trans_mes}",
            color=discord.Colour.green()
        )
        embed.add_field(name=translations[1], value=source_lang, inline=True)
        embed.add_field(name=translations[2], value=target_lang, inline=True)

        await ctx.send(embed=embed)

    @app_commands.command(name="check-db", description="Check database")
    async def check_db(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with self.bot.db.acquire() as conn:
                tables = await conn.fetch("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                total_records = 0
                for table in tables:
                    table_name = table["table_name"]
                    count_result = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                    total_records += count_result

                translations = await translate_bulk(["Database Online", "tables", "total records"], interaction)
                await interaction.followup.send(
                    f"**{translations[0]}**\n"
                    f"`{len(tables)}` {translations[1]}\n"
                    f"`{total_records}` {translations[2]}"
                )
        except Exception as e:
            error_msg = await tr("Database error", interaction)
            await interaction.followup.send(f"{error_msg}: `{e}`")

    @app_commands.command(name='coinflip', description='Flip a coin')
    @app_commands.describe(rig="Choose if you want to rig the coin")
    @app_commands.choices(rig=[
        discord.app_commands.Choice(name="Odd (Heads)", value="heads"),
        discord.app_commands.Choice(name="Even (Tails)", value="tails"),
    ])
    async def coinflip(self, interaction: discord.Interaction, rig: discord.app_commands.Choice[str] = None):
        result = rig.value if rig else random.choice(["heads", "tails"])

        if rig:
            msg = await tr(f"You flipped a coin... it will be {result.upper()}\n*(You secretly rigged it)*", interaction)
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            msg = await tr("You flipped a fair coin...!", interaction)
            await interaction.response.send_message(msg, ephemeral=True)
        
        public_msg = await tr(f"{interaction.user.mention} flipped a coin... it's **{result.upper()}**", interaction)
        await interaction.channel.send(public_msg)

    @app_commands.command(name="deathmatch", description="Fight another user")
    async def deathmatch(self, i: discord.Interaction, target: discord.Member):
        try:
            f = [i.user, target]
            win = random.choice(f)
            lose = target if win == i.user else i.user
            if win.id not in temp_store:
                temp_store[win.id] = 0
            if lose.id not in temp_store:
                temp_store[lose.id] = 0
            temp_store[win.id] += 1
            temp_store[lose.id] -= 1

            title = await tr("Deathmatch", i)
            desc = await tr(f"{win.mention} WIN, {lose.mention} failed horribly", i)
            embed = discord.Embed(
                title=title,
                description=desc,
                color=discord.Color.green() if i.user.id == win.id else discord.Color.red()
            )

            embed.add_field(name=f"{win.name}", value=temp_store[win.id])
            embed.add_field(name=f"{lose.name}", value=temp_store[lose.id])
            await i.response.send_message(embed=embed)
        except Exception as e:
            await i.response.send_message(str(e))

    @commands.hybrid_command(name="support", description="Get support server")
    async def support_cmd(self, ctx: commands.Context):
        translations = await translate_bulk(["Support Server", "You can join the support by clicking on the link below", "Hot link"], ctx)
        embed = discord.Embed(
            title=translations[0],
            description=translations[1],
            color=discord.Color.dark_red()
        )
        embed.add_field(name=translations[2], value=SUPPORT_DYNAMIC_LINK)
        await ctx.reply(embed=embed)

    # ---------- weather command (city/country/typo tolerant) ----------
    @commands.hybrid_command(name="weather", description="Check current weather info for a location in any language")
    async def weather(self, ctx: commands.Context, location: str, lang: str = "en"):
       
        try:
           
            await ctx.response.defer()
        except Exception:
        
            try:
                await ctx.defer()
            except Exception:
                pass

        try:
            async with aiohttp.ClientSession() as session:
                result = await fetch_weather_data(session, location, lang=lang)
                if not result:
                    msg = await tr(f"No weather data found for **{location}**.", ctx)
                    await ctx.reply(msg, ephemeral=True)
                    return
                city, data, aqi_data = result
                embed = build_weather_embed(city, data, aqi_data, lang=lang)
                await ctx.reply(embed=embed)
        except Exception as e:
            msg = await tr(f"Failed to fetch weather data: `{e}`", ctx)
            await ctx.reply(msg, ephemeral=True)

    # ---------- weather-alerts command ----------
    @commands.hybrid_command(name="weather-alerts", description="Check weather alerts (severe weather) for a location")
    async def weather_alerts(self, ctx: commands.Context, location: str, lang: str = "en"):
        try:
            await ctx.response.defer()
        except Exception:
            try:
                await ctx.defer()
            except Exception:
                pass

        try:
            async with aiohttp.ClientSession() as session:
                res = await fetch_weather_data(session, location, lang=lang)
                if not res:
                    msg = await tr(f"No location found for **{location}**.", ctx)
                    await ctx.reply(msg, ephemeral=True)
                    return
                city, data, aqi_data = res
                lat = data.get("coord", {}).get("lat")
                lon = data.get("coord", {}).get("lon")
                if lat is None or lon is None:
                    msg = await tr(f"Could not determine coordinates for **{city}**.", ctx)
                    await ctx.reply(msg, ephemeral=True)
                    return

                onecall_url = "https://api.openweathermap.org/data/3.0/onecall"
                params = {
                    "lat": lat,
                    "lon": lon,
                    "appid": OWM_API_KEY,
                    "units": "metric",
                    "lang": "en"
                }
                async with session.get(onecall_url, params=params, timeout=20) as resp:
                    if resp.status != 200:
                        msg = await tr(f"No weather alerts currently for **{city}**.", ctx)
                        await ctx.reply(msg, ephemeral=True)
                        return
                    onecall = await resp.json()

                alerts = onecall.get("alerts", [])
                if not alerts:
                    msg = await tr(f"No weather alerts currently for **{city}**.", ctx)
                    await ctx.reply(msg, ephemeral=True)
                    return

                embeds = build_alerts_embeds(city, alerts, lang=lang)
                for e in embeds:
                    await ctx.reply(embed=e)
        except Exception as e:
            msg = await tr(f"Failed to fetch weather alerts: `{e}`", ctx)
            await ctx.reply(msg, ephemeral=True)




    @commands.hybrid_command(name="guide", description="View the bot tutorial guide")
    async def guide(self, ctx: commands.Context):
        """Display the bot tutorial guide with pagination"""
        try:
            await ctx.defer()

            # Read all tutorial pages
            pages_content = []
            for i in range(1, 8):
                try:
                    with open(f"docs/tutorial/page_{i}.txt", "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            pages_content.append(content)
                except FileNotFoundError:
                    continue

            if not pages_content:
                await ctx.reply("Tutorial guide not available.")
                return

            # Create embeds for each page
            embeds = []
            page_titles = [
                "Welcome to the Bot!",
                "Core Stats & Effects",
                "Items & Inventory",
                "Economy & Trading",
                "Resource Gathering",
                "Combat & RPG",
                "Social Features & Games"
            ]

            for i, (content, title) in enumerate(zip(pages_content, page_titles)):
                embed = discord.Embed(
                    title=title,
                    description=content,
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text=f"Page {i+1}/{len(pages_content)}")
                embeds.append(embed)

            # Send first page
            if len(embeds) == 1:
                await ctx.reply(embed=embeds[0])
            else:
                view = GuideView(embeds, ctx.author.id)
                await ctx.reply(embed=embeds[0], view=view)

        except Exception as e:
            await ctx.reply(f"Error loading guide: {e}")


async def setup(bot):
    await bot.add_cog(Ping(bot))


class GuideView(discord.ui.View):
    def __init__(self, embeds, user_id):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.current_page = 0
        self.user_id = user_id

        self.prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary)

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.embeds) - 1

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This guide is not for you.", ephemeral=True)

        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This guide is not for you.", ephemeral=True)

        self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
