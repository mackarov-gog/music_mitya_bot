
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import aiohttp
import config

# -------------------- НАСТРОЙКИ yt-dlp --------------------
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# -------------------- НАСТРОЙКИ ДЛЯ РАДИО --------------------
RADIO_FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# -------------------- ПОИСК РАДИОСТАНЦИЙ --------------------
async def search_radio_stations(query: str, limit: int = 10):
    """Ищет радиостанции на radio-browser.info, сортируя по популярности."""
    url = "https://de1.api.radio-browser.info/json/stations/search"
    params = {
        "name": query,
        "limit": limit,
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data

# -------------------- ВЫБОР РАДИОСТАНЦИИ --------------------
class RadioSelectView(discord.ui.View):
    def __init__(self, stations, ctx):
        super().__init__(timeout=60)
        self.stations = stations
        self.ctx = ctx
        self.selected_station = None

        select = discord.ui.Select(
            placeholder="Выберите радиостанцию...",
            options=[
                discord.SelectOption(
                    label=f"{station['name'][:50]}",
                    description=f"🌍 {station.get('country', 'Неизвестно')} | 🎧 {station.get('clickcount', 0)}",
                    value=str(i)
                ) for i, station in enumerate(stations[:10])
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Эта команда была вызвана другим пользователем!", ephemeral=True)
            return
        self.selected_station = self.stations[int(interaction.data["values"][0])]
        await interaction.response.defer()
        self.stop()

# -------------------- ОСНОВНОЙ БОТ --------------------
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **config.FFMPEG_STREAM_OPTIONS), data=data)

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.queues = {}

    async def setup_hook(self):
        await self.add_cog(MusicCog(self))

bot = MusicBot()

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_queue(self, guild_id):
        if guild_id not in self.bot.queues:
            self.bot.queues[guild_id] = []
        return self.bot.queues[guild_id]

    async def play_next(self, guild):
        queue = self.get_queue(guild.id)
        if not queue:
            return
        item = queue.pop(0)
        voice_client = guild.voice_client
        if not voice_client:
            return

        if isinstance(item, dict) and 'path' in item:
            source = discord.FFmpegPCMAudio(
                item['path'],
                **config.FFMPEG_LOCAL_OPTIONS
            )
            title = item['title']
        else:
            source = item['source']
            title = item['title']
            source.volume = 0.5

        def after_play(error):
            if error:
                print(f'Ошибка воспроизведения: {error}')
            future = asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)
            try:
                future.result()
            except Exception as e:
                print(f'Ошибка при воспроизведении следующего трека: {e}')

        voice_client.play(source, after=after_play)
        channel = guild.system_channel or discord.utils.get(guild.text_channels, name='general')
        if channel:
            await channel.send(f"🎶 Сейчас играет: **{title}**")

    # -------------------- КОМАНДА РАДИО --------------------
    @commands.command(name='радио', aliases=['radio'])
    async def radio_command(self, ctx, *, query: str):
        """Воспроизвести интернет-радио по названию или стране."""
        if not ctx.author.voice:
            await ctx.send("❌ Вы не в голосовом канале!")
            return

        # Очищаем очередь и останавливаем текущее воспроизведение
        self.get_queue(ctx.guild.id).clear()
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        await ctx.send(f"📡 Ищу радиостанции по запросу **{query}**...")
        stations = await search_radio_stations(query)
        if not stations:
            await ctx.send(f"❌ Ничего не найдено по запросу `{query}`.")
            return

        # Показываем список для выбора
        embed = discord.Embed(
            title="📻 Доступные радиостанции",
            description=f"По запросу **{query}** найдено {len(stations)} станций. Выберите из списка ниже:",
            color=discord.Color.blue()
        )
        for i, station in enumerate(stations[:10], 1):
            embed.add_field(
                name=f"{i}. {station['name'][:50]}",
                value=f"🌍 {station.get('country', 'Неизвестно')} | 🎧 {station.get('clickcount', 0)} кликов",
                inline=False
            )

        view = RadioSelectView(stations, ctx)
        await ctx.send(embed=embed, view=view)
        await view.wait()

        if view.selected_station is None:
            await ctx.send("⏰ Время на выбор истекло. Попробуйте снова.")
            return

        station = view.selected_station
        stream_url = station['url']
        station_name = station['name']

        # Подключение к голосовому каналу
        voice_channel = ctx.author.voice.channel
        voice_client = ctx.voice_client

        if voice_client is None:
            try:
                await voice_channel.connect()
                await asyncio.sleep(1)
            except Exception as e:
                await ctx.send(f"❌ Ошибка подключения к голосовому каналу: {e}")
                return
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        voice_client = ctx.voice_client
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Не удалось подключиться к голосовому каналу. Проверьте права бота.")
            return

        # Воспроизводим радио
        try:
            source = discord.FFmpegPCMAudio(stream_url, **RADIO_FFMPEG_OPTIONS)
            voice_client.play(source)  # без after, чтобы не запускать очередь
            await ctx.send(f"🎶 **Сейчас играет радио:** {station_name}")
        except Exception as e:
            await ctx.send(f"❌ Ошибка воспроизведения: {e}")

    # -------------------- ОСТАЛЬНЫЕ МУЗЫКАЛЬНЫЕ КОМАНДЫ --------------------
    @commands.command(name='плей', aliases=['play', 'p'])
    async def play(self, ctx, *, query):
        voice = ctx.author.voice
        if not voice:
            await ctx.send("❌ Вы не в голосовом канале!")
            return
        voice_channel = voice.channel
        voice_client = ctx.voice_client

        if not voice_client:
            await voice_channel.connect()
            voice_client = ctx.voice_client

        await ctx.send(f"🔍 Ищу: {query}")

        try:
            source = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
        except Exception as e:
            await ctx.send(f"❌ Ошибка поиска: {e}")
            return

        queue = self.get_queue(ctx.guild.id)
        queue.append({'source': source, 'title': source.title, 'is_local': False})

        if voice_client.is_playing() or voice_client.is_paused():
            await ctx.send(f"➕ Добавлено в очередь: **{source.title}**")
        else:
            await self.play_next(ctx.guild)

    @commands.command(name='плейлокальный', aliases=['playlocal', 'pl'])
    async def play_local(self, ctx, *, filename):
        voice = ctx.author.voice
        if not voice:
            await ctx.send("❌ Вы не в голосовом канале!")
            return
        voice_channel = voice.channel
        voice_client = ctx.voice_client

        if not voice_client:
            await voice_channel.connect()
            voice_client = ctx.voice_client

        full_path = os.path.join(config.MUSIC_FOLDER, filename)
        if not os.path.exists(full_path):
            await ctx.send(f"❌ Файл `{filename}` не найден в папке `{config.MUSIC_FOLDER}`")
            return

        queue = self.get_queue(ctx.guild.id)
        queue.append({'path': full_path, 'title': filename, 'is_local': True})

        if voice_client.is_playing() or voice_client.is_paused():
            await ctx.send(f"➕ Добавлено в очередь: **{filename}**")
        else:
            await self.play_next(ctx.guild)

    @commands.command(name='пропустить', aliases=['skip', 's', 'скип'])
    async def skip(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await ctx.send("⏭ Трек пропущен.")
        else:
            await ctx.send("🎵 Сейчас ничего не играет.")

    @commands.command(name='стоп', aliases=['stop', 'disconnect'])
    async def stop(self, ctx):
        voice_client = ctx.voice_client
        if voice_client:
            self.get_queue(ctx.guild.id).clear()
            voice_client.stop()
            await voice_client.disconnect()
            await ctx.send("🛑 Остановлено и отключено.")
        else:
            await ctx.send("🤖 Бот не в голосовом канале.")

    @commands.command(name='пауза', aliases=['pause'])
    async def pause(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await ctx.send("⏸ Пауза.")
        else:
            await ctx.send("🎵 Сейчас ничего не играет.")

    @commands.command(name='возобновить', aliases=['resume', 'unpause'])
    async def resume(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await ctx.send("▶ Возобновлено.")
        else:
            await ctx.send("🎵 Сейчас ничего не на паузе.")

    @commands.command(name='очередь', aliases=['queue', 'q'])
    async def queue(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send("📭 Очередь пуста.")
            return
        lines = []
        for i, item in enumerate(queue[:10], 1):
            title = item.get('title') if isinstance(item, dict) else item.get('title', 'Неизвестно')
            lines.append(f"{i}. {title}")
        await ctx.send("**Очередь:**\n" + "\n".join(lines))
        if len(queue) > 10:
            await ctx.send(f"и ещё {len(queue)-10} треков...")

    @commands.command(name='список', aliases=['listlocal', 'll'])
    async def list_local(self, ctx):
        try:
            files = [f for f in os.listdir(config.MUSIC_FOLDER) if os.path.isfile(os.path.join(config.MUSIC_FOLDER, f))]
        except FileNotFoundError:
            await ctx.send(f"📁 Папка `{config.MUSIC_FOLDER}` не найдена.")
            return
        if not files:
            await ctx.send("📁 Нет локальных треков.")
            return
        await ctx.send("**Доступные локальные треки:**\n" + "\n".join(files[:20]))

    @commands.command(name='очистить', aliases=['clearqueue', 'cq'])
    async def clear_queue(self, ctx):
        self.get_queue(ctx.guild.id).clear()
        await ctx.send("🧹 Очередь очищена.")

    # Проверка голосового канала перед командами
    @play.before_invoke
    @play_local.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("❌ Вы не в голосовом канале.")
                raise commands.CommandError("Не в голосовом канале.")

if __name__ == "__main__":
    bot.run(config.TOKEN)
