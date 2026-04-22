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
    async def playlocal(self, interaction: discord.Interaction, filename: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)

        full_path = os.path.join(config.MUSIC_FOLDER, filename)
        if not os.path.exists(full_path):
            return await interaction.response.send_message(f"❌ Файл `{filename}` не найден.", ephemeral=True)

        await interaction.response.defer()

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            try:
                # Увеличиваем таймаут подключения (стандартно там 15 сек, иногда не хватает)
                voice_client = await voice_channel.connect(timeout=20.0)
            except asyncio.TimeoutError:
                # Если Discord затупил, сбрасываем зависшее состояние
                if interaction.guild.voice_client:
                    await interaction.guild.voice_client.disconnect(force=True)
                return await interaction.followup.send(
                    "❌ Discord не отвечает. Не удалось подключиться к голосовому каналу (Таймаут). Попробуй еще раз.")
            except Exception as e:
                return await interaction.followup.send(f"❌ Ошибка подключения: {e}")
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        # Создаем аудио-источник сразу
        source = discord.FFmpegPCMAudio(full_path)

        queue = get_queue(self.bot, interaction.guild.id)
        queue.append({
            'source': source,
            'title': filename,
            'duration_sec': 0,  # Можно оставить 0, если не читаем длительность файла
            'user_mention': interaction.user.mention,
            'type': 'Local',
            'channel': interaction.channel
        })

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"➕ Добавлено в очередь: **{filename}**")
        else:
            await play_next(self.bot, interaction.guild)
            await interaction.followup.send(f"🎶 Играю локальный файл: **{filename}**", ephemeral=True)

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