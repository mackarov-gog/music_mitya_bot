import discord
import asyncio
import config


def get_queue(bot, guild_id):
    if guild_id not in bot.queues:
        bot.queues[guild_id] = []
    return bot.queues[guild_id]


async def play_next(bot, guild):
    queue = get_queue(bot, guild.id)
    if not queue:
        return

    voice_client = guild.voice_client
    if not voice_client:
        return

    item = queue.pop(0)

    if 'path' in item:
        source = discord.FFmpegPCMAudio(item['path'], **config.FFMPEG_LOCAL_OPTIONS)
    else:
        source = item['source']
        source.volume = 0.5

    title = item['title']

    def after_play(error):
        if error:
            print(f'Ошибка воспроизведения: {error}')
        future = asyncio.run_coroutine_threadsafe(play_next(bot, guild), bot.loop)
        try:
            future.result()
        except Exception as e:
            print(f'Ошибка следующего трека: {e}')

    voice_client.play(source, after=after_play)