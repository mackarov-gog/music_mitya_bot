"""Universal queue player: state dicts, lazy source building, player view, embeds.

This module is the single source of truth for playback orchestration.
Cogs append queue items (see docs/QUEUE_CONTRACT.md) and call play_next().
"""
import asyncio
import datetime
import os
import random

import discord

import config
from utils.db import get_setting, set_setting
from utils.i18n import get_lang, set_lang, t
from utils.ytdl_source import YTDLSource

# --------------------------------------------------------------------------- #
# Per-guild state (in-memory; playlists/settings persist in SQLite)
# --------------------------------------------------------------------------- #

queues = {}                # guild_id -> list[queue_item]
playback_timers = {}       # guild_id -> int (seconds elapsed)
radio_pause_states = {}    # guild_id -> bool
last_player_messages = {}  # guild_id -> discord.Message
last_played_titles = {}    # guild_id -> str (legacy compatibility)
last_played_items = {}     # guild_id -> list[queue_item] (stack, max 10)
repeat_states = {}         # guild_id -> 'off' | 'one' | 'all'
volume_states = {}         # guild_id -> int (0-200, default 100) in-memory mirror
autoplay_history = {}      # guild_id -> set[str] of URLs already autoplayed (avoid loops)

LAST_PLAYED_STACK_MAX = 10


def get_queue(bot, guild_id):
    """Return (and lazily create) the queue list for a guild."""
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]


# --------------------------------------------------------------------------- #
# Volume helpers
# --------------------------------------------------------------------------- #

async def get_volume(guild_id: int) -> int:
    """Return in-memory volume, falling back to the persisted value."""
    if guild_id not in volume_states:
        volume_states[guild_id] = await get_setting(guild_id, 'volume', 100) or 100
    return volume_states[guild_id]


async def set_volume(guild_id: int, level: int) -> None:
    """Update in-memory volume and persist it."""
    level = max(0, min(200, int(level)))
    volume_states[guild_id] = level
    await set_setting(guild_id, 'volume', level)


# --------------------------------------------------------------------------- #
# Lazy source construction
# --------------------------------------------------------------------------- #

def _safe_local_path(file_name: str) -> str:
    """Join a file name with MUSIC_FOLDER and guard against path traversal."""
    base = os.path.basename(file_name)
    full_path = os.path.realpath(os.path.join(config.MUSIC_FOLDER, base))
    root = os.path.realpath(config.MUSIC_FOLDER)
    if not full_path.startswith(root + os.sep) and full_path != root:
        raise ValueError("Недопустимый путь к файлу")
    return full_path


async def build_source(item: dict, guild_id: int, seek_to: int = 0):
    """Build an AudioSource from a queue item that has source=None (lazy).

    If seek_to > 0, the FFmpeg process is started with -ss to skip ahead.
    """
    volume = await get_volume(guild_id) / 100.0
    item_type = item.get('type')

    def _seek_options(base: dict, seek_to: int) -> dict:
        if seek_to <= 0:
            return dict(base)
        opts = dict(base)
        before = opts.get('before_options', '')
        opts['before_options'] = f"-ss {seek_to} {before}".strip()
        return opts

    if item_type == 'YouTube':
        data = await YTDLSource.extract_info(item['url'], loop=asyncio.get_event_loop(), download=False)
        opts = _seek_options(config.FFMPEG_STREAM_OPTIONS, seek_to)
        source = discord.FFmpegPCMAudio(data['url'], **opts)
        wrapped = YTDLSource(source, data=data)
        wrapped.volume = volume
        item['source'] = wrapped
        if not item.get('thumbnail'):
            item['thumbnail'] = data.get('thumbnail')
        if not item.get('duration_sec'):
            item['duration_sec'] = int(data.get('duration') or 0)

    elif item_type == 'Radio':
        # Radio cannot be seeked (endless stream).
        source = discord.FFmpegPCMAudio(item['url'], **config.RADIO_FFMPEG_OPTIONS)
        item['source'] = discord.PCMVolumeTransformer(source, volume=volume)

    elif item_type == 'Local':
        file_name = item.get('file_name') or item['title']
        full_path = _safe_local_path(file_name)
        if not os.path.exists(full_path):
            raise FileNotFoundError(file_name)
        opts = _seek_options(config.FFMPEG_LOCAL_OPTIONS, seek_to)
        source = discord.FFmpegPCMAudio(full_path, **opts)
        item['source'] = discord.PCMVolumeTransformer(source, volume=volume)

    return item['source']


async def skip_tracks(bot, guild, count: int) -> int:
    """Skip `count` tracks from the queue (including the current one).

    Returns the number of tracks actually skipped.
    """
    guild_id = guild.id
    if count <= 0:
        return 0

    queue = get_queue(bot, guild_id)
    skipped = 0

    vc = guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        # Current track counts as one skip.
        count -= 1
        skipped += 1
        if radio_pause_states.get(guild_id):
            radio_pause_states[guild_id] = False
            if queue:
                queue.pop(0)
                skipped += 1

    # Remove the next (count-1) queued items.
    to_remove = min(count, len(queue))
    if to_remove > 0:
        del queue[:to_remove]
        skipped += to_remove

    # Stop what's playing (after-callback will call play_next).
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    else:
        await play_next(bot, guild)

    return skipped


async def seek_playback(bot, guild, seek_to: int) -> bool:
    """Seek the currently playing track to `seek_to` seconds.

    Works by stopping the current source and re-playing it from the offset.
    Returns False if the item cannot be seeked (radio, no source).
    """
    guild_id = guild.id
    item = None
    stack = last_played_items.get(guild_id, [])
    if stack:
        item = stack[-1]

    if item is None:
        return False
    if item.get('type') == 'Radio':
        return False

    duration = int(item.get('duration_sec') or 0)
    if duration and seek_to >= duration:
        seek_to = max(0, duration - 1)

    vc = guild.voice_client
    if not vc:
        return False

    # Build a fresh source from the offset and replay it.
    fresh_item = dict(item)
    fresh_item.pop('source', None)
    try:
        await build_source(fresh_item, guild_id, seek_to=seek_to)
    except Exception:
        return False

    playback_timers[guild_id] = seek_to
    vc.stop()

    def _after(_exc):
        asyncio.run_coroutine_threadsafe(play_next(bot, guild), bot.loop)

    vc.play(fresh_item['source'], after=_after)

    # Keep the stack entry in sync so later skips refer to the fresh item.
    if stack:
        stack[-1] = fresh_item
    return True


# --------------------------------------------------------------------------- #
# Chain-play (autoplay)
# --------------------------------------------------------------------------- #

_chain_play_cache = {}


def is_chain_play_enabled(guild_id: int) -> bool:
    """Return the in-memory chain-play flag (loaded on demand from SQLite)."""
    return _chain_play_cache.get(guild_id, False)


async def load_chain_play_state(guild_id: int) -> None:
    """Load persisted chain-play flag into the in-memory mirror."""
    _chain_play_cache[guild_id] = bool(await get_setting(guild_id, 'chain_play', 0))


def set_chain_play(guild_id: int, enabled: bool) -> None:
    """Update the in-memory chain-play flag and persist it."""
    _chain_play_cache[guild_id] = bool(enabled)
    # Persisted asynchronously via cogs/autoplay.py — keep this sync helper stateless.


async def get_autoplay_track(bot, guild_id: int, last_item: dict) -> dict | None:
    """Find a related YouTube track for chain-play.

    Only triggers for YouTube items. Returns a queue item dict with source=None
    (built lazily), or None when nothing can be found.
    """
    if last_item.get('type') != 'YouTube':
        return None

    last_title = last_item.get('title')
    if not last_title:
        return None

    history = autoplay_history.setdefault(guild_id, set())
    last_url = last_item.get('url')

    # Try several query strategies to find genuinely different tracks.
    queries = [f"{last_title} mix", last_title]
    tracks: list[dict] = []
    for query in queries:
        try:
            tracks = await YTDLSource.search(query, loop=bot.loop)
        except Exception:
            tracks = []
        if tracks:
            break

    if not tracks:
        return None

    # Candidate pool: different URL, not autoplayed before.
    candidates = []
    for entry in tracks:
        entry_url = entry.get('webpage_url')
        if not entry_url:
            continue
        if last_url and entry_url == last_url:
            continue
        if entry_url in history:
            continue
        candidates.append(entry)

    # If everything was already played, relax: allow any track (memory
    # will only hold the last 15 anyway).
    if not candidates:
        candidates = tracks

    # Pick a random one of the top candidates so the chain does not
    # deterministically loop over the same playlist order.
    pool = [c for c in candidates if c.get('webpage_url')]
    if not pool:
        return None

    selected = random.choice(pool[:5])

    selected_url = selected.get('webpage_url')
    if selected_url:
        history.add(selected_url)
        # Keep history bounded
        if len(history) > 30:
            autoplay_history[guild_id] = set(list(history)[-15:])

    return {
        'source': None,
        'title': selected.get('title') or 'Неизвестный трек',
        'url': selected_url,
        'thumbnail': selected.get('thumbnail'),
        'duration_sec': int(selected.get('duration') or 0),
        'user_mention': '🤖 Авто-DJ',
        'type': 'YouTube',
        'channel': None,
    }


# --------------------------------------------------------------------------- #
# Player embed
# --------------------------------------------------------------------------- #

def get_universal_embed(item, guild, current_time: int = 0):
    lang = get_lang(guild.id)
    title = (item.get('title') or 'Неизвестно')[:100]
    duration = int(item.get('duration_sec') or 0)
    user = item.get('user_mention') or 'Система'
    item_type = item.get('type') or 'YouTube'

    type_meta = {
        'YouTube': ('📺 YouTube', discord.Color.blurple()),
        'Radio': ('📻 Радио', discord.Color.red()),
        'Local': ('📁 Локальный файл', discord.Color.green()),
    }
    type_label, color = type_meta.get(item_type, ('📺 YouTube', discord.Color.blurple()))

    vc = guild.voice_client
    is_paused = (vc and vc.is_paused()) or radio_pause_states.get(guild.id, False)
    status = t(lang, 'paused') if is_paused else t(lang, 'playing')

    embed = discord.Embed(
        title=t(lang, 'now_playing'),
        description=f"**{title}**",
        color=color,
    )
    if item.get('thumbnail'):
        embed.set_thumbnail(url=item['thumbnail'])

    queue_len = len(get_queue(None, guild.id))

    if duration > 0:
        percent = min(current_time / duration, 1.0)
        bar_length = 15
        filled = int(bar_length * percent)
        bar = "▬" * filled + "🔘" + "▬" * max(0, (bar_length - filled - 1))
        cur_str = str(datetime.timedelta(seconds=int(current_time)))
        tot_str = str(datetime.timedelta(seconds=duration))
        embed.add_field(
            name=t(lang, 'progress'),
            value=f"[`{bar}`]\n`{cur_str} / {tot_str}`",
            inline=False,
        )
    elif item_type == 'Radio':
        embed.add_field(name=t(lang, 'progress'), value=t(lang, 'live'), inline=False)
    else:
        embed.add_field(name=t(lang, 'progress'), value=t(lang, 'local_file'), inline=False)

    repeat_mode = repeat_states.get(guild.id, 'off')
    repeat_label = {
        'off': t(lang, 'repeat_off'),
        'one': t(lang, 'repeat_one'),
        'all': t(lang, 'repeat_all'),
    }.get(repeat_mode, repeat_mode)
    chain_label = t(lang, 'on') if is_chain_play_enabled(guild.id) else t(lang, 'off')
    volume = volume_states.get(guild.id, 100)

    embed.add_field(name=t(lang, 'source'), value=type_label, inline=True)
    embed.add_field(name=t(lang, 'requested_by'), value=user, inline=True)
    embed.add_field(name=t(lang, 'queue_short', count=queue_len), value=f"{queue_len}", inline=True)
    embed.add_field(
        name=t(lang, 'status'),
        value=f"{status} | 🔁 {repeat_label} | 🔗 {chain_label} | 🔊 {volume}%",
        inline=False,
    )
    embed.set_footer(text=f"{guild.name}")
    return embed


# --------------------------------------------------------------------------- #
# Progress timer
# --------------------------------------------------------------------------- #

async def update_player_status(message, item, guild):
    """Periodically update the player embed.

    Only meaningful for finite tracks (duration > 0). Uses a 15s interval
    (≈4 requests/min) and skips edits when the visual progress bar has not
    moved, which keeps Discord rate limits comfortable.
    """
    duration = int(item.get('duration_sec') or 0)
    guild_id = guild.id
    playback_timers[guild_id] = 0

    # Radio / Local files have no finite duration — embed is static
    # (LIVE / LOCAL indicator). No periodic edits are needed at all.
    if duration <= 0:
        return

    step = 15
    bar_length = 15
    last_filled = -1

    while guild.voice_client and (
        guild.voice_client.is_playing()
        or guild.voice_client.is_paused()
        or radio_pause_states.get(guild_id)
    ):
        if guild.voice_client.is_playing():
            playback_timers[guild_id] += step

        elapsed = playback_timers[guild_id]

        if elapsed >= duration:
            break

        # Skip the edit when the progress bar has not visibly changed
        # (e.g. while paused, or between bar segments).
        filled = int(bar_length * min(elapsed / duration, 1.0))
        if filled == last_filled:
            await asyncio.sleep(step)
            continue
        last_filled = filled

        try:
            await message.edit(embed=get_universal_embed(item, guild, elapsed))
        except Exception:
            break

        await asyncio.sleep(step)


# --------------------------------------------------------------------------- #
# Next-track orchestration
# --------------------------------------------------------------------------- #

async def play_next(bot, guild):
    guild_id = guild.id

    # Lazily load persisted settings (chain_play / volume / repeat_mode)
    # on first use so autoplay works right after bot startup.
    if guild_id not in _chain_play_cache:
        try:
            await load_guild_state(guild_id)
        except Exception:
            pass

    # While a radio stream is paused, do not advance.
    if radio_pause_states.get(guild_id):
        return

    # Clean up the previous player message and its ephemeral tracking.
    if guild_id in last_player_messages:
        try:
            await last_player_messages[guild_id].delete()
        except Exception:
            pass
        del last_player_messages[guild_id]

    queue = get_queue(bot, guild_id)

    # --- Chain-play: fill the queue when empty ---------------------------- #
    if not queue and is_chain_play_enabled(guild_id):
        last_stack = last_played_items.get(guild_id)
        if last_stack:
            last_item = last_stack[-1]
            autoplay_item = await get_autoplay_track(bot, guild_id, last_item)
            if autoplay_item:
                autoplay_item['channel'] = item_channel_for(guild_id)
                queue.append(autoplay_item)
            else:
                playback_timers[guild_id] = 0
                return

    if not queue:
        playback_timers[guild_id] = 0
        # Idle panel: when the queue ends (something actually played),
        # show a small control menu so users can keep controlling the bot.
        if last_played_items.get(guild_id):
            channel = item_channel_for(guild_id)
            if channel and not last_player_messages.get(guild_id):
                try:
                    embed = discord.Embed(
                        title="🎵 Очередь закончилась",
                        description="Используйте кнопки, чтобы продолжить:",
                        color=discord.Color.darker_gray(),
                    )
                    view = IdlePlayerView(bot, guild_id)
                    msg = await channel.send(embed=embed, view=view)
                    last_player_messages[guild_id] = msg
                except Exception:
                    pass
        return

    item = queue.pop(0)
    playback_timers[guild_id] = 0

    # Track the last played item (stack for the Previous button).
    last_played_items.setdefault(guild_id, []).append(item)
    if len(last_played_items[guild_id]) > LAST_PLAYED_STACK_MAX:
        last_played_items[guild_id].pop(0)
    last_played_titles[guild_id] = item['title']

    voice_client = guild.voice_client
    if not voice_client:
        return

    # Apply repeat after popping (so the popped item is re-enqueued while playing).
    # The source of a finished item is exhausted — reset it so it is rebuilt lazily.
    repeat_mode = repeat_states.get(guild_id, 'off')
    if item.get('type') != 'Radio':
        if repeat_mode == 'one':
            item.pop('source', None)
            queue.insert(0, item)
        elif repeat_mode == 'all':
            item.pop('source', None)
            queue.append(item)

    # --- Lazy source build ------------------------------------------------ #
    if item.get('source') is None:
        try:
            await build_source(item, guild_id)
        except Exception:
            # Skip broken item and continue with the next one.
            await play_next(bot, guild)
            return

    source = item['source']
    if source is None:
        await play_next(bot, guild)
        return

    def _after(_exc):
        asyncio.run_coroutine_threadsafe(play_next(bot, guild), bot.loop)

    voice_client.play(source, after=_after)

    channel = item.get('channel')
    if channel:
        try:
            embed = get_universal_embed(item, guild, 0)
            view = UniversalPlayerView(bot, guild_id, item)
            msg = await channel.send(embed=embed, view=view)
            last_player_messages[guild_id] = msg
            bot.loop.create_task(update_player_status(msg, item, guild))
        except Exception:
            pass


def item_channel_for(guild_id: int):
    """Return the channel to use for autoplay items (last known channel)."""
    prev = last_played_items.get(guild_id)
    if prev:
        return prev[-1].get('channel')
    return None


# --------------------------------------------------------------------------- #
# Player view
# --------------------------------------------------------------------------- #

class QueuePaginationView(discord.ui.View):
    """Paginated queue display (15 tracks per page, prev/next buttons)."""

    PAGE_SIZE = 15

    def __init__(self, bot, guild_id: int, items: list):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.items = items
        self.page = 0
        self._update_buttons()

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.items) // self.PAGE_SIZE))

    def _update_buttons(self):
        # Buttons are rebuilt only on first construction; callbacks adjust page.
        self.page_prev.disabled = self.page <= 0
        self.page_next.disabled = self.page >= self.pages - 1

    def build_embed(self) -> discord.Embed:
        lang = get_lang(self.guild_id)
        start = self.page * self.PAGE_SIZE
        chunk = self.items[start:start + self.PAGE_SIZE]

        embed = discord.Embed(
            title="📜 Текущая очередь",
            description="\n".join(
                f"**{start + i + 1}.** {(item.get('title') or 'Неизвестный трек')[:80]}"
                f" — {item.get('user_mention', 'Система')}"
                for i, item in enumerate(chunk)
            ) or "—",
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Страница {self.page + 1} / {self.pages} • {len(self.items)} треков")
        return embed

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def page_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def page_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.pages - 1:
            self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class SeekModal(discord.ui.Modal, title="⏩ Перемотка"):
    seconds = discord.ui.TextInput(
        label="Секунды",
        placeholder="Например: 90",
        max_length=6,
        required=True,
    )

    def __init__(self, bot, guild_id: int, item: dict):
        lang = get_lang(guild_id)
        self.seconds.label = t(lang, 'modal_seconds')
        self.seconds.placeholder = t(lang, 'modal_seconds_ph')
        super().__init__(title=t(lang, 'modal_seek_title'))
        self.bot = bot
        self.guild_id = guild_id
        self.item = item

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = int(self.seconds.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Введите число секунд.", ephemeral=True
            )
        if seconds < 0:
            return await interaction.response.send_message(
                "❌ Секунды не могут быть отрицательными.", ephemeral=True
            )

        ok = await seek_playback(self.bot, interaction.guild, seconds)
        if not ok:
            return await interaction.response.send_message(
                "❌ Не удалось перемотать (радио нельзя).", ephemeral=True
            )

        pos = str(datetime.timedelta(seconds=seconds))
        await interaction.response.send_message(f"⏩ Перемотано на **{pos}**.", ephemeral=True)


class SkipNModal(discord.ui.Modal, title="⏭ Пропустить несколько"):
    count = discord.ui.TextInput(
        label="Сколько треков пропустить",
        placeholder="Например: 3",
        max_length=4,
        required=True,
    )

    def __init__(self, bot, guild_id: int):
        lang = get_lang(guild_id)
        self.count.label = t(lang, 'modal_skipn_label')
        self.count.placeholder = t(lang, 'modal_skipn_ph')
        super().__init__(title=t(lang, 'modal_skipn_title'))
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = int(self.count.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Введите число.", ephemeral=True
            )
        if n < 1:
            return await interaction.response.send_message(
                "❌ Число должно быть >= 1.", ephemeral=True
            )

        skipped = await skip_tracks(self.bot, interaction.guild, n)
        await interaction.response.send_message(
            f"⏭ Пропущено: **{skipped}**", ephemeral=True
        )


class UniversalPlayerView(discord.ui.View):
    def __init__(self, bot, guild_id: int, item: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.item = item
        self._localize_labels()

    def _localize_labels(self):
        """Translate button labels on the fly using the guild language."""
        lang = get_lang(self.guild_id)
        label_map = {
            'Очередь': t(lang, 'btn_queue'),
            'Плейлисты': t(lang, 'btn_playlists'),
            'Перемотка': t(lang, 'btn_seek'),
            'Skip N': t(lang, 'btn_skipn'),
            'Громкость': t(lang, 'btn_volume'),
            'Язык': t(lang, 'btn_language'),
        }
        for child in self.children:
            if getattr(child, 'label', None) in label_map:
                child.label = label_map[child.label]

    # -- helpers ----------------------------------------------------------- #

    async def _update_embed(self, interaction: discord.Interaction, item: dict):
        """Refreshes the player embed (does NOT shadow View._refresh from discord.py)."""
        current_time = playback_timers.get(self.guild_id, 0)
        try:
            await interaction.edit_original_response(
                embed=get_universal_embed(item, interaction.guild, current_time)
            )
        except discord.NotFound:
            pass
        except Exception:
            pass

    @staticmethod
    def _is_radio(item: dict) -> bool:
        return item.get('type') == 'Radio'

    # -- Row 1: transport -------------------------------------------------- #

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if not vc:
            return

        stack = last_played_items.get(self.guild_id, [])
        if len(stack) < 2:
            return await interaction.followup.send("⏮️ Нет предыдущего трека.", ephemeral=True)

        # Replay the second-to-last item. Do NOT pop the stack head — the
        # currently playing track stays in the history; play_next() will add
        # the replayed item on top when it starts.
        prev_item = stack[-2]

        # The previously played item's source is exhausted — rebuild lazily.
        prev_item = dict(prev_item)
        prev_item.pop('source', None)

        queue = get_queue(self.bot, self.guild_id)
        queue.insert(0, prev_item)

        if radio_pause_states.get(self.guild_id):
            radio_pause_states[self.guild_id] = False

        if vc.is_playing() or vc.is_paused():
            vc.stop()
        else:
            await play_next(self.bot, interaction.guild)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary, row=0)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if not vc:
            return

        is_radio = self._is_radio(self.item)
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

        await self._update_embed(interaction, self.item)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
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

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        queue = get_queue(self.bot, self.guild_id)
        if len(queue) <= 1:
            return await interaction.followup.send("🔀 Слишком мало треков для перемешивания.", ephemeral=True)

        random.shuffle(queue)
        queue_len = len(queue)
        await interaction.followup.send(
            f"🔀 Очередь перемешана ({queue_len} треков).", ephemeral=True
        )

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, row=0)
    async def repeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        order = ('off', 'one', 'all')
        current = repeat_states.get(self.guild_id, 'off')
        next_mode = order[(order.index(current) + 1) % len(order)]
        repeat_states[self.guild_id] = next_mode
        await set_setting(self.guild_id, 'repeat_mode', next_mode)

        labels = {'off': 'Выкл', 'one': '🔂 Один', 'all': '🔁 Все'}
        await interaction.followup.send(f"🔁 Повтор: {labels[next_mode]}", ephemeral=True)
        await self._update_embed(interaction, self.item)

    @discord.ui.button(emoji="🔗", style=discord.ButtonStyle.secondary, row=1)
    async def chain_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle chain-play right from the player panel."""
        if not interaction.response.is_done():
            await interaction.response.defer()

        guild_id = self.guild_id
        current = is_chain_play_enabled(guild_id)
        new_state = not current

        await set_setting(guild_id, 'chain_play', new_state)
        set_chain_play(guild_id, new_state)

        status = "✅ **включён**" if new_state else "⏹ **выключен**"
        await interaction.followup.send(f"🔗 Режим «По цепочке» {status}.", ephemeral=True)
        # Обновить embed (статус-строка показывает состояние цепочки).
        player_msg = last_player_messages.get(guild_id)
        if player_msg is not None:
            try:
                await player_msg.edit(
                    embed=get_universal_embed(
                        self.item, interaction.guild, playback_timers.get(guild_id, 0)
                    )
                )
            except Exception:
                pass

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary, label="Перемотка", row=2)
    async def seek_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a modal to seek the current track."""
        modal = SeekModal(self.bot, self.guild_id, self.item)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.secondary, label="Skip N", row=2)
    async def skip_n_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a modal to skip several tracks."""
        modal = SkipNModal(self.bot, self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.primary, label="Очередь", row=1)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.bot, self.guild_id)
        if not queue:
            return await interaction.response.send_message(
                t(get_lang(self.guild_id), 'queue_empty_menu'), ephemeral=True
            )

        # Send a paginated queue view (ephemeral, deletable).
        view = QueuePaginationView(self.bot, self.guild_id, queue[:50])
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.primary, label="Плейлисты", row=1)
    async def show_playlists(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.playlists import PlaylistSelectView

        try:
            playlists = await list_guild_playlists(self.guild_id)
        except Exception:
            return await interaction.response.send_message(
                "❌ Не удалось загрузить плейлисты.", ephemeral=True
            )

        if not playlists:
            return await interaction.response.send_message(
                "📭 У сервера ещё нет плейлистов. Создайте через `/playlist create`.",
                ephemeral=True,
            )

        view = PlaylistSelectView(playlists, interaction.user)
        if not interaction.response.is_done():
            await interaction.response.defer()
        msg = await interaction.followup.send(
            "📋 Выберите плейлист:", view=view, ephemeral=True
        )
        await view.wait()

        if view.selected_name is None:
            try:
                await msg.edit(content="⏰ Время выбора истекло.", view=None)
            except Exception:
                pass
            return

        try:
            tracks = await get_playlist_tracks_for(self.guild_id, view.selected_name)
        except Exception:
            return

        if not tracks:
            return await msg.edit(
                content=f"📭 Плейлист `{view.selected_name}` пуст.",
                view=None,
            )

        queue = get_queue(self.bot, self.guild_id)
        for track in tracks:
            queue.append({
                'source': None,
                'title': track['title'],
                'url': (track['url'] or None)
                       if track['source_type'] in ('YouTube', 'Radio') else None,
                'file_name': track['file_name'] if track['source_type'] == 'Local' else None,
                'thumbnail': None,
                'duration_sec': int(track['duration_sec'] or 0),
                'user_mention': interaction.user.mention,
                'type': track['source_type'],
                'channel': interaction.channel,
            })

        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            await msg.edit(
                content=f"📋 Плейлист **{view.selected_name}** добавлен в очередь ({len(tracks)} треков).",
                view=None,
            )
        else:
            if vc is None:
                # Не в голосовом канале — только заполняем очередь.
                await msg.edit(
                    content=f"📋 Плейлист **{view.selected_name}** поставлен в очередь ({len(tracks)} треков), но бот не в канале.",
                    view=None,
                )
                return
            await msg.edit(
                content=f"📋 Играет плейлист **{view.selected_name}** ({len(tracks)} треков).",
                view=None,
            )
            await play_next(self.bot, interaction.guild)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, label="Громкость", row=2)
    async def volume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        levels = [0, 25, 50, 75, 100, 125, 150, 200]
        options = [
            discord.SelectOption(
                label=str(level),
                value=str(level),
                default=(level == volume_states.get(self.guild_id, 100)),
            )
            for level in levels
        ]
        select = discord.ui.Select(placeholder="Выберите уровень громкости", options=options)

        async def _volume_callback(sel_interaction: discord.Interaction):
            if sel_interaction.user != interaction.user:
                return await sel_interaction.response.send_message(
                    "❌ Это не ваша панель громкости!", ephemeral=True
                )
            level = int(sel_interaction.data["values"][0])
            await set_volume(self.guild_id, level)

            vc = sel_interaction.guild.voice_client
            if vc and vc.source:
                source = vc.source
                if isinstance(source, discord.PCMVolumeTransformer):
                    source.volume = level / 100.0

            await sel_interaction.response.edit_message(
                content=f"🔊 Громкость установлена: **{level}%**", view=None
            )
            # Обновить embed плеера (громкость в статус-строке).
            player_msg = last_player_messages.get(self.guild_id)
            if player_msg is not None:
                try:
                    await player_msg.edit(
                        embed=get_universal_embed(
                            self.item, sel_interaction.guild, playback_timers.get(self.guild_id, 0)
                        )
                    )
                except Exception:
                    pass

        select.callback = _volume_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        # Панель громкости — отдельное ephemeral сообщение, не трогаем плеер.
        await interaction.followup.send(content="🔊 Уровень громкости:", view=view, ephemeral=True)

    @discord.ui.button(emoji="🌐", style=discord.ButtonStyle.secondary, label="Язык", row=2)
    async def language(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Choose the bot language from the player panel."""
        from cogs.help_menu import LanguageSelectView
        view = LanguageSelectView(interaction.user, bot=self.bot)
        await interaction.response.send_message(
            "🌍 Выберите язык / Choose a language:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=2)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc:
            get_queue(self.bot, self.guild_id).clear()
            playback_timers[self.guild_id] = 0
            radio_pause_states[self.guild_id] = False
            repeat_states[self.guild_id] = 'off'
            last_played_items.pop(self.guild_id, None)
            vc.stop()
            try:
                await vc.disconnect()
            except Exception:
                pass

            if self.guild_id in last_player_messages:
                del last_player_messages[self.guild_id]

            try:
                await interaction.edit_original_response(content="🛑 **Плеер остановлен**", embed=None, view=None)
            except discord.NotFound:
                await interaction.followup.send("🛑 Плеер остановлен", ephemeral=True)


# --------------------------------------------------------------------------- #
# Idle panel: shown when the queue ends so users can keep controlling the bot
# --------------------------------------------------------------------------- #

class IdlePlayerView(discord.ui.View):
    """Small control panel displayed after the queue ends."""

    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(emoji="🔗", style=discord.ButtonStyle.secondary, label="Цепочка")
    async def idle_chain(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle chain-play from the idle panel."""
        if not interaction.response.is_done():
            await interaction.response.defer()

        guild_id = self.guild_id
        last_stack = last_played_items.get(guild_id, [])
        last_item = last_stack[-1] if last_stack else None

        current = is_chain_play_enabled(guild_id)
        new_state = not current
        await set_setting(guild_id, 'chain_play', new_state)
        set_chain_play(guild_id, new_state)

        status = "✅ **включён**" if new_state else "⏹ **выключен**"
        msg_text = f"🔗 Режим «По цепочке» {status}."

        if new_state and last_item and last_item.get('type') == 'YouTube':
            autoplay_item = await get_autoplay_track(self.bot, guild_id, last_item)
            if autoplay_item:
                queue = get_queue(self.bot, guild_id)
                autoplay_item['channel'] = item_channel_for(guild_id)
                queue.append(autoplay_item)
                await play_next(self.bot, interaction.guild)
                msg_text += " 🎶 Подобрал похожий трек!"

        await interaction.followup.send(msg_text, ephemeral=True)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, label="Повторить последний")
    async def idle_replay(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Replay the last played track."""
        if not interaction.response.is_done():
            await interaction.response.defer()

        last_stack = last_played_items.get(self.guild_id, [])
        if not last_stack:
            return await interaction.followup.send("❌ Нет последнего трека.", ephemeral=True)

        last_item = dict(last_stack[-1])
        last_item.pop('source', None)
        queue = get_queue(self.bot, self.guild_id)
        queue.append(last_item)

        vc = interaction.guild.voice_client
        if vc:
            await play_next(self.bot, interaction.guild)
            await interaction.followup.send("▶️ Повторяю последний трек.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Бот не в голосовом канале.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, label="Стоп")
    async def idle_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Disconnect and clean everything."""
        if not interaction.response.is_done():
            await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc:
            get_queue(self.bot, self.guild_id).clear()
            playback_timers[self.guild_id] = 0
            radio_pause_states[self.guild_id] = False
            repeat_states[self.guild_id] = 'off'
            last_played_items.pop(self.guild_id, None)
            vc.stop()
            try:
                await vc.disconnect()
            except Exception:
                pass

        if self.guild_id in last_player_messages:
            del last_player_messages[self.guild_id]

        try:
            await interaction.edit_original_response(content="🛑 **Плеер остановлен**", embed=None, view=None)
        except discord.NotFound:
            await interaction.followup.send("🛑 Плеер остановлен", ephemeral=True)


# --------------------------------------------------------------------------- #
# Helper: guild playlists (avoid circular import with cogs.playlists)
# --------------------------------------------------------------------------- #

async def list_guild_playlists(guild_id: int):
    from utils.db import list_playlists
    return await list_playlists(guild_id)


async def get_playlist_tracks_for(guild_id: int, name: str):
    from utils.db import get_playlist_tracks
    return await get_playlist_tracks(guild_id, name)


async def load_guild_state(guild_id: int) -> None:
    """Load persisted settings into memory when a guild is first used."""
    await load_chain_play_state(guild_id)
    if guild_id not in volume_states:
        volume_states[guild_id] = await get_setting(guild_id, 'volume', 100) or 100
    repeat_states.setdefault(guild_id, await get_setting(guild_id, 'repeat_mode', 'off') or 'off')

    # Language
    lang = await get_setting(guild_id, 'language', 'ru') or 'ru'
    set_lang(guild_id, lang)


async def show_menu(interaction: discord.Interaction, bot) -> None:
    """Show the player control panel (used by /menu)."""
    guild_id = interaction.guild.id
    lang = get_lang(guild_id)

    try:
        await load_guild_state(guild_id)
    except Exception:
        pass

    vc = interaction.guild.voice_client
    if vc is None:
        return await interaction.response.send_message(
            t(lang, 'menu_no_vc'), ephemeral=True
        )

    # Reuse the current item (or a placehold embed) and the player view.
    last_stack = last_played_items.get(guild_id, [])
    current_item = last_stack[-1] if last_stack else None
    if current_item is None:
        queue = get_queue(None, guild_id)
        if queue:
            current_item = dict(queue[0])
            current_item.pop('source', None)

    if current_item is None:
        # Nothing played yet, but bot is in voice: show the idle panel.
        await interaction.response.defer()
        idle_view = IdlePlayerView(bot, guild_id)
        msg = await interaction.followup.send(
            t(lang, 'menu_nothing'),
            view=idle_view,
        )
        last_player_messages[guild_id] = msg
        return

    await interaction.response.defer()  # NOT ephemeral → followup can be public

    # Reuse the existing panel message if present (edit instead of duplicate).
    existing = last_player_messages.get(guild_id)
    if existing is not None:
        try:
            await existing.edit(
                content=t(lang, 'menu_shown'),
                embed=get_universal_embed(
                    current_item, interaction.guild, playback_timers.get(guild_id, 0)
                ),
                view=UniversalPlayerView(bot, guild_id, current_item),
            )
            return
        except Exception:
            # fall through to creating a fresh panel
            del last_player_messages[guild_id]

    embed = get_universal_embed(current_item, interaction.guild, playback_timers.get(guild_id, 0))
    view = UniversalPlayerView(bot, guild_id, current_item)

    msg = await interaction.followup.send(
        t(lang, 'menu_shown'), embed=embed, view=view
    )
    last_player_messages[guild_id] = msg