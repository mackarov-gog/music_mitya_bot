FROM python:3.10-slim

# Установка ffmpeg и зависимостей для PyNaCl
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libffi-dev \
    libnacl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Директории для локальной музыки и персистентной БД
RUN mkdir -p /app/music_library /app/data

# Healthcheck: /tmp/bot_health обновляется каждые 30 секунд.
# Контейнер считается unhealthy, если файл старше 90 секунд.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,time; t=os.path.getmtime('/tmp/bot_health'); exit(0 if time.time()-t<90 else 1)"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-u", "main.py"]
