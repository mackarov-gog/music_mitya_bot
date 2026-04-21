import discord
import yt_dlp
import asyncio
import config

ytdl = yt_dlp.YoutubeDL(config.YTDL_FORMAT_OPTIONS)

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
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False))
        return data.get('entries', [])

    @classmethod
    async def regather_stream(cls, data, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(data['webpage_url'], download=False))
        return cls(discord.FFmpegPCMAudio(data['url'], **config.FFMPEG_STREAM_OPTIONS), data=data)