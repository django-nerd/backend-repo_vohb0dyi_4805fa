import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from database import db, create_document, get_documents

app = FastAPI(title="Spiritual Guru Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    conversation_id: Optional[str] = None
    guru_id: str
    user_message: str
    user_name: Optional[str] = None

class AskResponse(BaseModel):
    conversation_id: str
    reply: str

# A tiny, offline rules-based "AI" to avoid external dependencies.
# In a real system, this could call an LLM provider. For now we craft
# thoughtful, safe responses based on archetype and message.

def generate_guru_reply(archetype: str, user_message: str) -> str:
    msg = user_message.strip()
    a = archetype.lower()
    preface = {
        "zen": "Zen Reflection:",
        "yogi": "Yogic Guidance:",
        "astrologer": "Astrological Insight:",
        "monk": "Monastic Wisdom:",
        "sufi": "Sufi Whisper:",
    }
    opening = preface.get(a, "Guidance:")

    if not msg:
        core = "Silence can be a teacher. Breathe, observe, and allow the next question to arise naturally."
    elif any(w in msg.lower() for w in ["stress", "anxious", "anxiety", "overwhelmed"]):
        core = (
            "Place a hand on your heart. Inhale for 4, hold for 4, exhale for 6."
            " Notice one thing you can see, hear, and feel. Your mind will follow your breath."
        )
    elif any(w in msg.lower() for w in ["purpose", "meaning", "direction"]):
        core = (
            "Purpose unfolds in small, honest steps. Name one value you refuse to abandon;"
            " take one action today that honors it."
        )
    elif any(w in msg.lower() for w in ["love", "relationship", "breakup", "heart"]):
        core = (
            "Love matures through presence and boundaries. Speak your needs with kindness;"
            " listen without preparing your defense."
        )
    elif any(w in msg.lower() for w in ["career", "job", "work"]):
        core = (
            "Treat your work as a dojo: show up, practice, reflect. Choose the smallest improvement"
            " you can repeat for 7 days; let results compound."
        )
    else:
        core = (
            "Return to the body: relax the jaw, soften the shoulders. Ask: What is truly needed now?"
            " Let the simple, compassionate response lead your next move."
        )

    tailoring = {
        "zen": " Embrace simplicity—wash the bowl, one mindful action at a time.",
        "yogi": " Align breath and intention; the posture of your day shapes the posture of your mind.",
        "astrologer": " Trust timing; not every seed sprouts in the same season.",
        "monk": " Choose quiet courage. Consistency is a humble miracle.",
        "sufi": " Let love polish the heart; dance gently with what is.",
    }

    return f"{opening} {core}{tailoring.get(a, '')}"

@app.get("/")
def read_root():
    return {"message": "Spiritual Guru Chat API is running"}

@app.get("/api/gurus")
def list_gurus():
    # Provide a few built-in archetypes if DB empty
    defaults = [
        {"name": "Zen Teacher", "archetype": "zen", "avatar": "🪷", "description": "Quiet clarity and koan-like reflections."},
        {"name": "Yogi Guide", "archetype": "yogi", "avatar": "🧘", "description": "Breath, alignment, and daily practice."},
        {"name": "Astrologer", "archetype": "astrologer", "avatar": "✨", "description": "Patterns of time and temperament."},
        {"name": "Monk Mentor", "archetype": "monk", "avatar": "🙏", "description": "Discipline, devotion, and gentle routine."},
        {"name": "Sufi Friend", "archetype": "sufi", "avatar": "🕊️", "description": "Heart-centered presence and poetry."},
    ]

    try:
        docs = get_documents("guru")
        if not docs:
            # seed defaults once for convenience
            for g in defaults:
                try:
                    create_document("guru", g)
                except Exception:
                    pass
            docs = get_documents("guru")
    except Exception:
        # If DB not configured, still return defaults (non-persistent)
        docs = defaults

    # Normalize _id to string if present
    result = []
    for d in docs:
        d2 = {k: v for k, v in d.items() if k != "_id"}
        if "_id" in d:
            d2["id"] = str(d["_id"])
        result.append(d2)
    return {"gurus": result}

@app.post("/api/ask", response_model=AskResponse)
def ask_guru(payload: AskRequest):
    # Resolve guru from DB or return error
    guru = None
    guru_docs = []
    try:
        guru_docs = get_documents("guru", {"$or": [{"archetype": payload.guru_id}, {"_id": payload.guru_id}]})
    except Exception:
        pass

    # If not found via DB, try matching defaults by archetype name
    if not guru_docs:
        for g in [
            {"name": "Zen Teacher", "archetype": "zen"},
            {"name": "Yogi Guide", "archetype": "yogi"},
            {"name": "Astrologer", "archetype": "astrologer"},
            {"name": "Monk Mentor", "archetype": "monk"},
            {"name": "Sufi Friend", "archetype": "sufi"},
        ]:
            if g["archetype"] == payload.guru_id:
                guru = g
                break
    else:
        guru = guru_docs[0]

    if not guru:
        raise HTTPException(status_code=404, detail="Guru not found")

    archetype = guru.get("archetype", "zen")
    reply = generate_guru_reply(archetype, payload.user_message)

    # Persist conversation and messages if DB available
    conv_id = payload.conversation_id
    try:
        if not conv_id:
            conv_id = create_document("conversation", {
                "guru_id": payload.guru_id,
                "user_name": payload.user_name,
                "title": None,
            })
        # store user message
        create_document("message", {
            "conversation_id": conv_id,
            "role": "user",
            "content": payload.user_message,
            "guru_id": payload.guru_id,
        })
        # store guru reply
        create_document("message", {
            "conversation_id": conv_id,
            "role": "guru",
            "content": reply,
            "guru_id": payload.guru_id,
        })
    except Exception:
        # If database not configured, we still return a reply without persistence
        if not conv_id:
            conv_id = "temp-session"

    return AskResponse(conversation_id=str(conv_id), reply=reply)

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
