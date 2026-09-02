"""
TTS service — Google Cloud Text-to-Speech API integration.

Synthesizes audio text via Google Cloud TTS REST API and normalizes/converts
the audio output into OGG Opus format ready for WhatsApp using ffmpeg.
"""
import io
import logging
import os
import re
import subprocess
import asyncio
import httpx
from typing import Optional

from config import (
    GOOGLE_TTS_API_KEY,
    GOOGLE_TTS_LANGUAGE_CODE,
    GOOGLE_TTS_VOICE_NAME,
)

logger = logging.getLogger(__name__)

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# ── ffmpeg locator ────────────────────────────────────────────────────────────

def _find_ffmpeg() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]
    import glob
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(winget_base):
        matches = glob.glob(os.path.join(winget_base, "**", "ffmpeg.exe"), recursive=True)
        candidates = matches + candidates
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "ffmpeg"

FFMPEG_BIN = _find_ffmpeg()

# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_for_tts(text: str) -> str:
    """Strip markdown and non-speakable formatting."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_~>#|]+", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _convert_audio_to_ogg_opus(audio_bytes: bytes) -> bytes:
    """Convert MP3/LINEAR16 audio bytes to WhatsApp-compatible OGG Opus."""
    cmd = [FFMPEG_BIN, "-y", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-vbr", "on", "-f", "ogg", "pipe:1"]
    proc = subprocess.run(cmd, input=audio_bytes, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {proc.stderr.decode()[:200]}")
    return proc.stdout


async def _synthesize_google_tts(
    text: str,
    voice_name: Optional[str] = None,
    language_code: Optional[str] = None,
) -> bytes:
    import base64

    api_key = GOOGLE_TTS_API_KEY or os.getenv("GOOGLE_TTS_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Google Cloud TTS API key is not configured")

    target_voice = voice_name or GOOGLE_TTS_VOICE_NAME
    if language_code:
        target_lang = language_code
    elif target_voice and "-" in target_voice:
        parts = target_voice.split("-")
        if len(parts) >= 2:
            target_lang = f"{parts[0]}-{parts[1]}"
        else:
            target_lang = GOOGLE_TTS_LANGUAGE_CODE
    else:
        target_lang = GOOGLE_TTS_LANGUAGE_CODE

    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": target_lang,
            "name": target_voice,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
        },
    }

    url = f"{GOOGLE_TTS_URL}?key={api_key}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)

    if response.status_code != 200:
        raise RuntimeError(f"Google TTS API error ({response.status_code}): {response.text}")

    data = response.json()
    audio_content = data.get("audioContent")
    if not audio_content:
        raise RuntimeError("Google TTS returned no audio content")

    raw_audio = base64.b64decode(audio_content)

    # Convert to OGG Opus in an executor thread
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _convert_audio_to_ogg_opus, raw_audio)


async def synthesize(
    text: str,
    voice: str = GOOGLE_TTS_VOICE_NAME,
    backend: str = "auto",
    ref_audio: Optional[str] = None,
    ref_text: Optional[str] = None,
) -> bytes:
    """
    Synthesize text into OGG Opus bytes using Google Cloud Text-to-Speech.
    """
    clean_text = _clean_for_tts(text)
    if not clean_text:
        raise ValueError("Text is empty after cleaning for TTS")

    return await _synthesize_google_tts(clean_text, voice_name=voice)


def invalidate_voice_clone_cache(ref_audio: str) -> None:
    """Legacy stub for voice clone cache invalidation."""
    pass
