"""
Speech-To-Text (STT) service using Groq Whisper API.
Replaces local faster-whisper CPU runtime.
"""
import io
import os
import logging
import httpx
from typing import Optional

from config import (
    GROQ_API_KEY,
    GROQ_STT_MODEL,
    GROQ_STT_TIMEOUT_SECONDS,
    GROQ_STT_LANGUAGE,
)

logger = logging.getLogger(__name__)

GROQ_AUDIO_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    language: Optional[str] = GROQ_STT_LANGUAGE,
    prompt: Optional[str] = None,
) -> Optional[str]:
    """
    Transcribe audio bytes using Groq Whisper API.

    Args:
        audio_bytes: Raw binary audio content.
        filename: Filename with extension (e.g., audio.ogg, voice.wav).
        language: Optional ISO-639-1 language code (e.g., "en").
        prompt: Optional prompt text to guide transcription style/vocab.

    Returns:
        Transcribed text or None if empty or on error.
    """
    if not audio_bytes:
        logger.warning("STT received empty audio bytes")
        return None

    api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("Groq API key not configured for STT")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    data = {
        "model": GROQ_STT_MODEL,
    }
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt

    files = {
        "file": (filename, audio_bytes, "application/octet-stream"),
    }

    try:
        async with httpx.AsyncClient(timeout=GROQ_STT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                GROQ_AUDIO_TRANSCRIPTIONS_URL,
                headers=headers,
                data=data,
                files=files,
            )

        if response.status_code != 200:
            logger.error("Groq STT failed with status %d: %s", response.status_code, response.text)
            return None

        result = response.json()
        text = result.get("text", "").strip()
        return text or None

    except httpx.TimeoutException:
        logger.error("Groq STT request timed out after %d seconds", GROQ_STT_TIMEOUT_SECONDS)
        return None
    except Exception as e:
        logger.exception("Error calling Groq STT API: %s", e)
        return None
