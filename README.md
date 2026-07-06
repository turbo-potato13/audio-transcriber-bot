# Audio Transcriber Telegram Bot

Небольшой Telegram-бот для преобразования голосовых, аудио и аудио/видео документов в текст. Распознавание работает бесплатно и оффлайн через локальный `whisper.cpp`; OpenAI API key, ChatGPT Plus и платные speech-to-text API не нужны.

Проект рассчитан на слабую Oracle Ubuntu VM с примерно 1 GB RAM и уже работающим другим Telegram-ботом. Поэтому рекомендуемый стартовый вариант: `whisper.cpp` + multilingual model `tiny` + `WHISPER_THREADS=1`.

## Что умеет бот

- принимает Telegram voice messages, audio messages, video messages и documents с audio/video MIME type;
- скачивает файл во временную папку;
- проверяет лимит размера из `MAX_FILE_MB`, по умолчанию 20 MB;
- конвертирует файл в WAV 16 kHz mono через `ffmpeg`;
- запускает локальный `whisper-cli`;
- отвечает распознанным текстом в reply-сообщениях;
- разбивает длинный текст на несколько сообщений;
- удаляет временные файлы после обработки;
- ограничивает доступ через `ALLOWED_CHAT_IDS`;
- обрабатывает файлы последовательно, чтобы не перегружать сервер;
- логирует старт, получение файла, размер, успешное распознавание и ошибки.

## Структура

```text
.
├── bot/
│   ├── __init__.py
│   ├── config.py
│   ├── files.py
│   ├── main.py
│   └── transcriber.py
├── deploy/
│   ├── audio-transcriber-bot.service
│   └── redeploy.sh
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## Установка whisper.cpp на Ubuntu

Эти команды ставят локальное оффлайн-распознавание отдельно от проекта бота:

```bash
cd /home/ubuntu
sudo apt update
sudo apt install -y git cmake build-essential ffmpeg

git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp

cmake -B build
cmake --build build -j 2

./models/download-ggml-model.sh tiny
```

Для русского языка нужна multilingual-модель `tiny`, `base`, `small` и так далее. Не ставьте `tiny.en`: она только для английского.

Проверить, что бинарник появился:

```bash
ls -lh /home/ubuntu/whisper.cpp/build/bin/whisper-cli
ls -lh /home/ubuntu/whisper.cpp/models/ggml-tiny.bin
```

## Установка бота

Ниже предполагается каталог `/home/ubuntu/audio-transcriber-bot`. Он отдельный от уже существующего бота.

```bash
cd /home/ubuntu
git clone <repo-url> audio-transcriber-bot
cd /home/ubuntu/audio-transcriber-bot
```

Создайте отдельное виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Создайте `.env`:

```bash
cp .env.example .env
nano .env
```

Минимальный `.env`:

```env
BOT_TOKEN=123456:telegram-bot-token
ALLOWED_CHAT_IDS=

DOWNLOAD_DIR=/home/ubuntu/audio-transcriber-bot/tmp/downloads
MAX_FILE_MB=20

FFMPEG_BINARY=ffmpeg
WHISPER_CPP_BINARY=/home/ubuntu/whisper.cpp/build/bin/whisper-cli
WHISPER_CPP_MODEL=/home/ubuntu/whisper.cpp/models/ggml-tiny.bin
WHISPER_LANGUAGE=ru
WHISPER_THREADS=1
TRANSCRIPTION_TIMEOUT_SECONDS=600
```

`BOT_TOKEN` берется у BotFather. `ALLOWED_CHAT_IDS` сначала можно оставить пустым, запустить бота, отправить ему `/chatId`, скопировать `chat_id` в `.env`, затем перезапустить сервис.

## Переменные окружения

| Переменная | Обязательная | Описание |
| --- | --- | --- |
| `BOT_TOKEN` | да | Токен Telegram-бота от BotFather. |
| `ALLOWED_CHAT_IDS` | нет | Список chat_id через запятую. Узнать можно командой `/chatid` или `/chatId`. Если пусто, доступ не ограничивается. |
| `DOWNLOAD_DIR` | нет | Каталог временных загрузок. |
| `MAX_FILE_MB` | нет | Максимальный размер файла в MB. По умолчанию `20`. |
| `FFMPEG_BINARY` | нет | Команда или путь к `ffmpeg`. Обычно `ffmpeg`. |
| `WHISPER_CPP_BINARY` | да | Путь к `whisper-cli`. |
| `WHISPER_CPP_MODEL` | да | Путь к модели `ggml-*.bin`. Для слабой VM начать с `ggml-tiny.bin`. |
| `WHISPER_LANGUAGE` | нет | Язык распознавания. Для русского `ru`. Можно оставить пустым для autodetect, но на слабой VM лучше `ru`. |
| `WHISPER_THREADS` | нет | Число CPU-потоков. Для 1 GB RAM и второго бота рекомендуется `1`. |
| `TRANSCRIPTION_TIMEOUT_SECONDS` | нет | Timeout локального распознавания. По умолчанию `600`. |

## Команды бота

- `/start` и `/help` - краткая справка;
- `/chatid` и `/chatId` - показать `chat_id`, который нужно вписать в `ALLOWED_CHAT_IDS`;
- `/status` - проверить, что бот жив.

## Локальная проверка на сервере

Запуск вручную:

```bash
cd /home/ubuntu/audio-transcriber-bot
source .venv/bin/activate
python -m bot.main
```

Остановить:

```bash
Ctrl+C
```

Если `.env` не заполнен, запуск должен остановиться на понятной ошибке `BOT_TOKEN is not set`. Реальный бот без токена не стартует.

## Systemd

Service уже подготовлен под каталог `/home/ubuntu/audio-transcriber-bot`:

```bash
sudo cp /home/ubuntu/audio-transcriber-bot/deploy/audio-transcriber-bot.service /etc/systemd/system/audio-transcriber-bot.service
sudo systemctl daemon-reload
sudo systemctl enable audio-transcriber-bot
sudo systemctl start audio-transcriber-bot
```

Проверить статус:

```bash
sudo systemctl status audio-transcriber-bot --no-pager
```

Смотреть логи:

```bash
journalctl -u audio-transcriber-bot -f
```

Перезапуск после изменения `.env`:

```bash
sudo systemctl restart audio-transcriber-bot
```

## Redeploy

```bash
cd /home/ubuntu/audio-transcriber-bot
chmod +x deploy/redeploy.sh
./deploy/redeploy.sh
```

Если не хватает прав на restart:

```bash
sudo ./deploy/redeploy.sh
```

## Если качество tiny слабое

На твоей VM безопаснее начать с `tiny`. Если качество окажется плохим, можно попробовать `base`:

```bash
cd /home/ubuntu/whisper.cpp
./models/download-ggml-model.sh base
```

Потом в `.env` заменить:

```env
WHISPER_CPP_MODEL=/home/ubuntu/whisper.cpp/models/ggml-base.bin
```

И перезапустить:

```bash
sudo systemctl restart audio-transcriber-bot
```

`small` для сервера с 1 GB RAM лучше не использовать: есть риск сильного swap и долгой обработки.
