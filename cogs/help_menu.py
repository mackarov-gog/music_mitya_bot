import discord
from discord.ext import commands
from discord import app_commands
from utils import db
from utils.i18n import SUPPORTED_LANGUAGES, get_lang, set_lang, t, desc_localizations
from utils.music_player import load_guild_state, show_menu, get_universal_embed, playback_timers, last_played_items


class LanguageSelectView(discord.ui.View):
    """Select to choose the bot language for this guild."""

    def __init__(self, user, bot=None):
        super().__init__(timeout=60)
        self.user = user
        self.bot = bot

        options = [
            discord.SelectOption(label="🇷🇺 Русский", value="ru", description="Русский язык"),
            discord.SelectOption(label="🇬🇧 English", value="en", description="English language"),
        ]
        select = discord.ui.Select(placeholder="Выберите язык / Choose language", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "❌ Это не ваш выбор!", ephemeral=True
            )
        lang = interaction.data["values"][0]
        guild_id = interaction.guild.id

        await db.set_setting(guild_id, 'language', lang)
        set_lang(guild_id, lang)

        msg = (
            "✅ Язык установлен: 🇷🇺 Русский"
            if lang == 'ru'
            else "✅ Language set: 🇬🇧 English"
        )
        await interaction.response.edit_message(content=msg, view=None)
        self.stop()

        # Refresh any existing player panel with the new language.
        from utils.music_player import (
            last_player_messages, UniversalPlayerView,
            last_played_items, get_universal_embed, playback_timers,
        )
        existing = last_player_messages.get(guild_id)
        if existing is not None:
            try:
                stack = last_played_items.get(guild_id, [])
                item = stack[-1] if stack else None
                if item is not None:
                    await existing.edit(
                        embed=get_universal_embed(
                            item, interaction.guild, playback_timers.get(guild_id, 0)
                        ),
                        view=UniversalPlayerView(self.bot, guild_id, item),
                    )
            except Exception:
                pass


class HelpMenuCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _help_embed(self, guild_id: int) -> discord.Embed:
        lang = get_lang(guild_id)
        embed = discord.Embed(
            title=t(lang, 'help_title'),
            description=t(lang, 'help_desc'),
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name=t(lang, 'help_music'),
            value=(
                f"`/play <query>` — {t(lang, 'cmd_play')}\n"
                f"`/radio <query>` — {t(lang, 'cmd_radio')}\n"
                f"`/playlocal [name]` — {t(lang, 'cmd_playlocal')}"
            ),
            inline=False,
        )
        embed.add_field(
            name=t(lang, 'help_controls'),
            value=(
                f"`/volume <0-200>` — {t(lang, 'cmd_volume')}\n"
                f"`/queue` — {t(lang, 'cmd_queue')}\n"
                f"`/pause` / `/resume` — {t(lang, 'cmd_pause')} / {t(lang, 'cmd_resume')}\n"
                f"`/skip` — {t(lang, 'cmd_skip')}\n"
                f"`/skipto <count>` — {t(lang, 'cmd_skipto')}\n"
                f"`/seek <seconds>` — {t(lang, 'cmd_seek')}\n"
                f"`/stop` — {t(lang, 'cmd_stop')}"
            ),
            inline=False,
        )
        embed.add_field(
            name=t(lang, 'help_settings'),
            value=(
                f"`/chainplay` — {t(lang, 'cmd_chainplay')}\n"
                f"`/language` — {t(lang, 'cmd_language')}\n"
                f"`/menu` — {t(lang, 'cmd_menu')}\n"
                f"`/help` — {t(lang, 'cmd_help')}"
            ),
            inline=False,
        )
        embed.add_field(
            name=t(lang, 'help_player'),
            value=t(lang, 'player_buttons'),
            inline=False,
        )
        embed.add_field(
            name=t(lang, 'help_playlists'),
            value=t(lang, 'playlist_cmds'),
            inline=False,
        )
        embed.set_footer(text=t(lang, 'help_footer'))
        return embed

    @app_commands.command(name='help', description="Показать справку по командам")
    async def help(self, interaction: discord.Interaction):
        try:
            await load_guild_state(interaction.guild.id)
        except Exception:
            pass
        embed = self._help_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='language', description="Выбрать язык бота")
    async def language(self, interaction: discord.Interaction):
        try:
            await load_guild_state(interaction.guild.id)
        except Exception:
            pass
        view = LanguageSelectView(interaction.user, bot=self.bot)
        await interaction.response.send_message(
            "🌍 Выберите язык / Choose a language:",
            view=view,
        )

    @app_commands.command(name='menu', description="Показать панель управления плеером")
    async def menu(self, interaction: discord.Interaction):
        await show_menu(interaction, self.bot)


async def setup(bot):
    await bot.add_cog(HelpMenuCog(bot))