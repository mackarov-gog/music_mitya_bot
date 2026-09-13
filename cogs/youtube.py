import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
from utils.ytdl_source import YTDLSource
from utils.i18n import desc_localizations
from utils.music_player import (
    get_queue, play_next, load_guild_state, get_volume, set_volume,
    skip_tracks, seek_playback,
)


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
            ) for i, item in enumerate(items[:25])
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

    @app_commands.command(name='play', description="Найти и воспроизвести музыку",
                          description_localizations=desc_localizations('play'))
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Вы не в голосовом канале!", ephemeral=True)

        await interaction.response.defer()

        try:
            await load_guild_state(interaction.guild.id)
        except Exception:
            pass

        volume = await get_volume(interaction.guild.id) / 100.0
        selected_data = None
        playlist_entries = None

        if query.startswith("http"):
            try:
                # Try to detect a playlist first (list= or /playlist/ in URL)
                playlist_entries = await YTDLSource.extract_playlist(query, loop=self.bot.loop, limit=50)
                if not playlist_entries:
                    source = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, volume=volume)
                    if source is None:
                        return await interaction.followup.send("❌ Не удалось получить трек по ссылке.")
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
            source = await YTDLSource.regather_stream(selected_data, loop=self.bot.loop, volume=volume)
            if source is None:
                return await interaction.followup.send("❌ Не удалось загрузить трек.")

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            try:
                voice_client = await voice_channel.connect(timeout=20.0)
            except asyncio.TimeoutError:
                if interaction.guild.voice_client:
                    await interaction.guild.voice_client.disconnect(force=True)
                return await interaction.followup.send(
                    "❌ Discord не отвечает. Не удалось подключиться к голосовому каналу (Таймаут). Попробуй еще раз.")
            except Exception as e:
                return await interaction.followup.send(f"❌ Ошибка подключения: {e}")
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        queue = get_queue(self.bot, interaction.guild.id)

        # --- Playlist by link: enqueue all tracks lazily -------------------- #
        if playlist_entries:
            for entry in playlist_entries:
                queue.append({
                    'source': None,
                    'title': entry.get('title') or 'Неизвестный трек',
                    'url': entry.get('webpage_url'),
                    'thumbnail': entry.get('thumbnail'),
                    'duration_sec': int(entry.get('duration') or 0),
                    'user_mention': interaction.user.mention,
                    'type': 'YouTube',
                    'channel': interaction.channel
                })

            if voice_client.is_playing() or voice_client.is_paused():
                await interaction.followup.send(
                    f"📃 Добавлен плейлист: **{len(playlist_entries)} треков** добавлено в очередь."
                )
            else:
                await play_next(self.bot, interaction.guild)
                await interaction.followup.send(
                    f"📃 Плейлист запущен: **{len(playlist_entries)} треков** в очереди."
                )
            return

        # --- Single track ---------------------------------------------------- #
        queue.append({
            'source': source,
            'title': source.title,
            'url': selected_data.get('webpage_url'),
            'thumbnail': source.thumbnail,
            'duration_sec': int(selected_data.get('duration', 0)),
            'user_mention': interaction.user.mention,
            'type': 'YouTube',
            'channel': interaction.channel
        })

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"➕ Добавлено в очередь: **{source.title}**")
        else:
            await play_next(self.bot, interaction.guild)

    @app_commands.command(name='skip', description="Пропустить текущий трек",
                          description_localizations=desc_localizations('skip'))
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭ Трек пропущен.")
        else:
            await interaction.response.send_message("🎵 Сейчас ничего не играет.", ephemeral=True)

    @app_commands.command(name='skipto', description="Пропустить несколько треков (указать количество)",
                          description_localizations=desc_localizations('skipto'))
    async def skipto(self, interaction: discord.Interaction, count: int):
        if count < 1:
            return await interaction.response.send_message(
                "❌ Количество должно быть >= 1.", ephemeral=True
            )

        skipped = await skip_tracks(self.bot, interaction.guild, count)
        await interaction.response.send_message(
            f"⏭ Пропущено треков: **{skipped}**"
        )

    @app_commands.command(name='seek', description="Перемотать текущий трек на указанную секунду",
                          description_localizations=desc_localizations('seek'))
    async def seek(self, interaction: discord.Interaction, seconds: int):
        if seconds < 0:
            return await interaction.response.send_message(
                "❌ Секунды не могут быть отрицательными.", ephemeral=True
            )

        ok = await seek_playback(self.bot, interaction.guild, seconds)
        if not ok:
            return await interaction.response.send_message(
                "❌ Не удалось перемотать (радио нельзя перематывать).", ephemeral=True
            )

        import datetime as _dt
        pos = str(_dt.timedelta(seconds=seconds))
        await interaction.response.send_message(
            f"⏩ Перемотано на **{pos}**."
        )

    @app_commands.command(name='stop', description="Остановить и очистить очередь",
                          description_localizations=desc_localizations('stop'))
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            from utils.music_player import (
                queues, playback_timers, radio_pause_states,
                last_player_messages, last_played_items, repeat_states,
            )
            guild_id = interaction.guild.id
            queues.pop(guild_id, None)
            playback_timers.pop(guild_id, None)
            radio_pause_states.pop(guild_id, None)
            last_played_items.pop(guild_id, None)
            repeat_states.pop(guild_id, None)
            msg = last_player_messages.pop(guild_id, None)
            if msg is not None:
                try:
                    await msg.delete()
                except Exception:
                    pass
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("🛑 Бот отключен.")
        else:
            await interaction.response.send_message("🤖 Бот не в канале.", ephemeral=True)

    @app_commands.command(name='queue', description="Показать очередь",
                          description_localizations=desc_localizations('queue'))
    async def queue(self, interaction: discord.Interaction):
        from utils.music_player import QueuePaginationView
        queue = get_queue(self.bot, interaction.guild.id)
        if not queue:
            return await interaction.response.send_message("📭 Очередь пуста.")

        view = QueuePaginationView(self.bot, interaction.guild.id, queue[:50])
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name='pause', description="Пауза",
                          description_localizations=desc_localizations('pause'))
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸")
        else:
            await interaction.response.send_message("❌ Ничего не играет.", ephemeral=True)

    @app_commands.command(name='resume', description="Продолжить",
                          description_localizations=desc_localizations('resume'))
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️")
        else:
            await interaction.response.send_message("❌ Не на паузе.", ephemeral=True)

    @app_commands.command(name='volume', description="Установить громкость (0–200%)",
                          description_localizations=desc_localizations('volume'))
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 200:
            return await interaction.response.send_message("❌ Громкость должна быть от 0 до 200.", ephemeral=True)

        await set_volume(interaction.guild.id, level)

        # Применить к текущему источнику мгновенно
        vc = interaction.guild.voice_client
        if vc and vc.source:
            source = vc.source
            if isinstance(source, discord.PCMVolumeTransformer):
                source.volume = level / 100.0

        await interaction.response.send_message(f"🔊 Громкость установлена: **{level}%**")


async def setup(bot):
    await bot.add_cog(YouTubeCog(bot))