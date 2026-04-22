import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from utils.radio_api import search_radio_stations
from utils.music_player import get_queue, play_next
import config

class RadioSelectView(discord.ui.View):
    def __init__(self, stations, user):
        super().__init__(timeout=60)
        self.stations = stations
        self.user = user
        self.selected_station = None

        options = [
            discord.SelectOption(
                label=f"{station['name'][:50]}",
                description=f"🌍 {station.get('country', 'Неизвестно')} | 🎧 {station.get('clickcount', 0)}",
                value=str(i)
            ) for i, station in enumerate(stations[:10])
        ]
        select = discord.ui.Select(placeholder="Выберите радиостанцию...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Вы не можете выбирать на чужом пульте!", ephemeral=True)
            return
        self.selected_station = self.stations[int(interaction.data["values"][0])]
        await interaction.response.defer()
        self.stop()

class RadioCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='radio', description="Включить интернет-радио")
    async def radio(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)

        await interaction.response.defer()

        # 1. Поиск станций
        stations = await search_radio_stations(query)
        if not stations:
            return await interaction.followup.send(f"❌ Ничего не найдено.")

        # 2. Выбор станции пользователем
        view = RadioSelectView(stations, interaction.user)
        message = await interaction.followup.send("📻 Выберите станцию:", view=view)
        await view.wait()

        if view.selected_station is None:
            return await message.edit(content="⏰ Время истекло.", view=None)

        station = view.selected_station

        # 3. ПОДКЛЮЧЕНИЕ К КАНАЛУ
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

        # 4. Подготовка данных для плеера
        queue = get_queue(self.bot, interaction.guild.id)
        queue.clear()  # Для радио очищаем очередь

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        # Создаем источник
        source = discord.FFmpegPCMAudio(station['url'], **config.RADIO_FFMPEG_OPTIONS)

        queue.append({
            'source': source,
            'title': station['name'],
            'url': station['url'],
            'duration_sec': 0,
            'user_mention': interaction.user.mention,
            'type': 'Radio',
            'channel': interaction.channel
        })

        # 5. Запуск
        await play_next(self.bot, interaction.guild)
        await message.edit(content=f"📻 Играет радио: **{station['name']}**", view=None)

async def setup(bot):
    await bot.add_cog(RadioCog(bot))