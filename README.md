# Audio Transcriber Telegram Bot

Небольшой Telegram-бот для преобразования голосовых, аудио и аудио/видео документов в текст через внешний speech-to-text API. Проект рассчитан на личное использование и слабую VM: локальная модель распознавания не запускается.

## Что умеет бот

- принимает Telegram voice messages, audio messages, video messages и documents с audio/video MIME type;
- скачивает файл во временную папку;
- проверяет лимит размера из `MAX_FILE_MB`, по умолчанию 20 MB;
- отправляет файл во внешний speech-to-text API;
- отвечает распознанным текстом в reply-сообщениях;
- разбивает длинный текст на несколько сообщений;
- удаляет временный файл после обработки;
- ограничивает доступ через `ALLOWED_CHAT_IDS`;
- логирует старт, получение файла, размер, успешное распознавание и ошибки.

По умолчанию используется OpenAI-compatible endpoint:

`https://api.openai.com/v1/audio/transcriptions`

Для OpenAI ключ берется в [OpenAI API keys](https://platform.openai.com/api-keys). В `.env` нужно вставить сам secret key целиком в `SPEECH_TO_TEXT_API_KEY`.

Важно: это не Telegram bot token и не ChatGPT Plus. Это отдельный API key в OpenAI Platform. Для работы API на аккаунте должна быть доступна оплата/кредиты.

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
├── README.md
└── requirements.txt
```

## Локальный запуск

Создайте виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Установите зависимости:

```bash
pip install -r requirements.txt
```

Создайте `.env`:

```bash
cp .env.example .env
nano .env
```

Минимально заполните:

```env
BOT_TOKEN=123456:telegram-bot-token
SPEECH_TO_TEXT_API_KEY=sk-your-openai-api-key
ALLOWED_CHAT_IDS=123456789
```

`ALLOWED_CHAT_IDS` можно узнать командой `/chatid` или `/chatId`. При первом запуске можно оставить `ALLOWED_CHAT_IDS` пустым, отправить команду боту, скопировать `chat_id` в `.env`, затем перезапустить бота.

Запустите бота:

```bash
python -m bot.main
```

## Переменные окружения

| Переменная | Обязательная | Описание |
| --- | --- | --- |
| `BOT_TOKEN` | да | Токен Telegram-бота от BotFather. |
| `SPEECH_TO_TEXT_API_KEY` | да | Secret key от OpenAI Platform или другого OpenAI-compatible speech-to-text сервиса. Для OpenAI создается на `https://platform.openai.com/api-keys`. |
| `ALLOWED_CHAT_IDS` | нет | Список chat_id через запятую. Узнать можно командой `/chatid` или `/chatId`. |
| `DOWNLOAD_DIR` | нет | Каталог временных загрузок. По умолчанию `tmp/downloads`. |
| `MAX_FILE_MB` | нет | Максимальный размер файла в MB. По умолчанию `20`. |
| `SPEECH_TO_TEXT_API_URL` | нет | Endpoint STT API. По умолчанию OpenAI audio transcriptions endpoint. |
| `SPEECH_TO_TEXT_MODEL` | нет | Модель STT. По умолчанию `whisper-1`. |
| `SPEECH_TO_TEXT_LANGUAGE` | нет | Подсказка языка, например `ru`. Можно оставить пустым. |
| `SPEECH_TO_TEXT_TIMEOUT_SECONDS` | нет | Timeout запроса к STT API. По умолчанию `120`. |

Если `ALLOWED_CHAT_IDS` пустой, доступ не ограничивается. Для личного бота лучше после проверки сразу заполнить `ALLOWED_CHAT_IDS`.

## Команды бота

- `/start` и `/help` - краткая справка;
- `/chatid` и `/chatId` - показать `chat_id`, который нужно вписать в `ALLOWED_CHAT_IDS`;
- `/status` - проверить, что бот жив.

## Деплой на Ubuntu через systemd

Ниже предполагается каталог `/home/ubuntu/audio-transcriber-bot`.

Клонируйте или скопируйте проект:

```bash
cd /home/ubuntu
git clone <repo-url> audio-transcriber-bot
cd audio-transcriber-bot
```

Создайте виртуальное окружение:

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

Установите systemd service:

```bash
sudo cp deploy/audio-transcriber-bot.service /etc/systemd/system/audio-transcriber-bot.service
sudo systemctl daemon-reload
sudo systemctl enable audio-transcriber-bot
sudo systemctl start audio-transcriber-bot
```

Проверьте статус:

```bash
sudo systemctl status audio-transcriber-bot
```

Посмотрите логи:

```bash
journalctl -u audio-transcriber-bot -f
```

## Redeploy

Скрипт `deploy/redeploy.sh` делает `git pull`, обновляет зависимости и перезапускает service.

Сделайте его исполняемым на сервере:

```bash
chmod +x deploy/redeploy.sh
```

Запуск:

```bash
./deploy/redeploy.sh
```

Если запускаете не от пользователя с правами на `systemctl restart`, используйте:

```bash
sudo ./deploy/redeploy.sh
```

## Проверка без запуска реального бота

Если `.env` не заполнен, команда:

```bash
python -m bot.main
```

должна завершиться ошибкой конфигурации о том, что `BOT_TOKEN` не задан. Это нормальная проверка, что проект доходит до валидации настроек и не запускает polling без токена.
