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

COPY main.py config.py ./
RUN mkdir -p /app/music_library

CMD ["python", "-u", "main.py"]