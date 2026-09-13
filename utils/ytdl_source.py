import discord
import yt_dlp
import asyncio
import config

# Настройки для FFmpeg (только поддерживаемые параметры)
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}


ytdl_options = config.YTDL_FORMAT_OPTIONS.copy()
ytdl_options['ignoreerrors'] = True

ytdl_options['extractor_args'] = {
'youtube': {
'player_client': ['android', 'web']
}
}

ytdl = yt_dlp.YoutubeDL(ytdl_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def extract_info(cls, url, *, loop=None, download=False):
        """Resolve a URL (or search query result) into its info dict.

        Returns the info dict (for single entries) or the first entry of a playlist.
        """
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(url, download=download)
            )
        except Exception as e:
            print(f"Ошибка yt-dlp extract_info: {e}")
            if isinstance(e, yt_dlp.utils.DownloadError):
                return None
            raise
        if not data:
            return None
        if 'entries' in data:
            data = data['entries'][0] if data['entries'] else None
        return data

    @classmethod
    async def search(cls, query, *, loop=None):
        """Search YouTube and return a list of entry dicts (max 15)."""
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(f"ytsearch15:{query}", download=False)
            )

            if not data:
                return []

            return [entry for entry in data.get('entries', []) if entry is not None]

        except Exception as e:
            print(f"Ошибка поиска yt-dlp: {e}")
            return []

    @classmethod
    async def extract_playlist(cls, url: str, *, loop=None, limit: int = 50) -> list[dict]:
        """Extract all entries from a playlist URL (up to `limit`).

        Returns a list of entry dicts (with webpage_url, title, duration).
        Empty list on failure or non-playlist URL.
        """
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(url, download=False, process=True)
            )
        except Exception as e:
            print(f"Ошибка извлечения плейлиста yt-dlp: {e}")
            return []

        if not data or 'entries' not in data:
            return []

        entries = []
        for entry in data.get('entries', []):
            if entry is None:
                continue
            if entry.get('webpage_url') is None:
                continue
            entries.append({
                'title': entry.get('title') or 'Неизвестный трек',
                'webpage_url': entry.get('webpage_url'),
                'duration': int(entry.get('duration') or 0),
                'thumbnail': entry.get('thumbnail'),
            })
            if len(entries) >= limit:
                break
        return entries

    @classmethod
    async def regather_stream(cls, data, *, loop=None, volume=1.0):
        """Re-resolve a previously found entry and build a streaming source."""
        loop = loop or asyncio.get_event_loop()
        info = await cls.extract_info(data['webpage_url'], loop=loop, download=False)
        if info is None:
            return None
        source = discord.FFmpegPCMAudio(info['url'], **ffmpeg_options)
        return cls(source, data=info, volume=volume)

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, volume=1.0):
        """Build a source directly from a URL (YouTube or other extractor)."""
        loop = loop or asyncio.get_event_loop()
        try:
            data = await cls.extract_info(url, loop=loop, download=not stream)
            if data is None:
                return None

            if 'entries' in data:
                data = data['entries'][0]

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
            return cls(source, data=data, volume=volume)
        except Exception as e:
            print(f"Ошибка при загрузке по URL: {e}")
            return None