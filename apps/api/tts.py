"""
TTS provider for incident summaries.
Supports OpenAI TTS, ElevenLabs, and mock mode.
"""
from __future__ import annotations

import os
import logging
import uuid
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("agora.tts")

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "mock")  # openai | elevenlabs | mock
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
TTS_CACHE_DIR = Path(__file__).parent / ".tts_cache"
TTS_MAX_CHARS = 800


class TTSProvider(ABC):
    """Abstract TTS provider."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "") -> bytes:
        """Synthesize text to audio bytes (MP3)."""
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class MockTTSProvider(TTSProvider):
    """Mock TTS — returns empty bytes for demo."""

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        logger.info(f"[TTS Mock] Would synthesize {len(text)} chars")
        return b""

    def name(self) -> str:
        return "mock"


class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS via /v1/audio/speech API."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_TTS_MODEL", "tts-1")

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        voice = voice or TTS_VOICE
        url = "https://api.openai.com/v1/audio/speech"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "input": text[:TTS_MAX_CHARS],
            "voice": voice,
            "response_format": "mp3",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.content

    def name(self) -> str:
        return "openai"


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs TTS API."""

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        voice_id = voice or ELEVENLABS_VOICE_ID
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
        payload = {
            "text": text[:TTS_MAX_CHARS],
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.content

    def name(self) -> str:
        return "elevenlabs"


def get_tts_provider() -> TTSProvider:
    """Factory: get TTS provider based on env config."""
    if TTS_PROVIDER == "openai" and os.getenv("OPENAI_API_KEY"):
        return OpenAITTSProvider()
    elif TTS_PROVIDER == "elevenlabs" and ELEVENLABS_API_KEY:
        return ElevenLabsTTSProvider()
    return MockTTSProvider()


def _cache_key(text: str, provider: str) -> str:
    """Generate cache key from text + provider."""
    h = hashlib.sha256(f"{provider}:{text}".encode()).hexdigest()[:16]
    return h


async def synthesize_cached(text: str, voice: str = "") -> Optional[str]:
    """
    Synthesize text with caching. Returns path to MP3 file or None.
    """
    provider = get_tts_provider()
    if provider.name() == "mock":
        return None

    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(text, provider.name())
    cache_path = TTS_CACHE_DIR / f"{key}.mp3"

    if cache_path.exists():
        logger.info(f"[TTS] Cache hit: {cache_path.name}")
        return str(cache_path)

    try:
        audio = await provider.synthesize(text, voice)
        if audio:
            cache_path.write_bytes(audio)
            logger.info(f"[TTS] Synthesized and cached: {cache_path.name} ({len(audio)} bytes)")
            return str(cache_path)
    except Exception as e:
        logger.warning(f"[TTS] Synthesis failed: {e}")

    return None
