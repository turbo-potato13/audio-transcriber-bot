from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4


logger = logging.getLogger(__name__)

SUPPORTED_MIME_PREFIXES = ("audio/", "video/")
SUPPORTED_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".amr",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
}

TELEGRAM_SAFE_MESSAGE_LENGTH = 3900


def ensure_download_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def make_temp_file_path(download_dir: Path, file_name: str | None, default_suffix: str) -> Path:
    suffix = _safe_suffix(file_name) or default_suffix
    return download_dir / f"{uuid4().hex}{suffix}"


def is_supported_document(file_name: str | None, mime_type: str | None) -> bool:
    if mime_type and mime_type.lower().startswith(SUPPORTED_MIME_PREFIXES):
        return True

    suffix = Path(file_name or "").suffix.lower()
    return suffix in SUPPORTED_EXTENSIONS


def human_file_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown size"

    units = ("B", "KB", "MB", "GB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


def split_text(text: str, max_length: int = TELEGRAM_SAFE_MESSAGE_LENGTH) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    remaining = normalized

    while len(remaining) > max_length:
        split_at = _best_split_position(remaining, max_length)
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def remove_file_quietly(path: Path | None) -> None:
    if not path:
        return

    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove temporary file: %s", path, exc_info=True)


def _safe_suffix(file_name: str | None) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix and len(suffix) <= 16:
        return suffix
    return ""


def _best_split_position(text: str, max_length: int) -> int:
    window = text[:max_length]
    for separator in ("\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "):
        position = window.rfind(separator)
        if position >= max_length // 2:
            return position + len(separator)
    return max_length
