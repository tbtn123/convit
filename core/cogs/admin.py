import discord
from discord.ext import commands
from discord import app_commands
import logging
from rapidfuzz import process, fuzz
from utils.db_helpers import ensure_guild_cfg
LOCALE_MAP = {
    "af": "Afrikaans - Afrikaans",
    "sq": "Albanian - Shqip",
    "am": "Amharic - አማርኛ",
    "ar": "Arabic - العربية",
    "hy": "Armenian - Հայերեն",
    "az": "Azerbaijani - Azərbaycan dili",
    "eu": "Basque - Euskara",
    "be": "Belarusian - Беларуская",
    "bn": "Bengali - বাংলা",
    "bs": "Bosnian - Bosanski",
    "bg": "Bulgarian - Български",
    "ca": "Catalan - Català",
    "ceb": "Cebuano - Cebuano",
    "ny": "Chichewa - Chichewa",
    "zh-CN": "Chinese (Simplified) - 中文 (简体)",
    "zh-TW": "Chinese (Traditional) - 中文 (繁體)",
    "co": "Corsican - Corsu",
    "hr": "Croatian - Hrvatski",
    "cs": "Czech - Čeština",
    "da": "Danish - Dansk",
    "nl": "Dutch - Nederlands",
    "en": "English - English",
    "eo": "Esperanto - Esperanto",
    "et": "Estonian - Eesti",
    "tl": "Filipino - Filipino",
    "fi": "Finnish - Suomi",
    "fr": "French - Français",
    "fy": "Frisian - Frysk",
    "gl": "Galician - Galego",
    "ka": "Georgian - ქართული",
    "de": "German - Deutsch",
    "el": "Greek - Ελληνικά",
    "gu": "Gujarati - ગુજરાતી",
    "ht": "Haitian Creole - Kreyòl Ayisyen",
    "ha": "Hausa - Hausa",
    "haw": "Hawaiian - ʻŌlelo Hawaiʻi",
    "iw": "Hebrew - עברית",
    "hi": "Hindi - हिन्दी",
    "hmn": "Hmong - Hmoob",
    "hu": "Hungarian - Magyar",
    "is": "Icelandic - Íslenska",
    "ig": "Igbo - Igbo",
    "id": "Indonesian - Bahasa Indonesia",
    "ga": "Irish - Gaeilge",
    "it": "Italian - Italiano",
    "ja": "Japanese - 日本語",
    "jw": "Javanese - Basa Jawa",
    "kn": "Kannada - ಕನ್ನಡ",
    "kk": "Kazakh - Қазақ тілі",
    "km": "Khmer - ខ្មែរ",
    "ko": "Korean - 한국어",
    "ku": "Kurdish - Kurdî",
    "ky": "Kyrgyz - Кыргызча",
    "lo": "Lao - ລາວ",
    "la": "Latin - Latina",
    "lv": "Latvian - Latviešu",
    "lt": "Lithuanian - Lietuvių",
    "lb": "Luxembourgish - Lëtzebuergesch",
    "mk": "Macedonian - Македонски",
    "mg": "Malagasy - Malagasy",
    "ms": "Malay - Bahasa Melayu",
    "ml": "Malayalam - മലയാളം",
    "mt": "Maltese - Malti",
    "mi": "Maori - Māori",
    "mr": "Marathi - मराठी",
    "mn": "Mongolian - Монгол",
    "my": "Myanmar (Burmese) - မြန်မာ",
    "ne": "Nepali - नेपाली",
    "no": "Norwegian - Norsk",
    "ps": "Pashto - پښتو",
    "fa": "Persian - فارسی",
    "pl": "Polish - Polski",
    "pt": "Portuguese - Português",
    "pa": "Punjabi - ਪੰਜਾਬੀ",
    "ro": "Romanian - Română",
    "ru": "Russian - Русский",
    "sm": "Samoan - Gagana Sāmoa",
    "gd": "Scots Gaelic - Gàidhlig",
    "sr": "Serbian - Српски",
    "st": "Sesotho - Sesotho",
    "sn": "Shona - chiShona",
    "sd": "Sindhi - سنڌي",
    "si": "Sinhala - සිංහල",
    "sk": "Slovak - Slovenčina",
    "sl": "Slovenian - Slovenščina",
    "so": "Somali - Soomaali",
    "es": "Spanish - Español",
    "su": "Sundanese - Basa Sunda",
    "sw": "Swahili - Kiswahili",
    "sv": "Swedish - Svenska",
    "tg": "Tajik - Тоҷикӣ",
    "ta": "Tamil - தமிழ்",
    "te": "Telugu - తెలుగు",
    "th": "Thai - ไทย",
    "tr": "Turkish - Türkçe",
    "uk": "Ukrainian - Українська",
    "ur": "Urdu - اردو",
    "uz": "Uzbek - O'zbek",
    "vi": "Vietnamese - Tiếng Việt",
    "cy": "Welsh - Cymraeg",
    "xh": "Xhosa - isiXhosa",
    "yi": "Yiddish - ייִדיש",
    "yo": "Yoruba - Yorùbá",
    "zu": "Zulu - isiZulu"
}

class Admin(commands.GroupCog, name="admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def locale_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        for code, name in LOCALE_MAP.items():
            display = f"{name} ({code})"
            if current.lower() in display.lower():
                choices.append(app_commands.Choice(name=display, value=code))
                if len(choices) >= 25:
                    break
        
        if not choices and current:
            matches = process.extract(current, LOCALE_MAP.values(), scorer=fuzz.WRatio, limit=25)
            for match_name, score, _ in matches:
                if score > 60:
                    code = [k for k, v in LOCALE_MAP.items() if v == match_name][0]
                    choices.append(app_commands.Choice(name=f"{match_name} ({code})", value=code))
        
        return choices[:25]

    @commands.hybrid_command(name="set-transfer-tax", description="Set the transfer tax rate (0.0 to 1.0)")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(tax_rate="Tax rate as decimal (e.g., 0.1 for 10%)")
    async def set_tax_transfer(self, ctx: commands.Context, tax_rate: float):
        TAX_CAP = 1.0

        # Ensure tax rate is between 0 and 1 (0% to 100%)
        tax_rate = max(0.0, min(tax_rate, TAX_CAP))

        percentage = tax_rate * 100
        try:
            await ensure_guild_cfg(self.bot.db, ctx.guild.id)
            async with self.bot.db.acquire() as conn:
                await conn.execute(
                    "UPDATE guild_config SET transfer_tax_rate = $1 WHERE guild_id = $2",
                    tax_rate, ctx.guild.id
                )

                embed = discord.Embed(
                    title="Transfer Tax Updated",
                    description=f"Transfer tax rate set to {percentage:.1f}%. Members will pay this tax on commands like `/give-coins`.",
                    color=discord.Color.green()
                )
                await ctx.reply(embed=embed)

        except Exception as e:
            logging.exception(e)
            embed = discord.Embed(
                title="Database Error",
                description="An error occurred while updating the tax rate. Please try again later.",
                color=discord.Color.red()
            )
            await ctx.reply(embed=embed)




    @commands.hybrid_command(name="get-transfer-tax", description="Get the current transfer tax rate")
    async def get_transfer_tax(self, ctx: commands.Context):
        try:
            await ensure_guild_cfg(self.bot.db, ctx.guild.id)
            async with self.bot.db.acquire() as conn:
                tax_rate = await conn.fetchval(
                    "SELECT transfer_tax_rate FROM guild_config WHERE guild_id = $1",
                    ctx.guild.id
                )

                if tax_rate is None:
                    tax_rate = 0.0

                percentage = tax_rate * 100
                embed = discord.Embed(
                    title="Transfer Tax Rate",
                    description=f"Current transfer tax rate: {percentage:.1f}%",
                    color=discord.Color.blue()
                )
                await ctx.reply(embed=embed)

        except Exception as e:
            logging.exception(e)
            embed = discord.Embed(
                title="Database Error",
                description="An error occurred while retrieving the tax rate. Please try again later.",
                color=discord.Color.red()
            )
            await ctx.reply(embed=embed)
    @commands.hybrid_command(name="set-prefix", description="Set server prefix")
    @commands.has_permissions(administrator=True)
    async def set_prefix(self, ctx: commands.Context, prefix: str):
        """Set a custom command prefix for the server."""
        if len(prefix) > 10:
            embed = discord.Embed(
                title="Prefix too long",
                description="The prefix must not exceed 10 characters.",
                color=discord.Color.red()
            )
            await ctx.reply(embed=embed)
            return

        try:
            async with self.bot.db.acquire() as conn:
                await conn.execute(
                    "UPDATE guild_config SET prefix = $1 WHERE guild_id = $2",
                    prefix,
                    ctx.guild.id
                )

            embed = discord.Embed(
                title="Prefix Updated",
                description=f"The server prefix has been set to: `{prefix}`",
                color=discord.Color.green()
            )
            await ctx.reply(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="Database Error",
                description="An error occurred while updating the prefix. Please try again later. Contact bot dev :(",
                color=discord.Color.red()
            )
            
            await ctx.reply(embed=embed)

    @commands.hybrid_command(name="allow-rob", description="Toggles robbing in your server")
    @commands.has_permissions(administrator=True)
    async def set_rob(self, ctx: commands.Context):
        """Toggles robbing feature for the server."""
        try:
            async with self.bot.db.acquire() as conn:

                allow = await conn.fetchval("SELECT allow_rob FROM guild_config WHERE guild_id = $1", ctx.guild.id)
                
                
                if allow is None:
                    print("So allow is none here")
                    allow = True


                new_allow = not allow


                await conn.execute(
                    "UPDATE guild_config SET allow_rob = $1 WHERE guild_id = $2", new_allow, ctx.guild.id
                )


                


            embed = discord.Embed(
                title="Robbing Feature Updated",
                description=f"Robbing is now {'enabled' if new_allow else 'disabled'} in this server.",
                color=discord.Color.green()
            )

            await ctx.reply(embed=embed)

        except Exception as e:
     
            embed = discord.Embed(
                title="Database Error",
                description="An error occurred while updating the robbing feature. Please try again later. Contact bot dev :(",
                color=discord.Color.red()
            )
            logging.error(e)
            await ctx.reply(embed=embed)

    @commands.hybrid_command(name="set-locale", description="Set server language")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(locale="Choose server language")
    @app_commands.autocomplete(locale=locale_autocomplete)
    async def set_locale(self, ctx: commands.Context, locale: str):
        if locale not in LOCALE_MAP:
            return await ctx.reply(f"Invalid locale code: `{locale}`")
        
        async with self.bot.db.acquire() as conn:
            await conn.execute(
                "UPDATE guild_config SET locale = $1 WHERE guild_id = $2",
                locale, ctx.guild.id
            )
        
        lang_name = LOCALE_MAP[locale]
        embed = discord.Embed(
            title="Server Locale Updated",
            description=f"Server language has been set to **{lang_name}** (`{locale}`)",
            color=discord.Color.green()
        )
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="get-locale", description="Check server language setting")
    async def get_locale(self, ctx: commands.Context):
        async with self.bot.db.acquire() as conn:
            locale = await conn.fetchval("SELECT locale FROM guild_config WHERE guild_id = $1", ctx.guild.id)
        
        if not locale:
            embed = discord.Embed(
                title="Server Locale",
                description="Server has no locale set. Using user locales.",
                color=discord.Color.blue()
            )
            return await ctx.reply(embed=embed)
        
        lang_name = LOCALE_MAP.get(locale, "Unknown")
        embed = discord.Embed(
            title="Server Locale",
            description=f"Server language is **{lang_name}** (`{locale}`)",
            color=discord.Color.blue()
        )
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
