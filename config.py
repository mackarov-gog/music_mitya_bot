from dotenv import load_dotenv
import os


# Переменные окружения
load_dotenv()


TOKEN = os.getenv('TOKEN')
MUSIC_FOLDER = os.getenv('MUSIC_FOLDER', './music_library')


if not os.path.exists(MUSIC_FOLDER):
    os.makedirs(MUSIC_FOLDER)


# yt-dlp параметры
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# Динамическая нормализация громкости (dynaudnorm)
# f=150  — длина окна (мс), g=15 — ширина гауссова фильтра,
# p=0.9  — целевой пик, s=10 — коэффициент компрессии.
AUDIO_FILTER = '-af "dynaudnorm=f=150:g=15:p=0.9:s=10"'

FFMPEG_STREAM_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': f'-vn {AUDIO_FILTER} -loglevel quiet'
}

FFMPEG_LOCAL_OPTIONS = {
    'options': f'-vn {AUDIO_FILTER} -loglevel quiet'
}

RADIO_FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': f'-vn {AUDIO_FILTER} -loglevel quiet'
}