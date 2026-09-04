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
    Currently disabled / commented out to keep backend lighter.
    """
    logger.info("Audio transcription requested, but STT service is currently disabled.")
    return None
    # if not audio_bytes:
    #     logger.warning("STT received empty audio bytes")
    #     return None
    # api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    # if not api_key:
    #     logger.error("Groq API key not configured for STT")
    #     return None
    # headers = {"Authorization": f"Bearer {api_key}"}
    # data = {"model": GROQ_STT_MODEL}
    # if language:
    #     data["language"] = language
    # if prompt:
    #     data["prompt"] = prompt
    # files = {"file": (filename, audio_bytes, "application/octet-stream")}
    # try:
    #     async with httpx.AsyncClient(timeout=GROQ_STT_TIMEOUT_SECONDS) as client:
    #         response = await client.post(GROQ_AUDIO_TRANSCRIPTIONS_URL, headers=headers, data=data, files=files)
    #     if response.status_code != 200:
    #         logger.error("Groq STT failed with status %d: %s", response.status_code, response.text)
    #         return None
    #     result = response.json()
    #     text = result.get("text", "").strip()
    #     return text or None
    # except Exception as e:
    #     logger.exception("Error calling Groq STT API: %s", e)
    #     return None
