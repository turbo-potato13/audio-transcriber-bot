from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_WHISPER_CPP_BINARY = "/home/ubuntu/whisper.cpp/build/bin/whisper-cli"
DEFAULT_WHISPER_CPP_MODEL = "/home/ubuntu/whisper.cpp/models/ggml-tiny.bin"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_chat_ids: frozenset[int]
    download_dir: Path
    max_file_mb: int
    ffmpeg_binary: str
    whisper_cpp_binary: Path
    whisper_cpp_model: Path
    whisper_language: str | None
    whisper_threads: int
    transcription_timeout_seconds: int

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


def load_config(env_file: str | Path = ".env") -> Config:
    env_path = Path(env_file)
    if env_path.exists():
        try:
            from dotenv import load_dotenv
        except ImportError as exc:
            raise ConfigError("python-dotenv is not installed") from exc

        load_dotenv(env_path)

    bot_token = _required("BOT_TOKEN")

    max_file_mb = _positive_int("MAX_FILE_MB", default=20)
    whisper_threads = _positive_int("WHISPER_THREADS", default=1)
    timeout_seconds = _positive_int("TRANSCRIPTION_TIMEOUT_SECONDS", default=600)

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "tmp/downloads")).expanduser()

    return Config(
        bot_token=bot_token,
        allowed_chat_ids=_parse_id_list("ALLOWED_CHAT_IDS"),
        download_dir=download_dir,
        max_file_mb=max_file_mb,
        ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg").strip() or "ffmpeg",
        whisper_cpp_binary=Path(
            os.getenv("WHISPER_CPP_BINARY", DEFAULT_WHISPER_CPP_BINARY).strip()
            or DEFAULT_WHISPER_CPP_BINARY
        ).expanduser(),
        whisper_cpp_model=Path(
            os.getenv("WHISPER_CPP_MODEL", DEFAULT_WHISPER_CPP_MODEL).strip()
            or DEFAULT_WHISPER_CPP_MODEL
        ).expanduser(),
        whisper_language=_optional("WHISPER_LANGUAGE"),
        whisper_threads=whisper_threads,
        transcription_timeout_seconds=timeout_seconds,
    )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set")
    return value


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _positive_int(name: str, *, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc

    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")

    return value


def _parse_id_list(name: str) -> frozenset[int]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return frozenset()

    ids: set[int] = set()
    for chunk in raw_value.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError as exc:
            raise ConfigError(f"{name} must contain only comma-separated integer IDs") from exc

    return frozenset(ids)
