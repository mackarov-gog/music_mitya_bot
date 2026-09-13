import discord
from discord.ext import commands, tasks
import os
import sys
import time
import config
from utils.db import init_db


def _log(msg: str):
    """Print with immediate flush so docker logs captures it."""
    print(msg, flush=True)


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
        _log("=== SETUP_HOOK START ===")
        try:
            await init_db()
            _log("База данных инициализирована.")
        except Exception as e:
            _log(f"ОШИБКА ИНИЦИАЛИЗАЦИИ БД: {type(e).__name__}: {e}")
            import traceback
            _log(traceback.format_exc())

        try:
            self.healthcheck_loop.start()
            self.watchdog_loop.start()
        except Exception as e:
            _log(f"ОШИБКА ЗАПУСКА LOOPS: {type(e).__name__}: {e}")

        _log("=== ЗАГРУЗКА COGS ===")
        loaded_cogs = []
        for filename in sorted(os.listdir('./cogs')):
            if filename.endswith('.py') and not filename.startswith('_'):
                module = f'cogs.{filename[:-3]}'
                try:
                    await self.load_extension(module)
                    loaded_cogs.append(module)
                    _log(f"OK: {module}")
                except Exception as e:
                    _log(f"ERROR: {module}: {type(e).__name__}: {e}")
                    import traceback
                    _log(traceback.format_exc())

        _log("=== КОМАНДЫ ДО SYNC ===")
        commands = self.tree.get_commands()
        _log(f"Всего команд в tree: {len(commands)}")
        for cmd in commands:
            _log(f"  /{cmd.name}")

        _log("=== SYNC ===")
        sync_guild_id = os.getenv('SYNC_GUILD_ID')
        try:
            if sync_guild_id and sync_guild_id.isdigit():
                guild = discord.Object(id=int(sync_guild_id))
                synced = await self.tree.sync(guild=guild)
                target = f"гильдию {sync_guild_id}"
            else:
                synced = await self.tree.sync()
                target = "глобально"

            _log(f"Discord получил команд: {len(synced)} (target: {target})")
            for cmd in synced:
                _log(f"  SYNCED /{cmd.name}")
        except Exception as e:
            _log(f"ОШИБКА СИНХРОНИЗАЦИИ: {type(e).__name__}: {e}")
            import traceback
            _log(traceback.format_exc())

        _log("=== ГОТОВО ===")
        _log(f"Коги загружены: {len(loaded_cogs)}")

    async def on_ready(self):
        _log(f'Бот {self.user} успешно запущен!')
        _log(f'Бот состоит в {len(self.guilds)} гильдиях')

        # Fallback: force-sync on every guild (instant, no 1h cache).
        try:
            for guild in self.guilds:
                synced = await self.tree.sync(guild=guild)
                _log(f"  Гильдия {guild.name} ({guild.id}): синхронизировано {len(synced)} команд")
            _log(f"Принудительная синхронизация на {len(self.guilds)} гильдиях выполнена.")
        except Exception as e:
            _log(f"Ошибка принудительной синхронизации: {type(e).__name__}: {e}")
            import traceback
            _log(traceback.format_exc())

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