import discord
from discord.ext import commands
from discord import app_commands
from utils import db
from utils.i18n import desc_localizations
from utils.music_player import is_chain_play_enabled, set_chain_play, load_guild_state


class AutoplayCog(commands.Cog):
    """Persistent chain-play (autoplay) toggle."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='chainplay',
                          description="Режим «По цепочке»: бот сам подбирает следующий трек")
    async def chainplay(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id

        # Ensure in-memory mirrors are loaded
        try:
            await load_guild_state(guild_id)
        except Exception:
            pass

        current = is_chain_play_enabled(guild_id)
        new_state = not current

        await db.set_setting(guild_id, 'chain_play', new_state)
        set_chain_play(guild_id, new_state)

        status = "✅ **включён**" if new_state else "⏹ **выключен**"
        await interaction.response.send_message(
            f"🔗 Режим «По цепочке» {status}.\n"
            f"{'Бот будет сам подбирать похожие треки, когда очередь закончится.' if new_state else ''}"
        )


async def setup(bot):
    await bot.add_cog(AutoplayCog(bot))