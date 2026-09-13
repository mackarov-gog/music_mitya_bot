import discord
from discord.ext import commands, tasks
import os
import time
import config
from utils.db import init_db


class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.queues = {}

    @tasks.loop(seconds=30)
    async def healthcheck_loop(self):
        try:
            with open("/tmp/bot_health", "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass

    @tasks.loop(seconds=60)
    async def watchdog_loop(self):
        """Self-exit if the health file is stale (event loop partially frozen).

        Forces the container to be restarted by Docker when the healthcheck
        loop itself cannot keep running.
        """
        if os.environ.get("DISABLE_WATCHDOG") == "1":
            return
        try:
            mtime = os.path.getmtime("/tmp/bot_health")
            if time.time() - mtime > 90:
                print("Watchdog: health file stale, exiting process.")
                os._exit(1)
        except FileNotFoundError:
            # health file not written yet on cold start — allow grace period
            pass
        except Exception:
            pass

    async def setup_hook(self):
        # Database for playlists and guild settings
        try:
            await init_db()
            print("База данных инициализирована.")
        except Exception as e:
            print(f"Ошибка инициализации БД: {e}")

        self.healthcheck_loop.start()
        self.watchdog_loop.start()

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                except Exception as e:
                    print(f"Ошибка загрузки кога {filename}: {e}")
        await self.tree.sync()
        print("Коги загружены и слеш-команды синхронизированы!")

    async def on_ready(self):
        print(f'Бот {self.user} успешно запущен!')

    async def on_voice_state_update(self, member, before, after):
        """Clean up guild state when the bot is disconnected from voice."""
        if member.id != self.user.id:
            return
        if before.channel and after.channel is None:
            # Bot left voice; reset transient state for this guild
            from utils.music_player import (
                queues, playback_timers, radio_pause_states,
                last_player_messages, last_played_items, repeat_states,
            )
            guild_id = before.channel.guild.id
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


bot = MusicBot()

if __name__ == "__main__":
    if not config.TOKEN:
        print("Ошибка: Токен бота не найден в .env")
    else:
        bot.run(config.TOKEN)