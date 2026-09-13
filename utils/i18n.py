"""Lightweight i18n for user-facing bot strings (Russian / English).

The active language is stored per guild in the database and cached in memory.
All translations are keyed; unknown keys fall back to the Russian string.
"""
import os

SUPPORTED_LANGUAGES = ('ru', 'en')

_language_cache: dict[int, str] = {}


def get_lang(guild_id: int) -> str:
    """Return the cached language for a guild (default 'ru')."""
    return _language_cache.get(guild_id, 'ru')


def set_lang(guild_id: int, lang: str) -> None:
    """Update the in-memory language cache."""
    if lang in SUPPORTED_LANGUAGES:
        _language_cache[guild_id] = lang
    else:
        _language_cache[guild_id] = 'ru'


T = {
    'ru': {
        # Player embed
        'now_playing': '🎶 Сейчас играет',
        'progress': '⏱ Прогресс',
        'live': '`🔴 Прямой эфир`',
        'local_file': '`📁 Локальный файл`',
        'source': '📺 Источник',
        'requested_by': '👤 Заказал',
        'in_queue': '📋 В очереди: {count} треков',
        'queue_short': '📋 В очереди: {count}',
        'status': '⚙️ Статус',
        'paused': '⏸ На паузе',
        'playing': '▶️ Играет',
        'repeat_off': 'Выкл',
        'repeat_one': 'Один',
        'repeat_all': 'Все',
        'on': 'Вкл',
        'off': 'Выкл',

        # Help
        'help_title': '❓ Митя — справка',
        'help_desc': 'Музыкальный бот: YouTube, радио, локальные файлы, плейлисты.',
        'help_music': '🎵 **Музыка**',
        'help_controls': '🎛 **Управление**',
        'help_player': '🎮 **Плеер**',
        'help_playlists': '📋 **Плейлисты**',
        'help_settings': '⚙️ **Настройки**',
        'cmd_play': 'Найти и воспроизвести музыку с YouTube (по поиску или ссылке)',
        'cmd_radio': 'Найти и включить интернет-радиостанцию',
        'cmd_playlocal': 'Выбрать локальный файл из списка и запустить (или по имени)',
        'cmd_volume': 'Установить громкость 0–200%',
        'cmd_queue': 'Показать текущую очередь',
        'cmd_pause': 'Поставить на паузу',
        'cmd_resume': 'Продолжить воспроизведение',
        'cmd_skip': 'Пропустить текущий трек',
        'cmd_skipto': 'Пропустить несколько треков (указать количество)',
        'cmd_seek': 'Перемотать трек на указанную секунду',
        'cmd_stop': 'Остановить и очистить очередь',
        'cmd_chainplay': 'Переключить режим «По цепочке» (автоподбор похожих)',
        'cmd_menu': 'Показать панель управления плеером',
        'cmd_help': 'Показать эту справку',
        'cmd_language': 'Выбрать язык бота',
        'cmd_playlist': 'Управление серверными плейлистами (см. ниже)',
        'player_buttons': 'Кнопки плеера: ⏮️ предыдущий · ⏯️ пауза · ⏭️ скип · 🔀 перемешать · 🔁 повтор · 🔗 цепочка · 📜 очередь · 📋 плейлисты · 🔊 громкость · ⏹️ стоп',
        'playlist_cmds': ('`/playlist create <name>` — создать\n'
                          '`/playlist add <name> <query>` — добавить по поиску\n'
                          '`/playlist addurl <name> <url> [kind]` — добавить по ссылке\n'
                          '`/playlist addlocal <name> <file>` — добавить локальный файл\n'
                          '`/playlist list` — список\n'
                          '`/playlist show <name>` — показать треки\n'
                          '`/playlist play <name> [position] [append]` — запустить\n'
                          '`/playlist remove <name> <position>` — удалить трек\n'
                          '`/playlist move <name> <from> <to>` — переместить\n'
                          '`/playlist delete <name>` — удалить плейлист'),
        'help_footer': 'Серверные плейлисты и настройки сохраняются между перезапусками.',

        # Menu
        'menu_no_vc': '🤖 Бот не в голосовом канале.',
        'menu_nothing': '📭 Нет ни одного сыгранного трека.',
        'menu_shown': '🎮 Панель управления плеером:',
        'queue_empty_menu': '📭 Очередь пуста.',

        # Modals
        'modal_seconds': 'Секунды',
        'modal_seconds_ph': 'Например: 90',
        'modal_seek_title': '⏩ Перемотка',
        'modal_skipn_label': 'Сколько треков пропустить',
        'modal_skipn_ph': 'Например: 3',
        'modal_skipn_title': '⏭ Пропустить несколько',

        # Buttons
        'btn_queue': 'Очередь',
        'btn_playlists': 'Плейлисты',
        'btn_seek': 'Перемотка',
        'btn_skipn': 'Скип N',
        'btn_volume': 'Громкость',
        'btn_language': 'Язык',

        # Language
        'lang_set': '✅ Язык установлен: 🇷🇺 Русский',
    },
    'en': {
        # Player embed
        'now_playing': '🎶 Now Playing',
        'progress': '⏱ Progress',
        'live': '`🔴 Live`',
        'local_file': '`📁 Local file`',
        'source': '📺 Source',
        'requested_by': '👤 Requested by',
        'in_queue': '📋 In queue: {count} tracks',
        'queue_short': '📋 In queue: {count}',
        'status': '⚙️ Status',
        'paused': '⏸ Paused',
        'playing': '▶️ Playing',
        'repeat_off': 'Off',
        'repeat_one': 'One',
        'repeat_all': 'All',
        'on': 'On',
        'off': 'Off',

        # Help
        'help_title': '❓ Mitya — Help',
        'help_desc': 'Music bot: YouTube, radio, local files, playlists.',
        'help_music': '🎵 **Music**',
        'help_controls': '🎛 **Controls**',
        'help_player': '🎮 **Player**',
        'help_playlists': '📋 **Playlists**',
        'help_settings': '⚙️ **Settings**',
        'cmd_play': 'Search and play music from YouTube (by search or link)',
        'cmd_radio': 'Search and play an internet radio station',
        'cmd_playlocal': 'Pick a local file from a list and play (or by name)',
        'cmd_volume': 'Set volume 0–200%',
        'cmd_queue': 'Show the current queue',
        'cmd_pause': 'Pause playback',
        'cmd_resume': 'Resume playback',
        'cmd_skip': 'Skip the current track',
        'cmd_skipto': 'Skip several tracks (specify a number)',
        'cmd_seek': 'Seek the track to a specified second',
        'cmd_stop': 'Stop and clear the queue',
        'cmd_chainplay': 'Toggle chain-play mode (similar tracks autoplay)',
        'cmd_menu': 'Show the player control panel',
        'cmd_help': 'Show this help',
        'cmd_language': 'Choose bot language',
        'cmd_playlist': 'Manage server playlists (see below)',
        'player_buttons': 'Player buttons: ⏮️ prev · ⏯️ pause · ⏭️ skip · 🔀 shuffle · 🔁 repeat · 🔗 chain · 📜 queue · 📋 playlists · 🔊 volume · ⏹️ stop',
        'playlist_cmds': ('`/playlist create <name>` — create\n'
                          '`/playlist add <name> <query>` — add by search\n'
                          '`/playlist addurl <name> <url> [kind]` — add by link\n'
                          '`/playlist addlocal <name> <file>` — add local file\n'
                          '`/playlist list` — list\n'
                          '`/playlist show <name>` — show tracks\n'
                          '`/playlist play <name> [position] [append]` — play\n'
                          '`/playlist remove <name> <position>` — remove track\n'
                          '`/playlist move <name> <from> <to>` — move\n'
                          '`/playlist delete <name>` — delete playlist'),
        'help_footer': 'Server playlists and settings persist across restarts.',

        # Menu
        'menu_no_vc': '🤖 The bot is not in a voice channel.',
        'menu_nothing': '📭 No track has been played yet.',
        'menu_shown': '🎮 Player control panel:',
        'queue_empty_menu': '📭 Queue is empty.',

        # Modals
        'modal_seconds': 'Seconds',
        'modal_seconds_ph': 'e.g. 90',
        'modal_seek_title': '⏩ Seek',
        'modal_skipn_label': 'How many tracks to skip',
        'modal_skipn_ph': 'e.g. 3',
        'modal_skipn_title': '⏭ Skip several',

        # Buttons
        'btn_queue': 'Queue',
        'btn_playlists': 'Playlists',
        'btn_seek': 'Seek',
        'btn_skipn': 'Skip N',
        'btn_volume': 'Volume',
        'btn_language': 'Language',

        # Language
        'lang_set': '✅ Language set: 🇬🇧 English',
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """Return the localized string for key. Falls back to Russian, then the key."""
    lang = lang if lang in SUPPORTED_LANGUAGES else 'ru'
    text = T.get(lang, {}).get(key)
    if text is None:
        text = T['ru'].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def default_language() -> str:
    """Language used before a guild picks one. Mirror of config env, RU by default."""
    return os.getenv('BOT_DEFAULT_LANGUAGE', 'ru') if 'BOT_DEFAULT_LANGUAGE' in os.environ else 'ru'


# --------------------------------------------------------------------------- #
# Command localization (native Discord name/description translations)
# --------------------------------------------------------------------------- #
# Discord shows these based on the client locale of the user.

COMMAND_DESC = {
    'play': {
        'ru': 'Найти и воспроизвести музыку',
        'en': 'Search and play music',
    },
    'radio': {
        'ru': 'Найти и включить интернет-радио',
        'en': 'Find and play internet radio',
    },
    'playlocal': {
        'ru': 'Выбрать локальный файл и воспроизвести',
        'en': 'Pick a local file and play it',
    },
    'volume': {
        'ru': 'Установить громкость (0–200%)',
        'en': 'Set volume (0–200%)',
    },
    'queue': {
        'ru': 'Показать очередь',
        'en': 'Show the queue',
    },
    'pause': {
        'ru': 'Пауза',
        'en': 'Pause',
    },
    'resume': {
        'ru': 'Продолжить',
        'en': 'Resume',
    },
    'skip': {
        'ru': 'Пропустить текущий трек',
        'en': 'Skip the current track',
    },
    'skipto': {
        'ru': 'Пропустить несколько треков',
        'en': 'Skip several tracks',
    },
    'seek': {
        'ru': 'Перемотать трек',
        'en': 'Seek the track',
    },
    'stop': {
        'ru': 'Остановить и очистить очередь',
        'en': 'Stop and clear the queue',
    },
    'chainplay': {
        'ru': 'Режим «По цепочке»: автоподбор похожих треков',
        'en': 'Chain-play: autoplay similar tracks',
    },
    'menu': {
        'ru': 'Показать панель управления плеером',
        'en': 'Show the player control panel',
    },
    'help': {
        'ru': 'Показать справку по командам',
        'en': 'Show command help',
    },
    'language': {
        'ru': 'Выбрать язык бота',
        'en': 'Choose bot language',
    },
    'playlist': {
        'ru': 'Управление серверными плейлистами',
        'en': 'Manage server playlists',
    },
    'playlist_create': {
        'ru': 'Создать плейлист',
        'en': 'Create a playlist',
    },
    'playlist_add': {
        'ru': 'Добавить трек по поиску YouTube в плейлист',
        'en': 'Add a track from YouTube search to a playlist',
    },
    'playlist_addurl': {
        'ru': 'Добавить трек по ссылке в плейлист',
        'en': 'Add a track by link to a playlist',
    },
    'playlist_addlocal': {
        'ru': 'Добавить локальный файл в плейлист',
        'en': 'Add a local file to a playlist',
    },
    'playlist_list': {
        'ru': 'Список плейлистов сервера',
        'en': 'List server playlists',
    },
    'playlist_show': {
        'ru': 'Показать треки плейлиста',
        'en': 'Show playlist tracks',
    },
    'playlist_play': {
        'ru': 'Запустить плейлист в очередь',
        'en': 'Play a playlist into the queue',
    },
    'playlist_remove': {
        'ru': 'Удалить трек из плейлиста',
        'en': 'Remove a track from the playlist',
    },
    'playlist_move': {
        'ru': 'Переместить трек в плейлисте',
        'en': 'Move a track in the playlist',
    },
    'playlist_delete': {
        'ru': 'Удалить плейлист',
        'en': 'Delete a playlist',
    },
}


def desc_localizations(cmd_key: str) -> dict[str, str]:
    """Return {locale: description} for Discord native localization."""
    entry = COMMAND_DESC.get(cmd_key, {})
    out = {}
    for locale, text in entry.items():
        out[f'discord.{locale}'] = text
    return out