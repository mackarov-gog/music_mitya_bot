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

    @app_commands.command(name='radio', description="Включить интернет-радио по названию или стране")
    @app_commands.describe(query="Название радиостанции или жанр")
    async def radio(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)

        await interaction.response.defer() # Говорим дискорду "подожди, я ищу"

        get_queue(self.bot, interaction.guild.id).clear()
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()

        stations = await search_radio_stations(query)
        if not stations:
            return await interaction.followup.send(f"❌ Ничего не найдено по запросу `{query}`.")

        embed = discord.Embed(
            title="📻 Доступные радиостанции",
            description=f"Найдено {len(stations)} станций. Выберите из списка:",
            color=discord.Color.blue()
        )

        view = RadioSelectView(stations, interaction.user)
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await view.wait()

        if view.selected_station is None:
            return await message.edit(content="⏰ Время на выбор истекло.", embed=None, view=None)

        station = view.selected_station
        stream_url = station['url']
        station_name = station['name']

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        try:
            source = discord.FFmpegPCMAudio(stream_url, **config.RADIO_FFMPEG_OPTIONS)

            def after_radio(error):
                if error:
                    print(f'Ошибка воспроизведения радио: {error}')
                asyncio.run_coroutine_threadsafe(play_next(self.bot, interaction.guild), self.bot.loop)

            voice_client.play(source, after=after_radio)

            await message.edit(content=f"🎶 **Сейчас играет радио:** {station_name}", embed=None, view=None)
        except Exception as e:
            await message.edit(content=f"❌ Ошибка воспроизведения: {e}", embed=None, view=None)

async def setup(bot):
    await bot.add_cog(RadioCog(bot))