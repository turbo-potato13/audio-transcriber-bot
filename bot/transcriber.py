from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Base class for transcription errors."""


class UnsupportedFormatError(TranscriptionError):
    """Raised when the speech-to-text API rejects the file format."""


class RecognitionAPIError(TranscriptionError):
    """Raised when the speech-to-text API fails."""


class EmptyTranscriptionError(TranscriptionError):
    """Raised when the speech-to-text API returns no text."""


class Transcriber:
    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        model: str,
        language: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.language = language
        import aiohttp

        self._aiohttp = aiohttp
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def transcribe(self, file_path: Path, *, content_type: str | None = None) -> str:
        aiohttp = self._aiohttp
        form = aiohttp.FormData()
        form.add_field("model", self.model)
        if self.language:
            form.add_field("language", self.language)

        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            with file_path.open("rb") as file_obj:
                form.add_field(
                    "file",
                    file_obj,
                    filename=file_path.name,
                    content_type=content_type or "application/octet-stream",
                )

                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.post(self.api_url, headers=headers, data=form) as response:
                        body = await response.text()
                        if response.status in {400, 415}:
                            raise UnsupportedFormatError(_short_error(body))
                        if response.status >= 400:
                            raise RecognitionAPIError(
                                f"speech-to-text API returned HTTP {response.status}: {_short_error(body)}"
                            )

                        payload = await _read_json_response(response, body, aiohttp)
        except UnsupportedFormatError:
            raise
        except RecognitionAPIError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise RecognitionAPIError("speech-to-text API request failed") from exc
        except OSError as exc:
            raise RecognitionAPIError("failed to read audio file") from exc

        text = _extract_text(payload)
        if not text:
            raise EmptyTranscriptionError("speech-to-text API returned an empty result")

        logger.info("Speech-to-text API returned %s characters", len(text))
        return text


async def _read_json_response(response: Any, body: str, aiohttp: Any) -> Any:
    try:
        return await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError) as exc:
        raise RecognitionAPIError(f"speech-to-text API returned non-JSON response: {_short_error(body)}") from exc


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if not isinstance(payload, dict):
        return ""

    for key in ("text", "transcript", "transcription"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    result = payload.get("result")
    if isinstance(result, dict):
        nested = _extract_text(result)
        if nested:
            return nested
    if isinstance(result, str) and result.strip():
        return result.strip()

    segments = payload.get("segments")
    if isinstance(segments, list):
        parts = []
        for segment in segments:
            if isinstance(segment, dict):
                value = segment.get("text")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
        if parts:
            return " ".join(parts).strip()

    return ""


def _short_error(body: str, max_length: int = 500) -> str:
    body = body.strip()
    if len(body) <= max_length:
        return body
    return f"{body[:max_length]}..."
