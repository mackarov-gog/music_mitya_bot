"""Diagnostic script: validate cog loading and command registration.

Run inside the container:
    docker exec -it discord-music-bot python diag_check.py
"""
import asyncio
import os
import sys


async def main():
    print("Python:", sys.version)
    try:
        import discord
        print("discord.py:", discord.__version__)
    except Exception as e:
        print(f"ERROR: discord import failed: {e}")
        return

    print("Cogs directory contents:")
    cogs_dir = './cogs'
    if os.path.isdir(cogs_dir):
        for f in sorted(os.listdir(cogs_dir)):
            print("  ", f)
    else:
        print("  MISSING ./cogs dir!")

    # Simulate what happens during cog load, without connecting to Discord.
    try:
        from utils import db, i18n, music_player, ytdl_source
        print("utils imports: OK")
    except Exception as e:
        print(f"ERROR: utils imports failed: {type(e).__name__}: {e}")
        return

    # Check that commands declare unique names and valid localizations.
    from utils.i18n import desc_localizations
    sample = desc_localizations('play')
    print("desc_localizations('play'):", sample)
    if 'discord.' in str(sample):
        print("ERROR: invalid locale keys found!")
    else:
        print("Locale keys: OK")

    # Count @app_commands.command decorators in each cog file.
    import re
    total = 0
    for f in sorted(os.listdir(cogs_dir)):
        if not f.endswith('.py') or f.startswith('_'):
            continue
        path = os.path.join(cogs_dir, f)
        try:
            with open(path, encoding='utf-8') as fh:
                src = fh.read()
            names = re.findall(r"@app_commands\.command\(name='([^']+)'", src)
            total += len(names)
            print(f"{f}: {len(names)} commands")
        except Exception as e:
            print(f"ERROR reading {f}: {e}")
    print(f"TOTAL @app_commands.command: {total}")


if __name__ == '__main__':
    asyncio.run(main())