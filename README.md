# 🎵 Mitya Music Bot

**Митя** — это продвинутый музыкальный бот для Discord, написанный на `discord.py`. Он умеет «решать вопросики» с музыкой из YouTube, стримить интернет-радио и воспроизводить локальные файлы с сервера. 

Полностью переведен на **Slash Commands (/)** и оснащен интерактивным плеером с кнопками.

---

## 🚀 Основные фишки

* **YouTube Integration**: Поиск по названию или воспроизведение по прямой ссылке.
* **Radio Browser**: Интерактивный поиск по 30,000+ станциям через API `radio-browser.info`.
* **Local Library**: Стриминг аудиофайлов напрямую из папки на сервере.
* **Smart UI**: Управление через кнопки (Play/Pause, Skip, Stop, Queue) — больше никакого спама командами.
* **Robust Engine**: Исправлены ошибки с двойными взаимодействиями (`InteractionResponded`) и зависанием FFmpeg.
* **Docker Ready**: Быстрый запуск в изолированном контейнере.

---

## 🛠 Установка и запуск

### 1. Локально (Python)
**Требования:** Python 3.10+, [FFmpeg](https://ffmpeg.org/download.html).

```bash
# Клонируем
git clone https://github.com/your-username/music_mitya_bot.git
cd music_mitya_bot

# Настраиваем окружение
python -m venv .venv
source .venv/bin/activate  # Или .venv\Scripts\activate на Windows
pip install -r requirements.txt
```

### 2. Через Docker (Рекомендуется)
Митя отлично чувствует себя в контейнере, где FFmpeg уже настроен.
```bash
docker-compose up -d --build
```

---

## ⚙️ Конфигурация

Создай файл `.env` в корне проекта:
```env
TOKEN=твой_токен_бота
MUSIC_FOLDER=\music  
```

Все технические параметры FFmpeg и лимиты поиска настраиваются в `config.py`.

---

## 🕹 Команды (Slash Commands)

| Команда | Описание |
| :--- | :--- |
| `/play <query>` | Найти на YouTube и добавить в очередь |
| `/radio <query>` | Найти радиостанцию и запустить стрим |
| `/playlocal <name>` | Запустить файл из локальной папки |
| `/listlocal` | Показать список доступных локальных файлов |
| `/queue` | Показать текущую очередь треков |
| `/stop` | Остановить музыку и очистить очередь |

> **Интерактивный плеер**: При запуске любого трека появляется панель управления. Кнопки «Play/Pause» и «Skip» работают мгновенно благодаря системе деферинга (defer) запросов.

---

## 📂 Структура проекта

```text
music_mitya_bot/
├── cogs/                # Модули бота (YouTube, Radio, Local)
├── utils/
│   ├── music_player.py  # Ядро плеера, UI-View и логика очереди
│   ├── radio_api.py     # Взаимодействие с Radio API
│   └── ytdl_source.py   # Обработка YouTube ссылок через yt-dlp
├── config.py            # Настройки FFmpeg и пути
├── main.py              # Точка входа и инициализация бота
└── docker-compose.yml   # Конфиг для деплоя
```
