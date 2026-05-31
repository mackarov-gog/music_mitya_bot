import discord
import asyncio
import datetime
from utils.ytdl_source import YTDLSource
import config

last_played_titles = {}

queues = {}
playback_timers = {}


last_player_messages = {}
radio_pause_states = {}


def get_queue(bot, guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]


class UniversalPlayerView(discord.ui.View):
    def __init__(self, bot, guild_id, item):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.item = item

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if not vc: return

        is_radio = self.item.get('type') == 'Radio'
        guild_id = self.guild_id

        if vc.is_playing():
            if is_radio:
                radio_pause_states[guild_id] = True
                queue = get_queue(self.bot, guild_id)
                radio_item = self.item.copy()
                radio_item.pop('source', None)
                queue.insert(0, radio_item)
                vc.stop()
            else:
                vc.pause()
        elif vc.is_paused() or radio_pause_states.get(guild_id):
            if is_radio and radio_pause_states.get(guild_id):
                radio_pause_states[guild_id] = False
                await play_next(self.bot, interaction.guild)
                return
            else:
                vc.resume()

        current_time = playback_timers.get(guild_id, 0)
        try:
            await interaction.edit_original_response(
                embed=get_universal_embed(self.item, interaction.guild, current_time)
            )
        except discord.NotFound:
            pass

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc:
            if radio_pause_states.get(self.guild_id):
                radio_pause_states[self.guild_id] = False
                get_queue(self.bot, self.guild_id).pop(0)
                await play_next(self.bot, interaction.guild)
            else:
                vc.stop()

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.primary, label="Очередь")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.bot, self.guild_id)
        if not queue:
            return await interaction.response.send_message("📭 Очередь пуста.", ephemeral=True)

        embed = discord.Embed(title="📜 Текущая очередь", color=discord.Color.blue())
        description = ""
        for i, track in enumerate(queue[:10], 1):
            title = track.get('title', 'Неизвестный трек')
            user = track.get('user_mention', 'Система')
            description += f"**{i}.** {title} — {user}\n"

        if len(queue) > 10:
            description += f"\n*...и ещё {len(queue) - 10} треков*"

        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc:
            get_queue(self.bot, self.guild_id).clear()
            playback_timers[self.guild_id] = 0
            radio_pause_states[self.guild_id] = False
            vc.stop()
            try:
                await vc.disconnect()
            except:
                pass

            if self.guild_id in last_player_messages:
                del last_player_messages[self.guild_id]

            try:
                await interaction.edit_original_response(content="🛑 **Плеер остановлен**", embed=None, view=None)
            except discord.NotFound:
                await interaction.followup.send("🛑 Плеер остановлен", ephemeral=True)


def get_universal_embed(item, guild, current_time=0):
    title = item.get('title', 'Неизвестно')
    duration = item.get('duration_sec', 0)
    user = item.get('user_mention', 'Система')

    vc = guild.voice_client
    is_paused = (vc and vc.is_paused()) or radio_pause_states.get(guild.id, False)
    status = "⏸ На паузе" if is_paused else "▶️ Играет"

    embed = discord.Embed(title=f"🎶 Сейчас играет", description=f"**{title}**", color=discord.Color.blurple())

    queue_len = len(get_queue(None, guild.id))

    if duration > 0:
        percent = min(current_time / duration, 1.0)
        bar_length = 15
        filled = int(bar_length * percent)
        bar = "▬" * filled + "🔘" + "▬" * max(0, (bar_length - filled - 1))

        cur_str = str(datetime.timedelta(seconds=int(current_time)))
        tot_str = str(datetime.timedelta(seconds=int(duration)))
        embed.add_field(name="Прогресс", value=f"[`{bar}`]\n`{cur_str} / {tot_str}`", inline=False)
    else:
        embed.add_field(name="Прогресс", value="`🔴 Прямой эфир / Локальный файл`", inline=False)

    embed.add_field(name="Статус", value=status, inline=True)
    embed.add_field(name="В очереди", value=f"{queue_len} треков", inline=True)
    embed.add_field(name="Заказал", value=user, inline=True)
    return embed


async def update_player_status(message, item, guild):
    duration = item.get('duration_sec', 0)
    guild_id = guild.id
    playback_timers[guild_id] = 0
    step = 15


    while guild.voice_client and (
            guild.voice_client.is_playing() or guild.voice_client.is_paused() or radio_pause_states.get(guild_id)):
        if guild.voice_client.is_playing():
            playback_timers[guild_id] += step

        elapsed = playback_timers[guild_id]

        if duration > 0 and elapsed >= duration:
            break

        try:
            await message.edit(embed=get_universal_embed(item, guild, elapsed))
        except Exception:
            break

        await asyncio.sleep(step)


async def play_next(bot, guild):
    guild_id = guild.id


    if radio_pause_states.get(guild_id):
        return


    if guild_id in last_player_messages:
        try:
            await last_player_messages[guild_id].delete()
        except Exception:
            pass
        del last_player_messages[guild_id]

    queue = get_queue(bot, guild_id)


    if not queue and config.CHAIN_PLAY_ENABLED.get(guild_id, False):
        last_title = last_played_titles.get(guild_id)
        if last_title:

            search_query = f"{last_title} mix"
            tracks = await YTDLSource.search(search_query, loop=bot.loop)
            if tracks:

                next_track = tracks[1] if len(tracks) > 1 else tracks[0]
                source = await YTDLSource.regather_stream(next_track, loop=bot.loop)
                queue.append({
                    'source': source,
                    'title': source.title,
                    'user_mention': "🤖 Авто-DJ",
                    'type': 'YouTube'
                })



    if not queue:
        playback_timers[guild_id] = 0
        return

    item = queue.pop(0)
    playback_timers[guild_id] = 0
    last_played_titles[guild_id] = item['title']

    voice_client = guild.voice_client
    if not voice_client: return


    if 'source' not in item or item['source'] is None:
        if item.get('type') == 'Radio':
            import config
            opts = getattr(config, 'RADIO_FFMPEG_OPTIONS',
                           {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                            'options': '-vn'})
            item['source'] = discord.FFmpegPCMAudio(item['url'], **opts)
        elif item.get('type') == 'Local':
            import os, config
            full_path = os.path.join(config.MUSIC_FOLDER, item['title'])
            item['source'] = discord.FFmpegPCMAudio(full_path)

    voice_client.play(item['source'], after=lambda e: asyncio.run_coroutine_threadsafe(play_next(bot, guild), bot.loop))

    channel = item.get('channel')
    if channel:
        embed = get_universal_embed(item, guild, 0)
        view = UniversalPlayerView(bot, guild_id, item)
        msg = await channel.send(embed=embed, view=view)


        last_player_messages[guild_id] = msg


        bot.loop.create_task(update_player_status(msg, item, guild))