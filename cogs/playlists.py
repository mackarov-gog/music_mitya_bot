import discord
from discord.ext import commands
from discord import app_commands
import datetime
from utils import db
from utils.i18n import desc_localizations
from utils.ytdl_source import YTDLSource
from utils.music_player import get_queue, play_next

# --------------------------------------------------------------------------- #
# Modals
# --------------------------------------------------------------------------- #

class CreatePlaylistModal(discord.ui.Modal, title="➕ Новый плейлист"):
    name = discord.ui.TextInput(
        label="Имя плейлиста",
        placeholder="Например: Chill",
        max_length=80,
        required=True,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name.value.strip()[:80]
        if not name:
            return await interaction.response.send_message(
                "❌ Имя не может быть пустым.", ephemeral=True
            )
        ok = await db.create_playlist(interaction.guild.id, name, interaction.user.mention)
        if ok:
            await interaction.response.send_message(f"✅ Плейлист **{name}** создан.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Плейлист **{name}** уже существует.", ephemeral=True
            )


class AddTrackModal(discord.ui.Modal, title="🍕 Добавить трек в плейлист"):
    playlist_name = discord.ui.TextInput(
        label="Имя плейлиста",
        placeholder="Например: Chill",
        max_length=80,
        required=True,
    )
    query = discord.ui.TextInput(
        label="Название / ссылка YouTube",
        placeholder="Например: Daft Punk — One More Time",
        max_length=200,
        required=True,
    )

    def __init__(self, cog, default_playlist: str = ""):
        super().__init__()
        self.cog = cog
        if default_playlist:
            self.playlist_name.default = default_playlist
            self.playlist_name.value = default_playlist

    async def on_submit(self, interaction: discord.Interaction):
        name = self.playlist_name.value.strip()[:80]
        query = self.query.value.strip()

        await interaction.response.defer(ephemeral=True)

        playlist = await db.get_playlist(interaction.guild.id, name)
        if not playlist:
            return await interaction.followup.send(
                f"❌ Плейлист **{name}** не найден. Сначала создайте его.", ephemeral=True
            )

        if query.startswith("http"):
            info = await YTDLSource.extract_info(query, loop=self.cog.bot.loop, download=False)
            if info is None:
                return await interaction.followup.send(
                    "❌ Не удалось получить информацию по ссылке.", ephemeral=True
                )
            await self._store_track(interaction, name, info, query)
            return

        # Search flow
        tracks = await YTDLSource.search(query, loop=self.cog.bot.loop)
        if not tracks:
            return await interaction.followup.send(
                "❌ Ничего не найдено по запросу.", ephemeral=True
            )

        from cogs.youtube import TrackSelectView
        view = TrackSelectView(tracks, interaction.user)
        msg = await interaction.followup.send("🔎 **Выберите трек:**", view=view, ephemeral=True)
        await view.wait()

        if view.index is None:
            try:
                await msg.edit(content="⏰ Время выбора истекло.", view=None)
            except Exception:
                pass
            return

        entry = tracks[view.index]
        await self._store_track(interaction, name, entry, entry.get('webpage_url'))

    async def _store_track(self, interaction, name, info, url):
        ok = await db.add_track(
            interaction.guild.id,
            name,
            title=(info.get('title') or 'Неизвестный трек')[:100],
            url=url,
            source_type='YouTube',
            duration_sec=int(info.get('duration') or 0),
            added_by=interaction.user.mention,
        )
        if ok:
            await interaction.followup.send(
                f"➕ В плейлист **{name}**: **{info.get('title')}**", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Плейлист **{name}** не найден.", ephemeral=True
            )


class RemoveTrackModal(discord.ui.Modal, title="🗑 Удалить трек"):
    position = discord.ui.TextInput(
        label="Номер трека в плейлисте",
        placeholder="Например: 3",
        max_length=5,
        required=True,
    )

    def __init__(self, cog, playlist_name: str):
        super().__init__()
        self.cog = cog
        self.playlist_name = playlist_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pos = int(self.position.value)
        except ValueError:
            return await interaction.response.send_message("❌ Введите число.", ephemeral=True)
        if pos < 1:
            return await interaction.response.send_message(
                "❌ Позиция должна быть >= 1.", ephemeral=True
            )

        ok = await db.remove_track(interaction.guild.id, self.playlist_name, pos)
        if ok:
            await interaction.response.send_message(
                f"🗑 Трек #{pos} удалён из **{self.playlist_name}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Плейлист **{self.playlist_name}** или позиция #{pos} не найдены.",
                ephemeral=True,
            )


# --------------------------------------------------------------------------- #
# Picker: choose one of the guild playlists
# --------------------------------------------------------------------------- #

class PlaylistPickerView(discord.ui.View):
    """Select a playlist. action: 'play' | 'list' | 'delete'."""

    def __init__(self, cog, user, action: str, playlists: list[dict]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.action = action
        self.playlists = playlists

        options = [
            discord.SelectOption(label=pl['name'][:80], value=pl['name'][:80])
            for pl in playlists[:25]
        ]
        select = discord.ui.Select(
            placeholder="Выберите плейлист...",
            options=options,
            row=0,
        )
        select.callback = self.select_callback
        self.add_item(select)

        cancel = discord.ui.Button(emoji="🚪", label="Назад", style=discord.ButtonStyle.secondary, row=1)
        cancel.callback = self.back_callback
        self.add_item(cancel)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "❌ Это не ваш выбор!", ephemeral=True
            )
        name = interaction.data["values"][0]
        await self._route(interaction, name)

    async def back_callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "❌ Это не ваша панель!", ephemeral=True
            )
        menu = PlaylistMenuView(self.cog, self.user)
        await interaction.response.edit_message(
            content="📋 **Меню плейлистов**",
            embed=await PlaylistMenuView.build_menu_embed(self.cog.bot, interaction.guild.id),
            view=menu,
        )

    async def _route(self, interaction: discord.Interaction, name: str):
        if self.action == 'play':
            await interaction.response.defer(ephemeral=True)
            await self.cog._play_playlist_by_name(interaction, name)
        elif self.action == 'list':
            await self.cog._show_tracks(interaction, name)
        elif self.action == 'delete':
            confirm = ConfirmDeleteView(self.cog, self.user, name)
            await interaction.response.send_message(
                f"🗑 Точно удалить плейлист **{name}**?",
                view=confirm,
                ephemeral=True,
            )


class ConfirmDeleteView(discord.ui.View):
    """Yes/No confirmation for playlist deletion."""

    def __init__(self, cog, user, playlist_name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.playlist_name = playlist_name

    @discord.ui.button(emoji="✅", label="Да", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        ok = await db.delete_playlist(interaction.guild.id, self.playlist_name)
        if ok:
            await interaction.response.edit_message(
                content=f"🗑 Плейлист **{self.playlist_name}** удалён.", view=None
            )
        else:
            await interaction.response.edit_message(
                content=f"❌ Плейлист **{self.playlist_name}** не найден.", view=None
            )

    @discord.ui.button(emoji="❌", label="Нет", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        await interaction.response.edit_message(
            content="🚫 Удаление отменено.", view=None
        )


# --------------------------------------------------------------------------- #
# Track list with pagination and actions
# --------------------------------------------------------------------------- #

class TrackListPaginationView(discord.ui.View):
    """Shows tracks of a playlist with pagination and admin actions."""

    PAGE_SIZE = 10

    def __init__(self, cog, user, playlist_name: str, items: list[dict]):
        super().__init__(timeout=180)
        self.cog = cog
        self.user = user
        self.playlist_name = playlist_name
        self.items = items
        self.page = 0
        self._refresh_buttons()

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.items) // self.PAGE_SIZE))

    def _refresh_buttons(self):
        self.prev.disabled = self.page <= 0
        self.next.disabled = self.page >= self.pages - 1

    def build_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        chunk = self.items[start:start + self.PAGE_SIZE]
        lines = []
        for item in chunk:
            dur = str(datetime.timedelta(seconds=int(item.get('duration_sec') or 0)))
            lines.append(f"`{item.get('position', 0):>3}`. **{item['title'][:55]}** — {dur}")

        embed = discord.Embed(
            title=f"📋 Плейлист **{self.playlist_name}**",
            description="\n".join(lines) or "— пусто —",
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"Страница {self.page + 1} / {self.pages} • {len(self.items)} треков"
        )
        return embed

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        if self.page > 0:
            self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        if self.page < self.pages - 1:
            self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(emoji="🗑", label="Удалить №", style=discord.ButtonStyle.danger, row=1)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        modal = RemoveTrackModal(self.cog, self.playlist_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="🚪", label="Назад", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        menu = PlaylistMenuView(self.cog, self.user)
        await interaction.response.edit_message(
            content="📋 **Меню плейлистов**",
            embed=await PlaylistMenuView.build_menu_embed(self.cog.bot, interaction.guild.id),
            view=menu,
        )


# --------------------------------------------------------------------------- #
# Main interactive playlist menu
# --------------------------------------------------------------------------- #

class PlaylistMenuView(discord.ui.View):
    """The main interactive panel for managing server playlists."""

    def __init__(self, cog, user):
        super().__init__(timeout=180)
        self.cog = cog
        self.user = user

    @staticmethod
    async def build_menu_embed(bot, guild_id) -> discord.Embed:
        try:
            playlists = await db.list_playlists(guild_id)
        except Exception:
            playlists = []

        if not playlists:
            desc = "У сервера ещё нет плейлистов.\nНажмите **➕ Создать**, чтобы сделать первый."
        else:
            lines = []
            for pl in playlists[:10]:
                lines.append(f"• **{pl['name']}**")
            desc = "\n".join(lines)
            if len(playlists) > 10:
                desc += f"\n*...и ещё {len(playlists) - 10}*"

        embed = discord.Embed(
            title="📋 Меню плейлистов",
            description=desc,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Серверные плейлисты хранятся в SQLite и переживают перезапуск бота.")
        return embed

    # ---- Row 0 ---------------------------------------------------------- #

    @discord.ui.button(emoji="📋", label="Список", style=discord.ButtonStyle.primary, row=0)
    async def list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        playlists = await db.list_playlists(interaction.guild.id)
        if not playlists:
            return await interaction.response.send_message(
                "📭 Плейлистов нет. Создайте через ➕.", ephemeral=True
            )
        view = PlaylistPickerView(self.cog, self.user, 'list', playlists)
        await interaction.response.edit_message(
            content="📋 **Выберите плейлист для просмотра:**",
            embed=None,
            view=view,
        )

    @discord.ui.button(emoji="▶️", label="Играть", style=discord.ButtonStyle.success, row=0)
    async def play_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "❌ Вы не в голосовом канале!", ephemeral=True
            )
        playlists = await db.list_playlists(interaction.guild.id)
        if not playlists:
            return await interaction.response.send_message(
                "📭 Плейлистов нет. Создайте через ➕.", ephemeral=True
            )
        view = PlaylistPickerView(self.cog, self.user, 'play', playlists)
        await interaction.response.edit_message(
            content="▶️ **Выберите плейлист для воспроизведения:**",
            embed=None,
            view=view,
        )

    @discord.ui.button(emoji="➕", label="Создать", style=discord.ButtonStyle.success, row=0)
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        await interaction.response.send_modal(CreatePlaylistModal(self.cog))

    # ---- Row 1 ---------------------------------------------------------- #

    @discord.ui.button(emoji="🍕", label="Добавить трек", style=discord.ButtonStyle.primary, row=1)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        await interaction.response.send_modal(AddTrackModal(self.cog))

    @discord.ui.button(emoji="🗑", label="Удалить", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        playlists = await db.list_playlists(interaction.guild.id)
        if not playlists:
            return await interaction.response.send_message(
                "📭 Плейлистов нет. Нечего удалять.", ephemeral=True
            )
        view = PlaylistPickerView(self.cog, self.user, 'delete', playlists)
        await interaction.response.edit_message(
            content="🗑 **Выберите плейлист для удаления:**",
            embed=None,
            view=view,
        )

    @discord.ui.button(emoji="🚪", label="Закрыть", style=discord.ButtonStyle.secondary, row=1)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Не ваша панель!", ephemeral=True)
        await interaction.response.edit_message(content="🚪 Меню закрыто.", embed=None, view=None)


# --------------------------------------------------------------------------- #
# Cog
# --------------------------------------------------------------------------- #

class PlaylistCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _play_playlist_by_name(self, interaction: discord.Interaction, name: str):
        """Play a playlist (used by the interactive picker)."""
        await self._play_playlist(interaction, name, position=0, append=False)

    async def _show_tracks(self, interaction: discord.Interaction, name: str):
        """Show tracks of a playlist with pagination & actions."""
        tracks = await db.get_playlist_tracks(interaction.guild.id, name)
        if not tracks:
            return await interaction.response.edit_message(
                content=f"📭 Плейлист **{name}** пуст или не найден.", embed=None, view=None
            )
        view = TrackListPaginationView(self, interaction.user, name, tracks)
        await interaction.response.edit_message(
            content=f"📋 Плейлист **{name}**",
            embed=view.build_embed(),
            view=view,
        )

    async def _play_playlist(
        self,
        interaction: discord.Interaction,
        name: str,
        position: int,
        append: bool,
    ) -> None:
        if not interaction.user.voice:
            return await interaction.followup.send(
                "❌ Вы не в голосовом канале!", ephemeral=True
            )

        tracks = await db.get_playlist_tracks(interaction.guild.id, name)
        if not tracks:
            return await interaction.followup.send(
                f"📭 Плейлист `{name}` пуст или не найден.", ephemeral=True
            )

        if position > 0:
            position = min(position, len(tracks))
            tracks = tracks[position - 1:]
        else:
            pass  # play all

        # Voice connection
        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            import asyncio
            try:
                voice_client = await voice_channel.connect(timeout=20.0)
            except asyncio.TimeoutError:
                if interaction.guild.voice_client:
                    await interaction.guild.voice_client.disconnect(force=True)
                return await interaction.followup.send(
                    "❌ Discord не отвечает. Не удалось подключиться к голосовому каналу (Таймаут). Попробуй еще раз."
                )
            except Exception as e:
                return await interaction.followup.send(f"❌ Ошибка подключения: {e}")
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        queue = get_queue(self.bot, interaction.guild.id)

        items = []
        for track in tracks:
            items.append({
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

        if not append:
            queue.clear()
            queue.extend(items)

            was_playing = voice_client.is_playing() or voice_client.is_paused()
            if was_playing:
                voice_client.stop()
            else:
                await play_next(self.bot, interaction.guild)

            await interaction.followup.send(
                f"📋 Плейлист **{name}** поставлен в очередь "
                f"({len(items)} треков)."
            )
            return

        queue.extend(items)
        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(
                f"➕ Добавлено в очередь из плейлиста **{name}** ({len(items)} треков)."
            )
        else:
            await play_next(self.bot, interaction.guild)
            await interaction.followup.send(
                f"📋 Играет плейлист **{name}** ({len(items)} треков)."
            )

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @app_commands.command(name='playlist', description="Управление серверными плейлистами",
                          description_localizations=desc_localizations('playlist'))
    async def playlist(self, interaction: discord.Interaction):
        """Open the interactive playlist menu."""
        await load_guild_state_safe(interaction)
        view = PlaylistMenuView(self, interaction.user)
        embed = await PlaylistMenuView.build_menu_embed(self.bot, interaction.guild.id)
        await interaction.response.send_message(
            "📋 **Меню плейлистов**",
            embed=embed,
            view=view,
        )

    # -- Legacy slash commands (kept for power users / scripts) ---------- #

    @app_commands.command(name='playlist_create', description="Создать плейлист",
                          description_localizations=desc_localizations('playlist_create'))
    async def playlist_create(self, interaction: discord.Interaction, name: str):
        name = name.strip()[:80]
        if not name:
            return await interaction.response.send_message("❌ Укажите имя плейлиста.", ephemeral=True)

        ok = await db.create_playlist(interaction.guild.id, name, interaction.user.mention)
        if ok:
            await interaction.response.send_message(f"✅ Плейлист **{name}** создан.")
        else:
            await interaction.response.send_message(
                f"❌ Плейлист **{name}** уже существует.", ephemeral=True
            )

    @app_commands.command(name='playlist_add', description="Добавить трек по поиску YouTube в плейлист",
                          description_localizations=desc_localizations('playlist_add'))
    async def playlist_add(self, interaction: discord.Interaction, name: str, query: str):
        await interaction.response.defer()

        tracks = await YTDLSource.search(query, loop=self.bot.loop)
        if not tracks:
            return await interaction.followup.send("❌ Ничего не найдено по запросу.", ephemeral=True)

        from cogs.youtube import TrackSelectView
        view = TrackSelectView(tracks, interaction.user)
        msg = await interaction.followup.send("🔎 **Выберите трек:**", view=view)
        await view.wait()

        if view.index is None:
            return await msg.edit(content="⏰ Время выбора истекло.", view=None)

        entry = tracks[view.index]
        await msg.delete()

        ok = await db.add_track(
            interaction.guild.id,
            name,
            title=(entry.get('title') or 'Неизвестный трек')[:100],
            url=entry.get('webpage_url'),
            source_type='YouTube',
            duration_sec=int(entry.get('duration') or 0),
            added_by=interaction.user.mention,
        )
        if ok:
            await interaction.followup.send(
                f"➕ В плейлист **{name}**: **{entry.get('title')}**"
            )
        else:
            await interaction.followup.send(
                f"❌ Плейлист **{name}** не найден.", ephemeral=True
            )

    @app_commands.command(name='playlist_addurl', description="Добавить трек по ссылке в плейлист",
                          description_localizations=desc_localizations('playlist_addurl'))
    async def playlist_addurl(
        self,
        interaction: discord.Interaction,
        name: str,
        url: str,
        kind: str = "YouTube",
    ):
        await interaction.response.defer()

        if not url.startswith(("http://", "https://")):
            return await interaction.followup.send(
                "❌ Ссылка должна начинаться с http(s).", ephemeral=True
            )

        if kind.lower() not in ("youtube", "radio"):
            return await interaction.followup.send(
                "❌ kind должен быть `YouTube` или `Radio`.", ephemeral=True
            )

        if kind.lower() == "youtube":
            info = await YTDLSource.extract_info(url, loop=self.bot.loop, download=False)
            if info is None:
                return await interaction.followup.send(
                    "❌ Не удалось получить информацию по ссылке.", ephemeral=True
                )
            ok = await db.add_track(
                interaction.guild.id,
                name,
                title=(info.get('title') or 'Неизвестный трек')[:100],
                url=url,
                source_type='YouTube',
                duration_sec=int(info.get('duration') or 0),
                added_by=interaction.user.mention,
            )
        else:  # Radio
            ok = await db.add_track(
                interaction.guild.id,
                name,
                title='📻 Радиостанция',
                url=url,
                source_type='Radio',
                duration_sec=0,
                added_by=interaction.user.mention,
            )

        if ok:
            await interaction.followup.send(f"➕ Добавлено в плейлист **{name}**.")
        else:
            await interaction.followup.send(
                f"❌ Плейлист **{name}** не найден.", ephemeral=True
            )

    @app_commands.command(name='playlist_addlocal', description="Добавить локальный файл в плейлист",
                          description_localizations=desc_localizations('playlist_addlocal'))
    async def playlist_addlocal(self, interaction: discord.Interaction, name: str, filename: str):
        import os
        import config

        base = os.path.basename(filename)
        full_path = os.path.join(config.MUSIC_FOLDER, base)
        if not os.path.exists(full_path):
            return await interaction.response.send_message(
                f"❌ Файл `{filename}` не найден.", ephemeral=True
            )

        ok = await db.add_track(
            interaction.guild.id,
            name,
            title=base[:100],
            file_name=base,
            source_type='Local',
            duration_sec=0,
            added_by=interaction.user.mention,
        )
        if ok:
            await interaction.response.send_message(
                f"➕ В плейлист **{name}**: `{base}`"
            )
        else:
            await interaction.response.send_message(
                f"❌ Плейлист **{name}** не найден.", ephemeral=True
            )

    @app_commands.command(name='playlist_list', description="Список плейлистов сервера",
                          description_localizations=desc_localizations('playlist_list'))
    async def playlist_list(self, interaction: discord.Interaction):
        playlists = await db.list_playlists(interaction.guild.id)
        if not playlists:
            return await interaction.response.send_message(
                "📭 На сервере нет плейлистов.", ephemeral=True
            )

        lines = []
        for pl in playlists:
            tracks_count = len(await db.get_playlist_tracks(interaction.guild.id, pl['name']))
            lines.append(f"**{pl['name']}** — {tracks_count} треков")

        embed = discord.Embed(
            title="📋 Плейлисты сервера",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='playlist_show', description="Показать треки плейлиста",
                          description_localizations=desc_localizations('playlist_show'))
    async def playlist_show(self, interaction: discord.Interaction, name: str):
        tracks = await db.get_playlist_tracks(interaction.guild.id, name)
        if not tracks:
            return await interaction.response.send_message(
                f"📭 Плейлист **{name}** пуст или не найден.", ephemeral=True
            )

        lines = []
        for tr in tracks:
            dur = str(datetime.timedelta(seconds=int(tr['duration_sec'] or 0)))
            lines.append(f"`{tr['position']:>3}`. **{tr['title'][:60]}** — {dur}")

        chunks = ["\n".join(lines[i:i + 20]) for i in range(0, len(lines), 20)]
        embed = discord.Embed(
            title=f"📋 Плейлист **{name}**",
            description=chunks[0],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Всего треков: {len(tracks)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='playlist_play', description="Запустить плейлист в очередь",
                          description_localizations=desc_localizations('playlist_play'))
    async def playlist_play(
        self,
        interaction: discord.Interaction,
        name: str,
        position: int = 0,
        append: bool = False,
    ):
        await interaction.response.defer()
        await self._play_playlist(interaction, name, position, append)

    @app_commands.command(name='playlist_remove', description="Удалить трек из плейлиста",
                          description_localizations=desc_localizations('playlist_remove'))
    async def playlist_remove(
        self,
        interaction: discord.Interaction,
        name: str,
        position: int,
    ):
        if position < 1:
            return await interaction.response.send_message(
                "❌ Позиция должна быть >= 1.", ephemeral=True
            )

        ok = await db.remove_track(interaction.guild.id, name, position)
        if ok:
            await interaction.response.send_message(
                f"🗑 Трек #{position} удалён из плейлиста **{name}**."
            )
        else:
            await interaction.response.send_message(
                f"❌ Плейлист **{name}** или позиция #{position} не найдены.",
                ephemeral=True,
            )

    @app_commands.command(name='playlist_move', description="Переместить трек в плейлисте",
                          description_localizations=desc_localizations('playlist_move'))
    async def playlist_move(
        self,
        interaction: discord.Interaction,
        name: str,
        from_position: int,
        to_position: int,
    ):
        ok = await db.move_track(interaction.guild.id, name, from_position, to_position)
        if ok:
            await interaction.response.send_message(
                f"↔️ Трек перемещён: #{from_position} → #{to_position} в плейлисте **{name}**."
            )
        else:
            await interaction.response.send_message(
                "❌ Не удалось переместить трек (проверьте позиции).", ephemeral=True
            )

    @app_commands.command(name='playlist_delete', description="Удалить плейлист",
                          description_localizations=desc_localizations('playlist_delete'))
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        ok = await db.delete_playlist(interaction.guild.id, name)
        if ok:
            await interaction.response.send_message(
                f"🗑 Плейлист **{name}** удалён."
            )
        else:
            await interaction.response.send_message(
                f"❌ Плейлист **{name}** не найден.", ephemeral=True
            )


async def load_guild_state_safe(interaction):
    """Best-effort load of guild settings before opening the menu."""
    try:
        from utils.music_player import load_guild_state
        await load_guild_state(interaction.guild.id)
    except Exception:
        pass


async def setup(bot):
    await bot.add_cog(PlaylistCog(bot))