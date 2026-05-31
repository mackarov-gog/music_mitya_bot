from dotenv import load_dotenv
import os


load_dotenv()


TOKEN = os.getenv('TOKEN')
MUSIC_FOLDER = os.getenv('MUSIC_FOLDER', './music_library')
CHAIN_PLAY_ENABLED = {}


if not os.path.exists(MUSIC_FOLDER):
    os.makedirs(MUSIC_FOLDER)

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

AUDIO_FILTER = '-af "loudnorm=I=-16:TP=-1.5:LRA=11"'

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