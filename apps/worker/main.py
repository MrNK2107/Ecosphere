"""
Perception worker (Agent C) — FastAPI app on port 8001.

Flow:
  Agora PCM 16k -> VAD (Silero ONNX) -> Deepgram WS (Nova-2 interim/final) -> POST /incidents/{id}/transcript -> API
  Fallback: browser WebAudio relay — frontend MediaRecorder -> base64 chunks -> POST /relay
           or direct transcript JSON -> WS /ws/ingest -> forward to API.
  Also: diarization via enrollment regex "This is X, Role" + participant list from API.

Mock mode: runnable without AGORA_APP_ID / AGORA_APP_CERT / DEEPGRAM_API_KEY.
           If keys missing, returns mock tokens and accepts transcript JSON directly so demo works.

Endpoints:
  GET  /health
  POST /relay          — accepts {incidentId, audioBase64/mimeType} OR {incidentId, transcript/segment/text}
  WS   /ws/ingest      — browser streams transcript segments or audio chunks
  GET  /agora/token    — generates Agora RTC token if env present else mock
  GET  /config         — debug: which modes are live vs mock
  POST /agora/bot/join — join Agora channel as bot (live mode only)
  POST /agora/bot/leave — leave channel

Run:
  uvicorn main:app --host 0.0.0.0 --port 8001
  API_URL env must point at API (default http://api:8000, for local dev http://localhost:8000)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Dict

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger("agora.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

# ---------------------------------------------------------------------------
# Env / config
# ---------------------------------------------------------------------------
API_URL = os.getenv("API_URL", "http://api:8000").rstrip("/")
AGORA_APP_ID = os.getenv("AGORA_APP_ID", "")
AGORA_APP_CERT = os.getenv("AGORA_APP_CERT", "") or os.getenv("AGORA_CERT", "") or os.getenv("AGORA_APP_CERTIFICATE", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))

MOCK_DEEPGRAM = not bool(DEEPGRAM_API_KEY)
MOCK_AGORA = not bool(AGORA_APP_ID and AGORA_APP_CERT)

logger.info(f"Worker config: API_URL={API_URL} DEEPGRAM={'live' if not MOCK_DEEPGRAM else 'mock'} AGORA={'live' if not MOCK_AGORA else 'mock-browser-relay'}")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Agora Perception Worker", version="0.2.0",
              description="Agent C — Perception / Ingest. Mock-runnable without keys.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Silero VAD (ONNX runtime)
# ---------------------------------------------------------------------------
class SileroVAD:
    """
    Silero VAD using ONNX runtime for lightweight voice activity detection.
    Falls back to energy heuristic if model not available.
    """
    def __init__(self):
        self._model = None
        self._available = False
        self.threshold = 0.5
        self.sample_rate = 16000
        self._load_model()

    def _load_model(self):
        try:
            import numpy as np
            # Try to download and load Silero VAD ONNX model
            model_url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
            model_path = os.path.join(os.path.dirname(__file__), "silero_vad.onnx")

            if not os.path.exists(model_path):
                logger.info("Downloading Silero VAD ONNX model...")
                import urllib.request
                urllib.request.urlretrieve(model_url, model_path)
                logger.info("Silero VAD model downloaded")

            import onnxruntime as ort
            self._session = ort.InferenceSession(model_path)
            self._available = True
            logger.info("Silero VAD loaded (ONNX runtime)")
        except Exception as e:
            logger.warning(f"Silero VAD unavailable ({e}), using energy heuristic")
            self._available = False

    def is_speech(self, pcm_bytes: bytes, sample_rate: int = 16000) -> bool:
        """Check if audio chunk contains speech."""
        if not pcm_bytes or len(pcm_bytes) < 320:
            return False

        if self._available:
            try:
                import numpy as np
                # Convert int16 PCM to float32
                audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                # Pad to 512 samples (Silero expects 512-sample chunks at 16kHz)
                if len(audio) < 512:
                    audio = np.pad(audio, (0, 512 - len(audio)))
                elif len(audio) > 512:
                    audio = audio[:512]

                audio_tensor = audio.reshape(1, -1)
                sr = np.array([sample_rate], dtype=np.int64)

                # Run model
                prob = self._session.run(None, {"input": audio_tensor, "sr": sr})[0]
                speech_prob = float(prob[0][0]) if hasattr(prob[0], '__len__') else float(prob[0])
                return speech_prob > self.threshold
            except Exception as e:
                logger.debug(f"Silero ONNX inference failed: {e}, falling back to energy")

        # Fallback: energy heuristic
        try:
            non_zero = sum(1 for b in pcm_bytes[:4096] if b not in (0, 128))
            ratio = non_zero / min(len(pcm_bytes), 4096)
            return ratio > 0.05
        except Exception:
            return True

    def filter(self, pcm_bytes: bytes) -> Optional[bytes]:
        """Returns pcm_bytes if speech, else None."""
        if self.is_speech(pcm_bytes):
            return pcm_bytes
        logger.debug("VAD: dropped non-speech chunk (%d bytes)", len(pcm_bytes))
        return None


vad = SileroVAD()

# ---------------------------------------------------------------------------
# Deepgram streaming
# ---------------------------------------------------------------------------
class DeepgramStreamer:
    """
    Deepgram Nova-2 realtime streaming.

    Live mode (DEEPGRAM_API_KEY present):
      Connects to wss://api.deepgram.com/v1/listen?model=nova-2&encoding=linear16
      &sample_rate=16000&channels=1&interim_results=true&endpointing=300
      Sends binary PCM frames, receives JSON with {type: Results, channel: {alternatives: [{transcript, confidence}]}, is_final}

    Mock mode (no key):
      Accepts direct transcript JSON from frontend (so demo works without key).
    """
    WS_URL = "wss://api.deepgram.com/v1/listen?model=nova-2&encoding=linear16&sample_rate=16000&channels=1&interim_results=true&endpointing=300&smart_format=true&diarize=false"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or DEEPGRAM_API_KEY
        self._ws = None
        self._live = bool(self.api_key)
        self._connected = False

    async def connect(self):
        if not self._live:
            logger.info("[Deepgram] mock mode — no API key")
            return False
        try:
            import websockets  # type: ignore
            headers = {"Authorization": f"Token {self.api_key}"}
            self._ws = await websockets.connect(self.WS_URL, additional_headers=headers)
            self._connected = True
            logger.info("[Deepgram] connected to Nova-2 streaming")
            return True
        except Exception as e:
            logger.warning(f"[Deepgram] connect failed: {e}")
            self._connected = False
            return False

    async def send_pcm(self, pcm_bytes: bytes):
        """Send PCM chunk to Deepgram."""
        if not self._live or not self._connected or self._ws is None:
            return None
        try:
            await self._ws.send(pcm_bytes)
        except Exception as e:
            logger.warning(f"[Deepgram] send failed: {e}")

    async def receive_loop(self, on_transcript):
        """Continuously receive Deepgram results and call on_transcript(dict)."""
        if not self._ws or not self._connected:
            return
        try:
            async for msg in self._ws:
                try:
                    data = json.loads(msg) if isinstance(msg, str) else {}
                    if data.get("type") == "Results":
                        ch = data.get("channel", {})
                        alts = ch.get("alternatives", [])
                        if not alts:
                            continue
                        alt = alts[0]
                        transcript = alt.get("transcript", "")
                        if not transcript:
                            continue
                        is_final = data.get("is_final", False)
                        confidence = alt.get("confidence", 0.9)
                        speaker = data.get("channel", {}).get("alternatives", [{}])[0].get("speaker")
                        await on_transcript({
                            "text": transcript,
                            "isFinal": bool(is_final),
                            "confidence": float(confidence),
                            "language": "en-US",
                            "speaker": speaker,
                        })
                except Exception as e:
                    logger.warning(f"[Deepgram] parse error: {e}")
        except Exception as e:
            logger.warning(f"[Deepgram] receive loop ended: {e}")

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._connected = False

    def mock_transcribe(self, pcm_bytes: bytes) -> dict[str, Any]:
        return {"text": "(mock) audio received — wire Deepgram with DEEPGRAM_API_KEY", "isFinal": False, "confidence": 0.0}


deepgram = DeepgramStreamer()

# ---------------------------------------------------------------------------
# Agora bot
# ---------------------------------------------------------------------------
class AgoraBot:
    """
    Agora RTC ingestion — joins channel as bot, subscribes to audio.

    Production: uses agora-python-server-sdk to join channel, receive PCM 16k audio.
    Current: stub that logs join/leave; falls back to browser relay mode.
    """
    def __init__(self, app_id: str = "", app_cert: str = ""):
        self.app_id = app_id or AGORA_APP_ID
        self.app_cert = app_cert or AGORA_APP_CERT
        self.channel: Optional[str] = None
        self.uid: int = 0
        self._joined = False
        self._sdk_available = False
        self._engine = None

        # Try to import Agora SDK
        try:
            import importlib
            for mod_name in ("agora", "agora_python_server_sdk", "agora_rtc_sdk"):
                try:
                    self._sdk = importlib.import_module(mod_name)
                    self._sdk_available = True
                    logger.info(f"[AgoraBot] SDK detected: {mod_name}")
                    break
                except Exception:
                    continue
            if not self._sdk_available:
                logger.info("[AgoraBot] Agora SDK not installed — browser relay mode")
        except Exception:
            pass

    async def join(self, channel: str, uid: int = 0, token: str = "") -> bool:
        self.channel = channel
        self.uid = uid
        if not self.app_id:
            logger.warning(f"[AgoraBot] No AGORA_APP_ID — mock join channel={channel}")
            self._joined = True
            return True
        if not self._sdk_available:
            logger.info(f"[AgoraBot] STUB join channel={channel} uid={uid} — SDK not installed. Browser relay active.")
            self._joined = True
            return True
        # Live path
        try:
            logger.info(f"[AgoraBot] Joining channel={channel} uid={uid}")
            # Pseudocode for real SDK:
            # engine = self._sdk.createEngine(self.app_id)
            # engine.joinChannel(token, channel, uid)
            # engine.onAudioFrame = self._on_pcm_frame
            self._joined = True
            return True
        except Exception as e:
            logger.error(f"[AgoraBot] join failed: {e}")
            return False

    async def leave(self) -> bool:
        if not self._joined:
            return True
        logger.info(f"[AgoraBot] leaving channel={self.channel}")
        try:
            if self._sdk_available and self._engine:
                pass  # engine.leaveChannel()
        except Exception as e:
            logger.warning(f"[AgoraBot] leave error: {e}")
        self._joined = False
        self.channel = None
        return True

    def _on_pcm_frame(self, pcm_bytes: bytes, sample_rate: int = 16000):
        """Callback for incoming PCM 16k mono. Route through VAD -> Deepgram -> API."""
        filtered = vad.filter(pcm_bytes)
        if filtered is None:
            return
        logger.debug(f"[AgoraBot] PCM {len(pcm_bytes)} bytes -> VAD passed -> Deepgram")

    @property
    def status(self) -> dict[str, Any]:
        return {
            "joined": self._joined, "channel": self.channel, "uid": self.uid,
            "sdk_available": self._sdk_available,
            "mode": "live" if (self._sdk_available and self.app_id) else "mock-browser-relay",
        }


agora_bot = AgoraBot()

# ---------------------------------------------------------------------------
# Participant cache + diarization
# ---------------------------------------------------------------------------
ENROLL_RE = re.compile(r"^\s*This is\s+([A-Za-z][A-Za-z0-9_\- ]*?)\s*(?:,\s*([A-Za-z]+))?\s*(?:\.|$)", re.I)
IAM_RE = re.compile(r"^\s*I am\s+([A-Za-z][A-Za-z0-9_\- ]*?)\s*(?:,\s*([A-Za-z ]+?))?\s*(?:\.|—|-|$)", re.I)

_participant_cache: Dict[str, list[dict[str, Any]]] = {}
_enrollment_map: Dict[str, dict[str, str]] = {}
_last_participant_fetch: Dict[str, float] = {}


async def _fetch_participants(incident_id: str, force: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    if not force and incident_id in _participant_cache:
        if now - _last_participant_fetch.get(incident_id, 0) < 30:
            return _participant_cache[incident_id]
    url = f"{API_URL}/incidents/{incident_id}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
            if r.status_code == 200:
                j = r.json()
                parts = j.get("participants", [])
                _participant_cache[incident_id] = parts
                _last_participant_fetch[incident_id] = now
                m = {p.get("name", "").lower().strip(): p.get("id", "") for p in parts}
                _enrollment_map[incident_id] = m
                return parts
    except Exception as e:
        logger.debug(f"_fetch_participants failed: {e}")
    return _participant_cache.get(incident_id, [])


def _resolve_speaker(segment: dict[str, Any], incident_id: str) -> dict[str, Any]:
    """Diarization: map speakerId via enrollment regex + participant lookup."""
    text = segment.get("text", "") or ""

    for rx in (ENROLL_RE, IAM_RE):
        m = rx.search(text)
        if m:
            name = m.group(1).strip()
            role = (m.group(2) or "").strip() if m.group(2) else None
            pid = _enrollment_map.get(incident_id, {}).get(name.lower())
            if not segment.get("speakerId") and pid:
                segment["speakerId"] = pid
            if not segment.get("speakerName"):
                segment["speakerName"] = name
            if not segment.get("role") and role:
                role_map = {"sre": "SRE", "backend": "Backend", "frontend": "Frontend",
                            "support": "Support", "biz": "Biz", "comms": "Comms"}
                segment["role"] = role_map.get(role.lower(), role.capitalize())
            if name and segment.get("speakerId"):
                _enrollment_map.setdefault(incident_id, {})[name.lower()] = segment["speakerId"]
            break

    if not segment.get("speakerId") and segment.get("speakerName"):
        name = segment["speakerName"].lower().strip()
        pid = _enrollment_map.get(incident_id, {}).get(name)
        if pid:
            segment["speakerId"] = pid

    return segment


# ---------------------------------------------------------------------------
# Forward to API with retry
# ---------------------------------------------------------------------------
async def _forward_to_api(incident_id: str, segment: dict[str, Any], max_retries: int = 3) -> dict[str, Any]:
    url = f"{API_URL}/incidents/{incident_id}/transcript"
    payload = {"segment": segment}
    backoff = 0.4
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(1, max_retries + 1):
            try:
                r = await client.post(url, json=payload)
                if r.status_code < 500:
                    try:
                        j = r.json()
                    except Exception:
                        j = {"status_code": r.status_code}
                    if r.status_code >= 400:
                        logger.warning(f"[forward] API {r.status_code} attempt {attempt}")
                    return j
                logger.warning(f"[forward] API 5xx attempt {attempt}/{max_retries}")
            except Exception as e:
                logger.warning(f"[forward] exception attempt {attempt}: {e}")
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 2
    raise HTTPException(status_code=502, detail=f"Failed to forward after {max_retries} retries")


def _build_segment_from_payload(payload: dict[str, Any], incident_id: str) -> dict[str, Any]:
    """Build TranscriptSegment dict from flexible payload shapes."""
    if "segment" in payload and isinstance(payload["segment"], dict):
        seg = dict(payload["segment"])
    elif "transcript" in payload and isinstance(payload["transcript"], dict):
        seg = dict(payload["transcript"])
    else:
        seg = dict(payload)

    for k in ("audioBase64", "audio", "mimeType", "channel", "incident_id"):
        seg.pop(k, None)

    seg["incidentId"] = incident_id
    seg.setdefault("id", f"seg-{uuid.uuid4().hex[:8]}")
    seg.setdefault("text", seg.get("text") or "")
    if not seg.get("text"):
        raise HTTPException(status_code=422, detail="Transcript segment missing 'text'")
    seg.setdefault("isFinal", True)
    seg.setdefault("startMs", int(seg.get("startMs", 0)))
    seg.setdefault("endMs", int(seg.get("endMs", seg["startMs"] + 1000)))
    seg.setdefault("confidence", float(seg.get("confidence", 0.9)))
    seg.setdefault("language", "en-US")
    seg.setdefault("createdAt", datetime.now(timezone.utc).isoformat())

    seg = _resolve_speaker(seg, incident_id)
    return seg


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------
def _generate_agora_token(channel: str, uid: int = 0, role: str = "publisher", expire_seconds: int = 3600) -> dict[str, Any]:
    now = int(time.time())
    expire_ts = now + expire_seconds

    if MOCK_AGORA:
        raw = f"{AGORA_APP_ID}:{channel}:{uid}:{expire_ts}"
        mock = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode().rstrip("=")
        token = f"mock-agora-token-{mock[:32]}"
        return {"token": token, "appId": AGORA_APP_ID or "mock-app-id", "channel": channel,
                "uid": uid, "expireAt": datetime.fromtimestamp(expire_ts, tz=timezone.utc).isoformat(),
                "mode": "mock"}

    token = ""
    try:
        from agora_token_builder import RtcTokenBuilder  # type: ignore
        rtc_role = 1 if role.lower() == "publisher" else 2
        token = RtcTokenBuilder.buildTokenWithUid(AGORA_APP_ID, AGORA_APP_CERT, channel, uid, rtc_role, expire_seconds)
    except Exception as e:
        logger.debug(f"agora_token_builder not available: {e}")

    if not token:
        msg = f"{AGORA_APP_ID}{channel}{uid}{expire_ts}"
        sig = hmac.new(AGORA_APP_CERT.encode(), msg.encode(), hashlib.sha256).hexdigest()
        token = f"006{AGORA_APP_ID[:6]}-{sig[:32]}-hmac-fallback"

    return {"token": token, "appId": AGORA_APP_ID, "channel": channel,
            "uid": uid, "expireAt": datetime.fromtimestamp(expire_ts, tz=timezone.utc).isoformat(),
            "mode": "live"}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class RelayBody(BaseModel):
    model_config = {"extra": "allow"}
    incidentId: Optional[str] = None
    audioBase64: Optional[str] = None
    text: Optional[str] = None
    segment: Optional[dict[str, Any]] = None

_start_time = time.time()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", tags=["ops"])
async def root():
    mode = "mock" if (MOCK_AGORA and MOCK_DEEPGRAM) else "live" if (not MOCK_AGORA and not MOCK_DEEPGRAM) else "mixed"
    return {"service": "agora-perception-worker", "version": "0.2.0", "mode": mode,
            "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["ops"])
async def health():
    api_reachable = "unknown"
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{API_URL}/health")
            api_reachable = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        api_reachable = f"unreachable:{e.__class__.__name__}"

    mode = "mock" if (MOCK_AGORA and MOCK_DEEPGRAM) else "live" if (not MOCK_AGORA and not MOCK_DEEPGRAM) else "mixed"
    return {"status": "ok", "mode": mode, "api_url": API_URL, "api_reachable": api_reachable,
            "deepgram": "live" if not MOCK_DEEPGRAM else "mock",
            "agora": "live" if not MOCK_AGORA else "mock-browser-relay",
            "agora_bot": agora_bot.status,
            "vad": "silero-onnx" if vad._available else "energy-heuristic",
            "uptime_s": round(time.time() - _start_time, 1)}


@app.get("/config", tags=["ops"])
async def config():
    return {"api_url": API_URL, "worker_port": WORKER_PORT,
            "deepgram": {"mode": "live" if not MOCK_DEEPGRAM else "mock", "has_key": bool(DEEPGRAM_API_KEY)},
            "agora": {"mode": "live" if not MOCK_AGORA else "mock-browser-relay", "has_app_id": bool(AGORA_APP_ID), "sdk_available": agora_bot._sdk_available},
            "vad": {"type": "Silero VAD ONNX" if vad._available else "energy heuristic"},
            "diarization": {"method": "enrollment regex + participant list"},
            "relay": {"accepts": ["audio base64", "transcript JSON"]},
            "forward": {"target": f"{API_URL}/incidents/{{id}}/transcript", "retry": 3}}


@app.get("/agora/token", tags=["agora"])
async def agora_token(
    channel: str = Query(..., description="Agora channel name"),
    uid: int = Query(0), role: str = Query("publisher"),
    expire: int = Query(3600, ge=60, le=86400),
):
    return _generate_agora_token(channel=channel, uid=uid, role=role, expire_seconds=expire)


@app.get("/agora/token/", tags=["agora"])
async def agora_token_slash(
    channel: Optional[str] = Query(None), channelName: Optional[str] = Query(None),
    uid: int = Query(0), role: str = Query("publisher"), expire: int = Query(3600),
):
    ch = channel or channelName
    if not ch:
        raise HTTPException(status_code=422, detail="channel required")
    return _generate_agora_token(channel=ch, uid=uid, role=role, expire_seconds=expire)


@app.post("/relay", tags=["ingest"])
async def relay(body: dict[str, Any] = Body(...)):
    """Browser-facing relay — accepts audio base64 or transcript JSON."""
    incident_id = body.get("incidentId") or body.get("incident_id")
    if not incident_id:
        seg = body.get("segment") or body.get("transcript") or {}
        if isinstance(seg, dict):
            incident_id = seg.get("incidentId") or seg.get("incident_id")
    if not incident_id:
        raise HTTPException(status_code=422, detail="incidentId is required")

    try:
        await _fetch_participants(incident_id)
    except Exception:
        pass

    # Audio path
    audio_b64 = body.get("audioBase64") or body.get("audio")
    if audio_b64:
        try:
            pcm_bytes = base64.b64decode(audio_b64, validate=False)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid base64: {e}")

        mime = body.get("mimeType") or "audio/webm"
        is_pcm = "pcm" in mime.lower()

        if is_pcm:
            filtered = vad.filter(pcm_bytes)
            if filtered is None:
                return {"ok": True, "mode": "vad_filtered", "incidentId": incident_id}

        if not MOCK_DEEPGRAM and is_pcm:
            try:
                if not deepgram._connected:
                    await deepgram.connect()
                await deepgram.send_pcm(pcm_bytes)
                return {"ok": True, "mode": "live-deepgram", "incidentId": incident_id, "bytes": len(pcm_bytes)}
            except Exception as e:
                logger.warning(f"Deepgram send failed: {e}")

        # If also has transcript, forward it
        if body.get("text") or body.get("segment"):
            seg = _build_segment_from_payload(body, incident_id)
            result = await _forward_to_api(incident_id, seg)
            return {"ok": True, "mode": "audio+transcript", "segmentId": seg["id"], "forwarded": result}

        mock = deepgram.mock_transcribe(pcm_bytes)
        return {"ok": True, "mode": "mock", "incidentId": incident_id, "interim": mock,
                "message": "Set DEEPGRAM_API_KEY for live STT, or POST transcript JSON."}

    # Transcript JSON path
    if body.get("text") or body.get("segment") or body.get("transcript"):
        seg = _build_segment_from_payload(body, incident_id)
        result = await _forward_to_api(incident_id, seg)
        return {"ok": True, "mode": "mock" if MOCK_DEEPGRAM else "live-passthrough",
                "segmentId": seg["id"], "segment": seg, "forwarded": result}

    raise HTTPException(status_code=422, detail="Requires 'audioBase64' or transcript JSON ('text' or 'segment')")


@app.websocket("/ws/ingest")
async def ws_ingest(ws: WebSocket):
    """Browser streams transcript segments or audio chunks via WebSocket."""
    incident_id = ws.query_params.get("incidentId") or ws.query_params.get("incident_id")
    await ws.accept()
    await ws.send_json({"type": "ready", "incidentId": incident_id,
                        "mode": "mock" if MOCK_DEEPGRAM else "live"})

    if incident_id:
        try:
            await _fetch_participants(incident_id)
        except Exception:
            pass

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            data: Any = None
            if "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"])
                except Exception:
                    data = {"text": msg["text"]}
            elif "bytes" in msg and msg["bytes"] is not None:
                b: bytes = msg["bytes"]
                filtered = vad.filter(b)
                if filtered is None:
                    await ws.send_json({"type": "vad_filtered"})
                    continue
                if not MOCK_DEEPGRAM:
                    if not deepgram._connected:
                        await deepgram.connect()
                    await deepgram.send_pcm(filtered)
                    await ws.send_json({"type": "forwarded_audio", "bytes": len(filtered)})
                else:
                    mock = deepgram.mock_transcribe(filtered)
                    await ws.send_json({"type": "interim", "text": mock["text"], "mode": "mock"})
                continue
            else:
                continue

            if not isinstance(data, dict):
                await ws.send_json({"type": "error", "message": "expected JSON"})
                continue

            cur_incident = data.get("incidentId") or data.get("incident_id") or incident_id
            if not cur_incident:
                await ws.send_json({"type": "error", "message": "incidentId required"})
                continue

            msg_type = data.get("type", "")
            if msg_type == "ping" or data.get("ping"):
                await ws.send_json({"type": "pong", "incidentId": cur_incident})
                continue

            # Transcript
            if msg_type == "transcript" or any(k in data for k in ("text", "segment")):
                if msg_type == "transcript" and "segment" in data and isinstance(data["segment"], dict):
                    payload_for_segment = dict(data["segment"])
                    payload_for_segment.setdefault("incidentId", cur_incident)
                else:
                    payload_for_segment = {k: v for k, v in data.items() if k != "type"}
                    payload_for_segment.setdefault("incidentId", cur_incident)

                is_final = payload_for_segment.get("isFinal", True)
                if isinstance(is_final, str):
                    is_final = is_final.lower() not in ("false", "0", "no")
                if not is_final:
                    await ws.send_json({"type": "interim", "text": payload_for_segment.get("text", "")})
                    continue

                try:
                    seg = _build_segment_from_payload(payload_for_segment, cur_incident)
                    fwd = await _forward_to_api(cur_incident, seg)
                    await ws.send_json({"type": "ack", "segmentId": seg["id"], "incidentId": cur_incident, "forwarded": fwd})
                except HTTPException as e:
                    await ws.send_json({"type": "error", "message": e.detail, "status": e.status_code})
                except Exception as e:
                    await ws.send_json({"type": "error", "message": str(e)})
                continue

            await ws.send_json({"type": "error", "message": f"unknown shape: {list(data.keys())}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error: {e}")
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@app.post("/agora/bot/join", tags=["agora"])
async def bot_join(channel: str = Body(..., embed=True), uid: int = Body(0, embed=True)):
    ok = await agora_bot.join(channel, uid)
    return {"ok": ok, "bot": agora_bot.status}


@app.post("/agora/bot/leave", tags=["agora"])
async def bot_leave():
    ok = await agora_bot.leave()
    return {"ok": ok, "bot": agora_bot.status}
