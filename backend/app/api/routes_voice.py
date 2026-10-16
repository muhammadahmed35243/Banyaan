"""Voice: spoken commands in, agent narration out.

Commands are parsed with simple rules (instant and predictable on stage) instead of an LLM
call; anything that isn't a known command is treated as a new goal, which the LLM handles.
Speech out uses ElevenLabs when ELEVENLABS_API_KEY is set (three agent voices, phrase cache),
otherwise the browser's own speechSynthesis (free) via the `browser` provider."""
import re

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..config import settings

router = APIRouter(prefix="/api/voice")

# ---------- commands ----------

RULES: list[tuple[str, str]] = [  # (intent, regex on the cleaned transcript)
    ("approve", r"^(approve|approved|accept|yes,? approve|go ahead|okay,? approve|منظور)"),
    ("reject", r"^(reject|deny|decline|مسترد)"),
    ("pause", r"^(pause|hold on|wait|روکو)"),
    ("resume", r"^(resume|continue|carry on|جاری)"),
    ("prune", r"^(prune|stop|cancel|kill)"),
    ("status", r"^(status|what'?s happening|what is happening|what is going on|report)"),
    ("explain", r"^(explain|why|what did you find)"),
    ("show_code", r"^(show|open) (me )?(the )?code"),
    ("view", r"^(show|open) (me )?(the )?(map|system map|timeline|tree|agent tree)"),
    ("demo_email", r"^(send|simulate) (a |an )?(test |demo |payment )?(email|bill)"),
]


class CommandIn(BaseModel):
    transcript: str


def parse(transcript: str) -> dict:
    text = transcript.strip()
    clean = re.sub(r"^(hey |ok |okay )?banyan[,!. ]*", "", text, flags=re.I).strip()
    low = clean.lower().rstrip(".!?")
    for intent, rx in RULES:
        m = re.match(rx, low)
        if m:
            rest = clean[m.end():].strip(" ,.:-") or None
            target = None
            if intent == "view":
                target = "map" if "map" in low else "timeline" if "timeline" in low else "tree"
            return {"intent": intent, "target": target, "text": rest}
    return {"intent": "new_goal", "target": None, "text": clean}


@router.post("/command")
async def command(body: CommandIn) -> dict:
    """Turns a transcript into an intent. The browser executes it with the same API calls
    as the buttons, so voice gets no extra power: high-risk approvals still need a click."""
    if not body.transcript.strip():
        raise HTTPException(400, "empty transcript")
    return parse(body.transcript)


# ---------- speech ----------

# Premade ElevenLabs voices (override with ELEVENLABS_VOICE_<ROLE>); one per agent role.
DEFAULT_VOICES = {
    "orchestrator": "21m00Tcm4TlvDq8ikWAM",  # Rachel: calm narrator
    "builder": "TxGEqnHWrfWFTfGW9XjX",  # Josh: upbeat
    "critic": "pNInz6obpgDQGcFmaJgB",  # Adam: deep, stern
    "watcher": "EXAVITQu4vr4xnVDxMaL",  # Sarah: soft
}
_cache: dict[tuple[str, str], bytes] = {}  # phrase cache (per warm instance)


@router.get("/config")
def config() -> dict:
    return {"provider": "elevenlabs" if settings.elevenlabs_api_key else "browser"}


class SpeakIn(BaseModel):
    text: str
    role: str = "orchestrator"


@router.post("/speak")
async def speak(body: SpeakIn) -> Response:
    if not settings.elevenlabs_api_key:
        raise HTTPException(404, "no TTS provider configured; use the browser voice")
    text = body.text.strip()[:300]
    role = body.role if body.role in DEFAULT_VOICES else "orchestrator"
    key = (role, text)
    if key not in _cache:
        voice = getattr(settings, f"elevenlabs_voice_{role}", "") or DEFAULT_VOICES[role]
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                headers={"xi-api-key": settings.elevenlabs_api_key},
                json={"text": text, "model_id": "eleven_flash_v2_5"})
        if r.status_code != 200:
            raise HTTPException(502, f"TTS failed ({r.status_code})")
        if len(_cache) > 200:
            _cache.clear()
        _cache[key] = r.content
    return Response(_cache[key], media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})
