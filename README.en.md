<div align="center">

# 🎵 Mitya Music Bot — English

**Mitya** — an advanced Discord music bot built with `discord.py`.

_🌍 [Русский](README.ru.md) | 📄 [Main README](README.md)_

</div>

---

## 🚀 Features

| Feature | Description |
|---|---|
| 🎬 **YouTube** | Search by name or play by direct link via yt-dlp |
| 📻 **Radio** | Interactive search over 30,000+ stations via `radio-browser.info` |
| 📁 **Local library** | Streaming audio files from a server folder |
| 📋 **Server playlists** | Guild-wide shared playlists persisted in SQLite (survive restarts) |
| 🔗 **Chain-play mode** | The bot auto-picks similar tracks when the queue is over |
| 🔊 **Auto volume leveling** | `dynaudnorm` (FFmpeg) normalizes all sources + manual `/volume` |
| 🎛 **Smart player** | 9 buttons: prev/play/skip/shuffle/repeat/queue/playlists/volume/stop |
| 🖥 **Docker & Healthcheck** | Auto-restart on crash, healthcheck probe, watchdog on freeze |
| 🔐 **Security** | Path traversal protection, parameterized SQL, owner check in selects |

---

## ⚙️ Setup

### Locally

Requirements: **Python 3.10+**, [FFmpeg](https://ffmpeg.org/download.html).

```bash
git clone https://github.com/your-username/music_mitya_bot.git
cd music_mitya_bot

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Docker (recommended)

FFmpeg is pre-configured in the image.

```bash
docker compose up -d --build
```

---

## 📝 Configuration

Create a `.env` file in the project root:

```env
TOKEN=your_bot_token
MUSIC_FOLDER=./music_library
# SYNC_GUILD_ID=123456789  # Guild ID for instant slash-command sync
```

FFmpeg options and the normalization filter are configured in `config.py`.

> ⚠️ **Slash commands missing?** Discord caches global commands for up to 1 hour.
> Set `SYNC_GUILD_ID=<your server id>` in `.env` — commands appear instantly.
> Or just wait ~1h / re-login to Discord (Ctrl+R).

---

## 🕹 Commands

| Command | Description |
| :--- | :--- |
| `/play <query>` | Search YouTube and enqueue (or by direct link) |
| `/radio <query>` | Find a radio station and stream it |
| `/playlocal [name]` | Pick a local file from a list and play immediately (or by name) |
| `/volume <0-200>` | Set volume (persisted per guild) |
| `/queue` | Show the current queue |
| `/pause` / `/resume` | Pause / resume |
| `/skip` | Skip the current track |
| `/stop` | Stop and clear the queue |
| `/chainplay` | Toggle chain-play mode |
| `/skipto <count>` | Skip several tracks |
| `/seek <seconds>` | Seek the track to a second |
| `/menu` | Show the player panel again |
| `/help` | Show command help |
| `/language` | Choose language (RU/EN) |
| `/playlist` | **Interactive playlist menu** (recommended) |
| `/playlist create <name>` | Create a playlist |
| `/playlist add <name> <query>` | Add a track by YouTube search |
| `/playlist addurl <name> <url> [kind]` | Add by URL (YouTube/Radio) |
| `/playlist addlocal <name> <file>` | Add a local file |
| `/playlist list` | List server playlists |
| `/playlist show <name>` | Show playlist tracks |
| `/playlist play <name> [position] [append]` | Play a playlist into the queue |
| `/playlist remove <name> <position>` | Remove a track |
| `/playlist move <name> <from> <to>` | Move a track |
| `/playlist delete <name>` | Delete a playlist |

---

## 📋 Interactive Playlist Menu

The **`/playlist`** command opens a button-driven panel for managing server playlists — no commands to memorize:

```
📋 Playlist Menu
━━━━━━━━━━━━━━━━━━━━
• Nostalgia
• Chill Music
• Morning Mix

[📋 List] [▶️ Play] [➕ Create]
[🍕 Add Track] [🗑 Delete] [🚪 Close]
```

| Button | What it does |
|---|---|
| **📋 List** | Show tracks of a chosen playlist (pagination, remove by number) |
| **▶️ Play** | Pick a playlist → enqueue it |
| **➕ Create** | Create a new playlist (modal for the name) |
| **🍕 Add Track** | Add a track to a playlist (modal: playlist name + title/link) |
| **🗑 Delete** | Delete a playlist (confirmation) |
| **🚪 Close** | Close the menu |

Inside the track list: **◀️ ▶️** — pages, **🗑 Remove №** — modal to remove by position, **🚪 Back** — return to the menu.

> **Tip:** the traditional `/playlist ...` commands still work for quick actions.

---

## 🎛 Interactive Player

Every played track brings up the control panel (3 rows, 14 buttons):

```
⏮️ ⏯️ ⏭️ 🔀 🔁    ← previous / play-pause / skip / shuffle / repeat (off·one·all)
🔗 📜 📋          ← chain-play / queue (paginated) / playlists
⏩ ⏭ 🔊 🌐 ⏹️    ← seek / skip N / volume / language / stop
```

- Radio pause is emulated (stop + re-insert at queue head)
- Repeat is ignored for endless radio streams
- Player buttons are available to all guild members; select menus are owner-only
- When the queue ends, a mini-panel appears: 🔗 chain / ▶️ replay / ⏹️ stop

---

## 🗄 Persistence (SQLite)

| Data | Storage | Survives restart |
|---|---|---|
| Playlists and tracks | `data/bot.db` (SQLite, WAL) | ✅ |
| Guild settings (volume, chainplay, repeat) | `data/bot.db` (guild_settings) | ✅ |
| Queue, timers, previous stack | in-memory | ❌ (expected) |

---

## 🖥 Docker & Resilience

| Mechanism | Purpose |
|---|---|
| `restart: unless-stopped` | Restart on process crash |
| `HEALTHCHECK` | Probes `/tmp/bot_health` (updated every 30s) |
| `watchdog_loop` | Self-exit on frozen event loop |
| Volume `./data` | Database persistence |
| Volume `./music_library` | Local audio files |

---

## 📂 Project Structure

```text
music_mitya_bot/
├── cogs/
│   ├── youtube.py        # YouTube search/stream, /volume
│   ├── radio.py          # Internet radio
│   ├── local_audio.py    # Local files (/playlocal)
│   ├── playlists.py      # Server playlists
│   └── autoplay.py       # Chain-play mode
├── utils/
│   ├── music_player.py   # Core: queue, play_next, player UI, embed
│   ├── ytdl_source.py    # yt-dlp wrapper
│   ├── radio_api.py      # radio-browser.info client
│   └── db.py             # SQLite layer (playlists, settings)
├── config.py             # FFmpeg, dynaudnorm, paths
├── main.py               # Entry point, healthcheck, watchdog
├── docs/                 # Architecture, queue contract, player, deploy
└── docker-compose.yml    # Deployment
```

---

## 📚 Documentation

- 📖 **[User Guide](docs/USER_GUIDE_EN.md)** — how to use the bot
- [`docs/ARCHITECTURE_PLAN.md`](docs/ARCHITECTURE_PLAN.md) — architecture & plan
- [`docs/QUEUE_CONTRACT.md`](docs/QUEUE_CONTRACT.md) — queue item contract
- [`docs/PLAYER.md`](docs/PLAYER.md) — player specification
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Docker deployment

---

<div align="center">

_🌍 [Русский](README.ru.md) | 📄 [Main README](README.md)_

</div>