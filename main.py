import discord
from discord.ext import commands, tasks  # ДОБАВЛЕНО: tasks
import os
import time
import config

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

    async def setup_hook(self):
        self.healthcheck_loop.start()
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        await self.tree.sync()
        print("Коги загружены и слеш-команды синхронизированы!")

    async def on_ready(self):
        print(f'Бот {self.user} успешно запущен!')

bot = MusicBot()

if __name__ == "__main__":
    if not config.TOKEN:
        print("Ошибка: Токен бота не найден в .env")
    else:
        bot.run(config.TOKEN)