import discord
import yt_dlp
import asyncio
import config

# Настройки для FFmpeg (только поддерживаемые параметры)
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# Если вы хотите, чтобы yt-dlp игнорировал ошибки, это делается здесь
ytdl_options = config.YTDL_FORMAT_OPTIONS.copy()
ytdl_options['ignoreerrors'] = True
ytdl = yt_dlp.YoutubeDL(ytdl_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def search(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        try:
            # Пытаемся найти треки
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(f"ytsearch15:{query}", download=False)
            )

            if not data:
                return []

            # Оставляем только те результаты, которые успешно извлеклись
            return [entry for entry in data.get('entries', []) if entry is not None]

        except Exception as e:
            print(f"Ошибка поиска yt-dlp: {e}")
            return []

    @classmethod
    async def regather_stream(cls, data, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        # Повторно получаем прямую ссылку перед проигрыванием
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(data['webpage_url'], download=False))
        return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data)

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

            if 'entries' in data:
                data = data['entries'][0]

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except Exception as e:
            print(f"Ошибка при загрузке по URL: {e}")
            return None