from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from uuid import uuid4


logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Base class for transcription errors."""


class UnsupportedFormatError(TranscriptionError):
    """Raised when the local tools cannot decode the audio file."""


class RecognitionError(TranscriptionError):
    """Raised when local speech recognition fails."""


class EmptyTranscriptionError(TranscriptionError):
    """Raised when local speech recognition returns no text."""


class Transcriber:
    def __init__(
        self,
        *,
        whisper_cpp_binary: Path,
        whisper_cpp_model: Path,
        ffmpeg_binary: str = "ffmpeg",
        language: str | None = "ru",
        threads: int = 1,
        timeout_seconds: int = 600,
    ) -> None:
        self.whisper_cpp_binary = whisper_cpp_binary
        self.whisper_cpp_model = whisper_cpp_model
        self.ffmpeg_binary = ffmpeg_binary
        self.language = language
        self.threads = threads
        self.timeout_seconds = timeout_seconds

    async def transcribe(self, file_path: Path, *, content_type: str | None = None) -> str:
        del content_type

        self._validate_runtime_files()

        wav_path = file_path.with_name(f"{file_path.stem}.{uuid4().hex}.wav")
        try:
            await self._convert_to_wav(file_path, wav_path)
            stdout, stderr = await self._run_whisper(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)

        text = _extract_text(stdout)
        if not text:
            text = _extract_text(stderr)

        if not text:
            raise EmptyTranscriptionError("local speech recognition returned an empty result")

        logger.info("Local speech recognition returned %s characters", len(text))
        return text

    def _validate_runtime_files(self) -> None:
        if not self.whisper_cpp_binary.exists():
            raise RecognitionError(f"whisper.cpp binary not found: {self.whisper_cpp_binary}")
        if not self.whisper_cpp_model.exists():
            raise RecognitionError(f"whisper.cpp model not found: {self.whisper_cpp_model}")

    async def _convert_to_wav(self, source_path: Path, wav_path: Path) -> None:
        command = [
            self.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]

        stdout, stderr, return_code = await _run_command(command, timeout_seconds=self.timeout_seconds)
        if return_code != 0:
            logger.warning("ffmpeg failed: %s", stderr or stdout)
            raise UnsupportedFormatError("ffmpeg failed to decode the file")

    async def _run_whisper(self, wav_path: Path) -> tuple[str, str]:
        command = [
            str(self.whisper_cpp_binary),
            "-m",
            str(self.whisper_cpp_model),
            "-f",
            str(wav_path),
            "-t",
            str(self.threads),
            "-nt",
        ]

        if self.language:
            command.extend(["-l", self.language])

        stdout, stderr, return_code = await _run_command(command, timeout_seconds=self.timeout_seconds)
        if return_code != 0:
            logger.warning("whisper.cpp failed: %s", stderr or stdout)
            raise RecognitionError("whisper.cpp command failed")

        return stdout, stderr


async def _run_command(command: list[str], *, timeout_seconds: int) -> tuple[str, str, int]:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise RecognitionError(f"failed to start command: {command[0]}") from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RecognitionError(f"command timed out after {timeout_seconds} seconds: {command[0]}") from exc

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return stdout, stderr, process.returncode or 0


def _extract_text(output: str) -> str:
    parts: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or _looks_like_log_line(line):
            continue

        line = re.sub(r"^\[[\d:.,\s>\-]+\]\s*", "", line).strip()
        if line and not _looks_like_log_line(line):
            parts.append(line)

    return " ".join(parts).strip()


def _looks_like_log_line(line: str) -> bool:
    prefixes = (
        "whisper_",
        "ggml_",
        "main:",
        "system_info:",
        "sampling:",
        "n_threads",
    )
    return line.startswith(prefixes)
