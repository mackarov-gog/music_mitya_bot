import discord
from discord.ext import commands
from discord import app_commands
import os
import config
from utils.music_player import get_queue, play_next


class LocalAudioCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='playlocal', description="Воспроизвести локальный файл")
    @app_commands.describe(filename="Название файла из папки music (с расширением)")
    async def playlocal(self, interaction: discord.Interaction, filename: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)

        full_path = os.path.join(config.MUSIC_FOLDER, filename)
        if not os.path.exists(full_path):
            return await interaction.response.send_message(f"❌ Файл `{filename}` не найден.", ephemeral=True)

        await interaction.response.defer()

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if not voice_client:
            voice_client = await voice_channel.connect()

        queue = get_queue(self.bot, interaction.guild.id)
        queue.append({'path': full_path, 'title': filename, 'is_local': True})

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"➕ Добавлено в очередь: **{filename}**")
        else:
            await interaction.followup.send(f"🎶 Начинаю воспроизведение: **{filename}**")
            await play_next(self.bot, interaction.guild)

    @app_commands.command(name='listlocal', description="Список доступных локальных треков")
    async def listlocal(self, interaction: discord.Interaction):
        try:
            files = [f for f in os.listdir(config.MUSIC_FOLDER) if os.path.isfile(os.path.join(config.MUSIC_FOLDER, f))]
        except FileNotFoundError:
            return await interaction.response.send_message(f"📁 Папка музыки не найдена.", ephemeral=True)

        if not files:
            return await interaction.response.send_message("📁 Нет локальных треков.")

        await interaction.response.send_message("**Доступные локальные треки:**\n" + "\n".join(files[:20]))


async def setup(bot):
    await bot.add_cog(LocalAudioCog(bot))