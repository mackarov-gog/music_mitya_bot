import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
import config
from utils.i18n import desc_localizations
from utils.music_player import get_queue, play_next, load_guild_state, get_volume


class LocalSelectView(discord.ui.View):
    """Paginated select for local files (25 per page). Selecting plays immediately."""

    def __init__(self, files: list[str], user):
        super().__init__(timeout=60)
        self.user = user
        self.files = files
        self.page = 0
        self.selected_file = None
        self._rebuild_select()

    def _page_files(self) -> list[str]:
        start = self.page * 25
        return self.files[start:start + 25]

    def _rebuild_select(self):
        self.clear_items()
        page_files = self._page_files()
        options = [
            discord.SelectOption(label=file[:90], value=file[:90])
            for file in page_files
        ]
        select = discord.ui.Select(
            placeholder="Выберите файл...",
            options=options[:25],
        )
        select.callback = self.select_callback
        self.add_item(select)

        if self.page > 0:
            prev = discord.ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary)
            prev.callback = self.prev_page
            self.add_item(prev)
        if (self.page + 1) * 25 < len(self.files):
            nxt = discord.ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary)
            nxt.callback = self.next_page
            self.add_item(nxt)

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Это не ваш список!", ephemeral=True)
        self.page -= 1
        self._rebuild_select()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Это не ваш список!", ephemeral=True)
        self.page += 1
        self._rebuild_select()
        await interaction.response.edit_message(view=self)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("❌ Это не ваш список!", ephemeral=True)
        self.selected_file = interaction.data["values"][0]
        await interaction.response.defer()
        self.stop()


class LocalAudioCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _list_files(self) -> list[str]:
        try:
            return sorted(
                f for f in os.listdir(config.MUSIC_FOLDER)
                if os.path.isfile(os.path.join(config.MUSIC_FOLDER, f))
            )
        except FileNotFoundError:
            return []

    async def _play_file(self, interaction: discord.Interaction, filename: str):
        """Connect to voice and play (or enqueue) a local file."""
        if not interaction.user.voice:
            return await interaction.followup.send(
                "❌ Вы не в голосовом канале!", ephemeral=True
            )

        base = os.path.basename(filename)
        full_path = os.path.join(config.MUSIC_FOLDER, base)
        if not os.path.exists(full_path):
            return await interaction.followup.send(
                f"❌ Файл `{filename}` не найден.", ephemeral=True
            )

        try:
            await load_guild_state(interaction.guild.id)
        except Exception:
            pass

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
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

        volume = await get_volume(interaction.guild.id) / 100.0
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(full_path, **config.FFMPEG_LOCAL_OPTIONS),
            volume=volume,
        )

        queue = get_queue(self.bot, interaction.guild.id)
        queue.append({
            'source': source,
            'title': base,
            'file_name': base,
            'duration_sec': 0,
            'user_mention': interaction.user.mention,
            'type': 'Local',
            'channel': interaction.channel
        })

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"➕ Добавлено в очередь: **{base}**")
        else:
            await play_next(self.bot, interaction.guild)
            await interaction.followup.send(f"🎶 Играю локальный файл: **{base}**")

    @app_commands.command(name='playlocal', description="Выбрать локальный файл и воспроизвести",
                          description_localizations=desc_localizations('playlocal'))
    async def playlocal(self, interaction: discord.Interaction, filename: str | None = None):
        """Play a local file. Without a filename — pick from a select."""
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "❌ Вы не в голосовом канале!", ephemeral=True
            )

        await interaction.response.defer()

        # Быстрый запуск по имени файла
        if filename:
            return await self._play_file(interaction, filename)

        # Выбор из списка → сразу запуск/добавление
        files = self._list_files()
        if not files:
            return await interaction.followup.send("📁 Нет локальных треков.", ephemeral=True)

        view = LocalSelectView(files, interaction.user)
        msg = await interaction.followup.send(
            f"📁 **Локальные треки** ({len(files)}):\nСтраница 1",
            view=view,
        )
        await view.wait()

        if view.selected_file is None:
            try:
                await msg.edit(content="⏰ Время выбора истекло.", view=None)
            except Exception:
                pass
            return

        await self._play_file(interaction, view.selected_file)

        try:
            await msg.edit(
                content=f"📁 Выбран файл: `{view.selected_file}`",
                view=None,
            )
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(LocalAudioCog(bot))