from dotenv import load_dotenv
import os


load_dotenv()


TOKEN = os.getenv('TOKEN')
MUSIC_FOLDER = os.getenv('MUSIC_FOLDER', '/app/music_library')

FFMPEG_STREAM_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 128k -loglevel quiet'
}

# Для локальных файлов
FFMPEG_LOCAL_OPTIONS = {
    'before_options': '',   # без reconnect
    'options': '-vn -b:a 128k -loglevel quiet'
}