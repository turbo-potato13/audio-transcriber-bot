from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from .config import Config, ConfigError, load_config
from .files import (
    ensure_download_dir,
    human_file_size,
    is_supported_document,
    make_temp_file_path,
    remove_file_quietly,
    split_text,
)
from .transcriber import EmptyTranscriptionError, RecognitionError, Transcriber, UnsupportedFormatError


logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Я преобразую голосовые и аудио сообщения в текст.\n\n"
    "Отправьте voice message, audio file, video file или document с audio/video файлом.\n\n"
    "Команды:\n"
    "/help - справка\n"
    "/chatid или /chatId - показать chat_id для ALLOWED_CHAT_IDS\n"
    "/status - проверить, что бот жив"
)


@dataclass(frozen=True)
class IncomingMedia:
    file_id: str
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    default_suffix: str
    kind: str


class DownloadError(RuntimeError):
    """Raised when Telegram file download cannot be completed."""


async def main() -> None:
    setup_logging()

    try:
        config = load_config()
    except ConfigError as exc:
        logger.critical("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    ensure_download_dir(config.download_dir)
    logger.info("Starting audio transcriber bot")

    await run_bot(config)


async def run_bot(config: Config) -> None:
    from aiogram import Bot, Dispatcher, F, Router
    from aiogram.exceptions import TelegramAPIError
    from aiogram.filters import Command
    from aiogram.types import Message

    bot = Bot(token=config.bot_token)
    dispatcher = Dispatcher()
    router = Router()
    processing_lock = asyncio.Lock()
    transcriber = Transcriber(
        whisper_cpp_binary=config.whisper_cpp_binary,
        whisper_cpp_model=config.whisper_cpp_model,
        ffmpeg_binary=config.ffmpeg_binary,
        language=config.whisper_language,
        threads=config.whisper_threads,
        timeout_seconds=config.transcription_timeout_seconds,
    )

    @router.message(Command("start", "help"))
    async def handle_help(message: Message) -> None:
        if not await ensure_allowed(message, config):
            return
        await message.answer(HELP_TEXT)

    @router.message(Command("chatid", "chatId"))
    async def handle_chat_id(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else "unknown"
        await message.answer(
            f"chat_id: {message.chat.id}\n"
            f"user_id: {user_id}\n\n"
            "Для ограничения доступа добавьте chat_id в ALLOWED_CHAT_IDS."
        )

    @router.message(Command("status"))
    async def handle_status(message: Message) -> None:
        if not await ensure_allowed(message, config):
            return
        await message.answer("Бот жив и готов принимать аудио.")

    @router.message(F.voice | F.audio | F.document | F.video)
    async def handle_media(message: Message) -> None:
        if not await ensure_allowed(message, config):
            return

        try:
            media = extract_media(message)
        except UnsupportedFormatError:
            await message.reply("Формат не поддерживается. Отправьте voice, audio или audio/video document.")
            return

        logger.info(
            "Received %s from chat_id=%s user_id=%s size=%s",
            media.kind,
            message.chat.id,
            message.from_user.id if message.from_user else None,
            media.file_size,
        )

        if media.file_size is not None and media.file_size > config.max_file_bytes:
            await message.reply(
                "Файл слишком большой: "
                f"{human_file_size(media.file_size)}. Лимит: {config.max_file_mb} MB."
            )
            logger.warning("Rejected file before download because it is too large: %s", media.file_size)
            return

        if processing_lock.locked():
            await message.reply("Сейчас обрабатываю другой файл. Ваш файл поставлен в очередь.")

        async with processing_lock:
            await process_media_message(message, bot, transcriber, config, media, TelegramAPIError)

    @router.message()
    async def handle_other(message: Message) -> None:
        if not await ensure_allowed(message, config):
            return
        await message.answer("Отправьте voice, audio, video или audio/video document для распознавания.")

    dispatcher.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


async def process_media_message(
    message: object,
    bot: object,
    transcriber: Transcriber,
    config: Config,
    media: IncomingMedia,
    telegram_error_type: type[Exception],
) -> None:
    local_path: Path | None = None

    try:
        local_path = make_temp_file_path(config.download_dir, media.file_name, media.default_suffix)

        telegram_file = await bot.get_file(media.file_id)
        if not telegram_file.file_path:
            raise DownloadError("Telegram did not provide file_path")

        with local_path.open("wb") as destination:
            await bot.download_file(telegram_file.file_path, destination=destination)

        actual_size = local_path.stat().st_size
        logger.info("Downloaded file to %s, size=%s", local_path, actual_size)

        if actual_size > config.max_file_bytes:
            await message.reply(
                "Файл слишком большой: "
                f"{human_file_size(actual_size)}. Лимит: {config.max_file_mb} MB."
            )
            logger.warning("Rejected file after download because it is too large: %s", actual_size)
            return

        await message.reply("Файл получен, начинаю локальное распознавание.")

        text = await transcriber.transcribe(local_path, content_type=media.mime_type)
        chunks = split_text(text)
        if not chunks:
            raise EmptyTranscriptionError("empty text after splitting")

        logger.info("Transcription succeeded, chunks=%s, chars=%s", len(chunks), len(text))
        for chunk in chunks:
            await message.reply(chunk)

    except (telegram_error_type, DownloadError):
        logger.exception("Failed to download Telegram file")
        await message.reply("Не удалось скачать файл. Попробуйте отправить его еще раз.")
    except UnsupportedFormatError:
        logger.exception("Local transcriber rejected file format")
        await message.reply("Формат не поддерживается или файл поврежден.")
    except EmptyTranscriptionError:
        logger.exception("Local transcriber returned empty result")
        await message.reply("Распознавание завершилось, но текст не найден.")
    except RecognitionError:
        logger.exception("Local transcription error")
        await message.reply("Ошибка локального распознавания. Проверьте установку whisper.cpp и попробуйте позже.")
    except OSError:
        logger.exception("Failed to process local temporary file")
        await message.reply("Не удалось обработать временный файл. Попробуйте еще раз.")
    finally:
        remove_file_quietly(local_path)


async def ensure_allowed(message: object, config: Config) -> bool:
    if is_allowed(message, config):
        return True

    user_id = message.from_user.id if message.from_user else None
    logger.warning("Rejected unauthorized message from chat_id=%s user_id=%s", message.chat.id, user_id)
    await message.answer("Доступ к этому боту ограничен.")
    return False


def is_allowed(message: object, config: Config) -> bool:
    if not config.allowed_chat_ids:
        return True

    return message.chat.id in config.allowed_chat_ids


def extract_media(message: object) -> IncomingMedia:
    if message.voice:
        return IncomingMedia(
            file_id=message.voice.file_id,
            file_name=None,
            mime_type=message.voice.mime_type or "audio/ogg",
            file_size=message.voice.file_size,
            default_suffix=".ogg",
            kind="voice",
        )

    if message.audio:
        return IncomingMedia(
            file_id=message.audio.file_id,
            file_name=message.audio.file_name,
            mime_type=message.audio.mime_type,
            file_size=message.audio.file_size,
            default_suffix=".mp3",
            kind="audio",
        )

    if message.video:
        return IncomingMedia(
            file_id=message.video.file_id,
            file_name=message.video.file_name,
            mime_type=message.video.mime_type,
            file_size=message.video.file_size,
            default_suffix=".mp4",
            kind="video",
        )

    if message.document:
        document = message.document
        if not is_supported_document(document.file_name, document.mime_type):
            raise UnsupportedFormatError("unsupported document")

        return IncomingMedia(
            file_id=document.file_id,
            file_name=document.file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
            default_suffix=".bin",
            kind="document",
        )

    raise UnsupportedFormatError("unsupported message")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    asyncio.run(main())
