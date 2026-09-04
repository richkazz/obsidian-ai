import json
import os
import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import DATABASE_TYPE
from database import get_db
from models import WhatsAppChannel, WAContactSession, Session as ChatSession, Agent
from auth import get_current_user, TokenData, bearer_scheme, decode_token

if DATABASE_TYPE == "mongo":
    from database_mongo import get_database
    from models_mongo import WhatsAppChannelCollection, WAContactSessionCollection, SessionCollection, AgentCollection

router = APIRouter(prefix="/wa", tags=["whatsapp"])

# URL of the Baileys sidecar (configurable via env)
SIDECAR_URL = os.environ.get("WA_SIDECAR_URL", "http://localhost:3200")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class WAChannelCreate(BaseModel):
    name: str
    agent_id: int | str


class WAChannelUpdate(BaseModel):
    name: Optional[str] = None
    agent_id: Optional[int | str] = None
    allowed_jids: Optional[list[str]] = None  # None = no change; [] = allow all
    reject_message: Optional[str] = None
    voice_reply_enabled: Optional[bool] = None
    voice_reply_jids: Optional[list[str]] = None  # None = no change; [] = all contacts
    voice_reply_voice: Optional[str] = None       # Qwen preset (Ryan/Aiden/…) or pocket voice
    tts_backend: Optional[str] = None             # "auto" | "qwen" | "classic"
    voice_clone_ref_text: Optional[str] = None    # transcript for voice cloning


class WAIncomingMessage(BaseModel):
    channel_id: int | str
    wa_chat_id: str   # JID of the conversation
    wa_sender: str    # JID of the actual sender (differs from wa_chat_id in groups)
    wa_lid: Optional[str] = None  # Raw @lid JID if sender was resolved from lid
    message_text: str
    is_group: bool = False
    wa_group_name: Optional[str] = None  # Display name of the group (groups only)
    sender_name: Optional[str] = None     # WhatsApp push name of the sender
    wa_message_ids: Optional[list[str]] = None  # WA key.id of each buffered message (for quoting)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _channel_dict(ch) -> dict:
    """Serialize a SQLAlchemy WhatsAppChannel to a dict."""
    return {
        "id": ch.id,
        "user_id": ch.user_id,
        "agent_id": ch.agent_id,
        "name": ch.name,
        "wa_phone": ch.wa_phone,
        "status": ch.status,
        "allowed_jids": json.loads(ch.allowed_jids) if ch.allowed_jids else None,
        "reject_message": ch.reject_message,
        "voice_reply_enabled": getattr(ch, "voice_reply_enabled", False) or False,
        "voice_reply_jids": json.loads(ch.voice_reply_jids) if getattr(ch, "voice_reply_jids", None) else [],
        "voice_reply_voice": getattr(ch, "voice_reply_voice", None) or "Ryan",
        "tts_backend": getattr(ch, "tts_backend", None) or "auto",
        "voice_clone_audio_path": getattr(ch, "voice_clone_audio_path", None),
        "voice_clone_ref_text": getattr(ch, "voice_clone_ref_text", None),
        "has_voice_clone": bool(getattr(ch, "voice_clone_audio_path", None)),
        "is_active": ch.is_active,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }


def _serialize_mongo_channel(ch: dict) -> dict:
    """Convert a MongoDB channel doc to a JSON-safe dict (ObjectId → str)."""
    return {
        "id": str(ch["_id"]),
        "user_id": str(ch.get("user_id", "")),
        "agent_id": str(ch.get("agent_id", "")),
        "name": ch.get("name", ""),
        "wa_phone": ch.get("wa_phone"),
        "status": ch.get("status", "disconnected"),
        "allowed_jids": ch.get("allowed_jids"),
        "reject_message": ch.get("reject_message"),
        "voice_reply_enabled": ch.get("voice_reply_enabled", False),
        "voice_reply_jids": ch.get("voice_reply_jids") or [],
        "voice_reply_voice": ch.get("voice_reply_voice") or "Ryan",
        "tts_backend": ch.get("tts_backend") or "auto",
        "voice_clone_audio_path": ch.get("voice_clone_audio_path"),
        "voice_clone_ref_text": ch.get("voice_clone_ref_text"),
        "has_voice_clone": bool(ch.get("voice_clone_audio_path")),
        "is_active": ch.get("is_active", True),
        "created_at": ch["created_at"].isoformat() if ch.get("created_at") else None,
        "updated_at": ch["updated_at"].isoformat() if ch.get("updated_at") else None,
    }


async def _get_user_from_token_or_query(
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> TokenData:
    """Auth dependency that accepts Bearer header OR ?token= query param (needed for EventSource)."""
    raw = None
    if credentials:
        raw = credentials.credentials
    elif token:
        raw = token
    if not raw:
        from fastapi import status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(raw)
    return TokenData(
        user_id=payload.get("user_id"),
        username=payload.get("username"),
        role=payload.get("role", "user"),
        token_type="user",
    )


async def _call_sidecar(method: str, path: str, **kwargs) -> dict:
    """Call the Baileys sidecar and return the JSON response."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await getattr(client, method)(f"{SIDECAR_URL}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()


# ── SQLite routes ─────────────────────────────────────────────────────────────

@router.get("/channels")
async def list_channels(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        channels = await WhatsAppChannelCollection.find_by_user(mongo_db, str(current_user.user_id))
        return [_serialize_mongo_channel(ch) for ch in channels]

    channels = db.query(WhatsAppChannel).filter(
        WhatsAppChannel.user_id == current_user.user_id,
        WhatsAppChannel.is_active == True,
    ).all()
    return [_channel_dict(ch) for ch in channels]


@router.post("/channels", status_code=201)
async def create_channel(
    body: WAChannelCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        agent = await AgentCollection.find_by_id(mongo_db, str(body.agent_id))
        if not agent:
            raise HTTPException(404, "Agent not found")
        ch = await WhatsAppChannelCollection.create(mongo_db, {
            "user_id": str(current_user.user_id),
            "agent_id": str(body.agent_id),
            "name": body.name,
            "status": "disconnected",
        })
        return _serialize_mongo_channel(ch)

    agent = db.query(Agent).filter(Agent.id == int(body.agent_id), Agent.user_id == current_user.user_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    auth_path = os.path.join("wa_auth", str(current_user.user_id))
    ch = WhatsAppChannel(
        user_id=current_user.user_id,
        agent_id=int(body.agent_id),
        name=body.name,
        auth_state_path=auth_path,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    # Update auth path to include channel id now we have it
    ch.auth_state_path = os.path.join("wa_auth", str(ch.id))
    db.commit()
    db.refresh(ch)
    return _channel_dict(ch)


@router.get("/channels/{channel_id}")
async def get_channel(
    channel_id: int | str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        ch = await WhatsAppChannelCollection.find_by_id(mongo_db, str(channel_id))
        if not ch or ch.get("user_id") != str(current_user.user_id):
            raise HTTPException(404, "Channel not found")
        return _serialize_mongo_channel(ch)

    ch = db.query(WhatsAppChannel).filter(
        WhatsAppChannel.id == int(channel_id),
        WhatsAppChannel.user_id == current_user.user_id,
        WhatsAppChannel.is_active == True,
    ).first()
    if not ch:
        raise HTTPException(404, "Channel not found")
    return _channel_dict(ch)


@router.patch("/channels/{channel_id}")
async def update_channel(
    channel_id: int | str,
    body: WAChannelUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        updates: dict = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.agent_id is not None:
            updates["agent_id"] = str(body.agent_id)
        if body.allowed_jids is not None:
            updates["allowed_jids"] = body.allowed_jids
        if body.reject_message is not None:
            updates["reject_message"] = body.reject_message
        if body.voice_reply_enabled is not None:
            updates["voice_reply_enabled"] = body.voice_reply_enabled
        if body.voice_reply_jids is not None:
            updates["voice_reply_jids"] = body.voice_reply_jids
        if body.voice_reply_voice is not None:
            updates["voice_reply_voice"] = body.voice_reply_voice
        if body.tts_backend is not None:
            updates["tts_backend"] = body.tts_backend
        if body.voice_clone_ref_text is not None:
            updates["voice_clone_ref_text"] = body.voice_clone_ref_text or None
        ch = await WhatsAppChannelCollection.update(mongo_db, str(channel_id), str(current_user.user_id), updates)
        if not ch:
            raise HTTPException(404, "Channel not found")
        return _serialize_mongo_channel(ch)

    ch = db.query(WhatsAppChannel).filter(
        WhatsAppChannel.id == int(channel_id),
        WhatsAppChannel.user_id == current_user.user_id,
        WhatsAppChannel.is_active == True,
    ).first()
    if not ch:
        raise HTTPException(404, "Channel not found")

    if body.name is not None:
        ch.name = body.name
    if body.agent_id is not None:
        ch.agent_id = int(body.agent_id)
    if body.allowed_jids is not None:
        ch.allowed_jids = json.dumps(body.allowed_jids) if body.allowed_jids else None
    if body.reject_message is not None:
        ch.reject_message = body.reject_message or None
    if body.voice_reply_enabled is not None:
        ch.voice_reply_enabled = body.voice_reply_enabled
    if body.voice_reply_jids is not None:
        ch.voice_reply_jids = json.dumps(body.voice_reply_jids) if body.voice_reply_jids else None
    if body.voice_reply_voice is not None:
        ch.voice_reply_voice = body.voice_reply_voice or "Ryan"
    if body.tts_backend is not None:
        ch.tts_backend = body.tts_backend or "auto"
    if body.voice_clone_ref_text is not None:
        ch.voice_clone_ref_text = body.voice_clone_ref_text or None
    db.commit()
    db.refresh(ch)
    return _channel_dict(ch)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: int | str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        deleted = await WhatsAppChannelCollection.delete(mongo_db, str(channel_id), str(current_user.user_id))
        if not deleted:
            raise HTTPException(404, "Channel not found")
        return

    ch = db.query(WhatsAppChannel).filter(
        WhatsAppChannel.id == int(channel_id),
        WhatsAppChannel.user_id == current_user.user_id,
    ).first()
    if not ch:
        raise HTTPException(404, "Channel not found")

    # Tell sidecar to disconnect before deleting
    try:
        await _call_sidecar("post", f"/channels/{channel_id}/stop")
    except Exception:
        pass

    ch.is_active = False
    db.commit()


@router.post("/channels/{channel_id}/connect")
async def connect_channel(
    channel_id: int | str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tell the Baileys sidecar to start the WA socket for this channel."""
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        ch = await WhatsAppChannelCollection.find_by_id(mongo_db, str(channel_id))
        if not ch or ch.get("user_id") != str(current_user.user_id):
            raise HTTPException(404, "Channel not found")
        auth_path = ch.get("auth_state_path") or f"wa_auth/{channel_id}"
    else:
        ch = db.query(WhatsAppChannel).filter(
            WhatsAppChannel.id == int(channel_id),
            WhatsAppChannel.user_id == current_user.user_id,
            WhatsAppChannel.is_active == True,
        ).first()
        if not ch:
            raise HTTPException(404, "Channel not found")
        auth_path = ch.auth_state_path or f"wa_auth/{channel_id}"

    try:
        result = await _call_sidecar("post", f"/channels/{channel_id}/start", json={"auth_path": auth_path})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Sidecar error: {e}")

    # Mark as pending_qr
    if DATABASE_TYPE == "mongo":
        await WhatsAppChannelCollection.update(mongo_db, str(channel_id), str(current_user.user_id), {"status": "pending_qr"})
    else:
        ch.status = "pending_qr"
        db.commit()

    return {"status": "pending_qr", "message": "Scan the QR code at /wa/channels/{id}/qr"}


@router.post("/channels/{channel_id}/disconnect")
async def disconnect_channel(
    channel_id: int | str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        ch = await WhatsAppChannelCollection.find_by_id(mongo_db, str(channel_id))
        if not ch or ch.get("user_id") != str(current_user.user_id):
            raise HTTPException(404, "Channel not found")
    else:
        ch = db.query(WhatsAppChannel).filter(
            WhatsAppChannel.id == int(channel_id),
            WhatsAppChannel.user_id == current_user.user_id,
            WhatsAppChannel.is_active == True,
        ).first()
        if not ch:
            raise HTTPException(404, "Channel not found")

    try:
        await _call_sidecar("post", f"/channels/{channel_id}/stop")
    except Exception:
        pass

    if DATABASE_TYPE == "mongo":
        await WhatsAppChannelCollection.update(mongo_db, str(channel_id), str(current_user.user_id), {"status": "disconnected"})
    else:
        ch.status = "disconnected"
        db.commit()

    return {"status": "disconnected"}


@router.get("/channels/{channel_id}/qr")
async def stream_qr(
    channel_id: int | str,
    current_user: TokenData = Depends(_get_user_from_token_or_query),
    db: Session = Depends(get_db),
):
    """SSE proxy: streams QR code events from the Baileys sidecar to the frontend."""
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        ch = await WhatsAppChannelCollection.find_by_id(mongo_db, str(channel_id))
        if not ch or ch.get("user_id") != str(current_user.user_id):
            raise HTTPException(404, "Channel not found")
    else:
        ch = db.query(WhatsAppChannel).filter(
            WhatsAppChannel.id == int(channel_id),
            WhatsAppChannel.user_id == current_user.user_id,
            WhatsAppChannel.is_active == True,
        ).first()
        if not ch:
            raise HTTPException(404, "Channel not found")

    async def event_generator():
        try:
            # No read timeout: this stream stays open and idle while the user
            # scans the QR code, which can take well over 2 minutes.
            timeout = httpx.Timeout(connect=10, read=None, write=10, pool=10)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", f"{SIDECAR_URL}/channels/{channel_id}/events") as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            yield f"{line}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/channels/{channel_id}/status")
async def update_channel_status(
    channel_id: int | str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Called internally by the Baileys sidecar to update channel status/phone.
    No user auth — sidecar is localhost-only.
    """
    body = await request.json()
    status = body.get("status")
    wa_phone = body.get("wa_phone")

    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        updates: dict = {}
        if status:
            updates["status"] = status
        if wa_phone:
            updates["wa_phone"] = wa_phone
        if updates:
            # Update without user_id constraint (sidecar call)
            collection = mongo_db["whatsapp_channels"]
            from bson import ObjectId
            updates["updated_at"] = datetime.now(timezone.utc)
            await collection.update_one({"_id": ObjectId(str(channel_id))}, {"$set": updates})
        return {"ok": True}

    ch = db.query(WhatsAppChannel).filter(WhatsAppChannel.id == int(channel_id)).first()
    if not ch:
        raise HTTPException(404, "Channel not found")
    if status:
        ch.status = status
    if wa_phone:
        ch.wa_phone = wa_phone
    db.commit()
    return {"ok": True}


# VOICE_SAMPLES_DIR = os.environ.get("VOICE_SAMPLES_DIR", "voice_samples")

# Audio processing & voice sample handlers disabled to keep backend lighter for now.

@router.get("/channels/{channel_id}/voice-script")
async def get_voice_script(
    channel_id: int | str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(501, "Voice script generation is currently disabled.")


@router.post("/channels/{channel_id}/voice-sample")
async def upload_voice_sample(
    channel_id: int | str,
    file: UploadFile = File(...),
    ref_text: Optional[str] = Form(None),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(501, "Voice sample uploading is currently disabled.")


@router.delete("/channels/{channel_id}/voice-sample")
async def delete_voice_sample(
    channel_id: int | str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(501, "Voice sample management is currently disabled.")


@router.post("/transcribe")
async def transcribe_audio(request: Request):
    """
    Called by the Baileys sidecar to transcribe a WhatsApp voice note.
    Receives multipart/form-data with field 'file', returns {"text": "..."}.
    No user auth — sidecar is localhost-only.
    All processing is routed via Groq Whisper API (stt_service).
    Degrades gracefully with a friendly user prompt on timeout or corrupted audio.
    """
    form = await request.form()
    upload = form.get("file")
    if not upload:
        raise HTTPException(400, "No file field in form data")

    audio_bytes = await upload.read()
    filename = getattr(upload, "filename", "voice.ogg") or "voice.ogg"
    await upload.close()

    try:
        from services.stt_service import transcribe_audio as groq_transcribe
        text = await groq_transcribe(audio_bytes, filename=filename)
        if not text:
            return {"text": "[Voice Note Error: Unable to transcribe audio. Please send a text message instead.]"}
        return {"text": text}
    except Exception as e:
        return {"text": "[Voice Note Error: Unable to transcribe audio. Please send a text message instead.]"}


@router.post("/incoming")
async def incoming_message(body: WAIncomingMessage):
    """
    Called by the Baileys sidecar when a WhatsApp message arrives.
    Returns immediately — message is buffered and processed asynchronously.
    No user auth — sidecar is localhost-only.
    """
    from services.whatsapp_service import handle_incoming_message
    asyncio.ensure_future(handle_incoming_message(body.dict(), None))
    return {"status": "ok"}
