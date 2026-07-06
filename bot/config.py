from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_STT_API_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_STT_MODEL = "whisper-1"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    speech_to_text_api_key: str
    allowed_user_ids: frozenset[int]
    allowed_chat_ids: frozenset[int]
    download_dir: Path
    max_file_mb: int
    speech_to_text_api_url: str
    speech_to_text_model: str
    speech_to_text_language: str | None
    speech_to_text_timeout_seconds: int

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
    api_key = _required("SPEECH_TO_TEXT_API_KEY")

    max_file_mb = _positive_int("MAX_FILE_MB", default=20)
    timeout_seconds = _positive_int("SPEECH_TO_TEXT_TIMEOUT_SECONDS", default=120)

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "tmp/downloads")).expanduser()

    return Config(
        bot_token=bot_token,
        speech_to_text_api_key=api_key,
        allowed_user_ids=_parse_id_list("ALLOWED_USER_IDS"),
        allowed_chat_ids=_parse_id_list("ALLOWED_CHAT_IDS"),
        download_dir=download_dir,
        max_file_mb=max_file_mb,
        speech_to_text_api_url=os.getenv("SPEECH_TO_TEXT_API_URL", DEFAULT_STT_API_URL).strip()
        or DEFAULT_STT_API_URL,
        speech_to_text_model=os.getenv("SPEECH_TO_TEXT_MODEL", DEFAULT_STT_MODEL).strip()
        or DEFAULT_STT_MODEL,
        speech_to_text_language=_optional("SPEECH_TO_TEXT_LANGUAGE"),
        speech_to_text_timeout_seconds=timeout_seconds,
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
