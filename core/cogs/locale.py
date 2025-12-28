import discord
from discord.ext import commands
from discord import app_commands
import pycountry
from rapidfuzz import process, fuzz

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
    "uz": "Uzbek - O‘zbek",
    "vi": "Vietnamese - Tiếng Việt",
    "cy": "Welsh - Cymraeg",
    "xh": "Xhosa - isiXhosa",
    "yi": "Yiddish - ייִדיש",
    "yo": "Yoruba - Yorùbá",
    "zu": "Zulu - isiZulu"
}


class LocaleCog(commands.Cog):
    def __init__(self, bot):
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

    @commands.hybrid_command(name="setlocale", description="Set your preferred language")
    @app_commands.describe(locale="Choose your language")
    @app_commands.autocomplete(locale=locale_autocomplete)
    async def setlocale(self, ctx: commands.Context, locale: str):
        if locale not in LOCALE_MAP:
            return await ctx.reply(f"Invalid locale code: `{locale}`")
        
        async with self.bot.db.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_config(user_id, locale) VALUES($1, $2) ON CONFLICT(user_id) DO UPDATE SET locale = $2",
                ctx.author.id, locale
            )
        
        lang_name = LOCALE_MAP[locale]
        await ctx.reply(f"Your locale has been set to **{lang_name}** (`{locale}`)")

    @commands.hybrid_command(name="getlocale", description="Check your current language setting")
    async def getlocale(self, ctx: commands.Context):
        async with self.bot.db.acquire() as conn:
            locale = await conn.fetchval("SELECT locale FROM user_config WHERE user_id = $1", ctx.author.id)
        
        if not locale:
            locale = "en"
        
        lang_name = LOCALE_MAP.get(locale, "Unknown")
        await ctx.reply(f"Your current locale is **{lang_name}** (`{locale}`)")

async def setup(bot):
    await bot.add_cog(LocaleCog(bot))
