import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
from utils.ytdl_source import YTDLSource
from utils.music_player import get_queue, play_next


class TrackSelectView(discord.ui.View):
    def __init__(self, items, user):
        super().__init__(timeout=30)
        self.user = user
        self.index = None

        options = [
            discord.SelectOption(
                label=f"{item['title'][:50]}",
                description=f"Длительность: {str(datetime.timedelta(seconds=item.get('duration', 0)))}",
                value=str(i)
            ) for i, item in enumerate(items)
        ]
        self.select = discord.ui.Select(placeholder="Выберите трек...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Это не ваш поиск!", ephemeral=True)
        self.index = int(self.select.values[0])
        await interaction.response.defer()
        self.stop()


class YouTubeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='play', description="Найти и воспроизвести музыку")
    @app_commands.describe(query="Название песни или ссылка")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)

        await interaction.response.defer()


        if query.startswith("http"):
            try:
                source = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
                selected_data = source.data
            except Exception as e:
                return await interaction.followup.send(f"❌ Ошибка загрузки: {e}")
        else:
            tracks = await YTDLSource.search(query, loop=self.bot.loop)
            if not tracks:
                return await interaction.followup.send("❌ Ничего не найдено.")

            view = TrackSelectView(tracks, interaction.user)
            search_msg = await interaction.followup.send("🔎 **Результаты поиска:**", view=view)
            await view.wait()

            if view.index is None:
                return await search_msg.edit(content="⏰ Время поиска истекло.", view=None)

            selected_data = tracks[view.index]
            await search_msg.delete()
            source = await YTDLSource.regather_stream(selected_data, loop=self.bot.loop)


        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await interaction.user.voice.channel.connect()


        queue = get_queue(self.bot, interaction.guild.id)
        duration_str = str(datetime.timedelta(seconds=selected_data.get('duration', 0)))

        queue.append({
            'source': source,
            'title': source.title,
            'duration': duration_str,
            'user_mention': interaction.user.mention,
            'is_local': False
        })

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"➕ Добавлено в очередь: **{source.title}**")
        else:
            await interaction.followup.send(f"🎶 Начинаю играть: **{source.title}**")
            await play_next(self.bot, interaction.guild)

    @app_commands.command(name='skip', description="Пропустить текущий трек")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭ Трек пропущен.")
        else:
            await interaction.response.send_message("🎵 Сейчас ничего не играет.", ephemeral=True)

    @app_commands.command(name='stop', description="Остановить и очистить очередь")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            get_queue(self.bot, interaction.guild.id).clear()
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("🛑 Бот отключен.")
        else:
            await interaction.response.send_message("🤖 Бот не в канале.", ephemeral=True)

    @app_commands.command(name='queue', description="Показать очередь")
    async def queue(self, interaction: discord.Interaction):
        queue = get_queue(self.bot, interaction.guild.id)
        if not queue:
            return await interaction.response.send_message("📭 Очередь пуста.")

        lines = [f"{i + 1}. {item['title']} (`{item.get('duration', '??')}`)" for i, item in enumerate(queue[:10])]
        msg = "**Очередь:**\n" + "\n".join(lines)
        if len(queue) > 10:
            msg += f"\n*и ещё {len(queue) - 10}...*"
        await interaction.response.send_message(msg)

    @app_commands.command(name='pause', description="Пауза")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸")
        else:
            await interaction.response.send_message("❌ Ничего не играет.", ephemeral=True)

    @app_commands.command(name='resume', description="Продолжить")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️")
        else:
            await interaction.response.send_message("❌ Не на паузе.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(YouTubeCog(bot))