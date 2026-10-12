import asyncio
import html
import json
import os
import random
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# CONFIGURATION — original Fresh Air AI: Ollama llama3.2:1b
# =========================================================

def get_setting(name, default=""):
    """Read Streamlit Secrets first, then environment variables."""
    try:
        value = st.secrets.get(name)
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass
    value = os.getenv(name)
    return str(value) if value not in (None, "") else default


OLLAMA_MODEL = get_setting("OLLAMA_MODEL", "llama3.2:1b").strip() or "llama3.2:1b"
OLLAMA_URL = get_setting("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
SERPAPI_API_KEY = get_setting("SERPAPI_API_KEY")
ELEVENLABS_API_KEY = get_setting("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = get_setting("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
MONGODB_URI = get_setting("MONGODB_URI")
MONGODB_DATABASE = get_setting("MONGODB_DATABASE", "fresh_air")
MONGODB_COLLECTION = get_setting("MONGODB_COLLECTION", "mission_journal")

st.set_page_config(page_title="Fresh Air | Guided Nature Missions", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")

_SESSION_DEFAULTS = {
    "mission": None, "mission_number": 0, "mission_completed": False,
    "current_mission_id": None, "last_inputs": {}, "completed": [],
    "completed_mission_ids": [], "points": 0, "journal": [],
    "destination_results": [], "destination_search_location": "",
    "selected_destination": None, "destination_choice": "No specific destination",
    "ai_model_test": None, "mission_generation_error": None,
    "mission_generation_source": "", "mission_generation_model": OLLAMA_MODEL,
    "mission_used_ai": False, "chat_messages": [], "agent_trace": [],
    "mission_candidates": [], "mission_feedback_saved": False,
}
for _key, _default in _SESSION_DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default.copy() if isinstance(_default, (dict, list)) else _default


def clean_text(value, fallback="", max_length=700):
    if not isinstance(value, str):
        return fallback
    value = " ".join(value.replace("\x00", "").split()).strip()
    return value[:max_length] if value else fallback


def ollama_endpoint(path="/api/generate"):
    base = OLLAMA_URL
    if base.lower() in {"false", "true", "none", "null", "0", "1", ""}:
        raise ValueError("OLLAMA_URL is missing or invalid. Set it to the base URL of a reachable Ollama server.")
    if not base.startswith(("http://", "https://")):
        raise ValueError("OLLAMA_URL must begin with http:// or https://.")
    if base.endswith("/api/generate"):
        base = base[:-len("/api/generate")]
    if base.endswith("/api/show"):
        base = base[:-len("/api/show")]
    return base.rstrip("/") + path


def call_original_ai(prompt, *, temperature=0.65, timeout=120, json_mode=False, max_tokens=400):
    """Call the original Ollama mission AI with bounded output and a realistic read timeout."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            # llama3.2:1b is intentionally kept concise: it runs on the user's laptop
            # through a tunnel, so long generations can exceed Render's request window.
            "num_predict": max(64, min(int(max_tokens), 700)),
        },
    }
    if json_mode:
        payload["format"] = "json"
    response = requests.post(ollama_endpoint("/api/generate"), json=payload, timeout=(8, timeout))
    response.raise_for_status()
    data = response.json()
    answer = data.get("response", "") if isinstance(data, dict) else ""
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Ollama returned an empty response.")
    return answer.strip()


def parse_json_object(raw):
    """Parse JSON robustly, including models that accidentally add code fences."""
    raw = str(raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(raw[start:end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError("AI response did not contain a valid JSON object.")


# =========================================================
# OPTIONAL PERSISTENT JOURNAL (MongoDB); session-only fallback
# =========================================================

@st.cache_resource(show_spinner=False)
def get_mongo_collection():
    if not MONGODB_URI:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)
        client.admin.command("ping")
        return client[MONGODB_DATABASE][MONGODB_COLLECTION]
    except Exception:
        return None


def get_user_key():
    """A browser-session identifier, not an identity verification mechanism."""
    if not st.session_state.get("journal_user_key"):
        st.session_state.journal_user_key = str(uuid.uuid4())
    return st.session_state.journal_user_key


def load_journal():
    local = st.session_state.get("journal", [])
    collection = get_mongo_collection()
    if collection is None:
        return local
    try:
        docs = list(collection.find({"session_key": get_user_key()}).sort("completed_at", -1).limit(100))
        if docs:
            for doc in docs:
                doc.pop("_id", None)
                if isinstance(doc.get("completed_at"), datetime) and doc["completed_at"].tzinfo is None:
                    doc["completed_at"] = doc["completed_at"].replace(tzinfo=timezone.utc)
            st.session_state.journal = docs
            return docs
    except Exception:
        pass
    return local


def save_completed_mission(mission_id, mission, preferences, feedback=None):
    entry = {
        "mission_id": mission_id,
        "title": clean_text(mission.get("title"), "Outdoor Mission", 120),
        "activity": clean_text(mission.get("activity"), mission.get("title", "Outdoor activity"), 100),
        "goal": clean_text(mission.get("goal"), "General", 100),
        "completed_at": datetime.now(timezone.utc),
        "feedback": feedback,
        "preferences": preferences or {},
        "points": max(0, min(50, int(mission.get("points", 20)))),
        "duration_minutes": max(0, int((preferences or {}).get("minutes", 0))),
        "status": "completed",
    }
    journal = st.session_state.setdefault("journal", [])
    journal[:] = [x for x in journal if x.get("mission_id") != mission_id]
    journal.insert(0, entry)
    collection = get_mongo_collection()
    if collection is not None:
        try:
            collection.update_one(
                {"session_key": get_user_key(), "mission_id": mission_id},
                {"$set": {**entry, "session_key": get_user_key()}},
                upsert=True,
            )
        except Exception:
            pass
    return entry


def update_feedback(mission_id, feedback):
    for entry in st.session_state.get("journal", []):
        if entry.get("mission_id") == mission_id:
            entry["feedback"] = feedback
    collection = get_mongo_collection()
    if collection is not None:
        try:
            collection.update_one({"session_key": get_user_key(), "mission_id": mission_id}, {"$set": {"feedback": feedback}})
        except Exception:
            pass


def mission_history(limit=30):
    journal = load_journal()
    return [x for x in journal if x.get("status") == "completed"][:limit]


def get_disliked_activities(history):
    return sorted({clean_text(x.get("activity"), "", 100) for x in history if x.get("feedback") == "Didn't enjoy it" and x.get("activity")})


def build_memory_summary(history):
    """Compress relevant prior experience into safe, useful context for the model."""
    if not history:
        return "No previous completed mission history is available yet."
    dislikes = get_disliked_activities(history)
    goals = [clean_text(x.get("preferences", {}).get("goal"), "", 100) for x in history]
    interests = [clean_text(x.get("preferences", {}).get("interests"), "", 100) for x in history]
    enjoyed = [x.get("activity") for x in history if x.get("feedback") == "Enjoyed it" and x.get("activity")]
    return json.dumps({
        "recent_missions": [{"title": x.get("title"), "activity": x.get("activity"), "goal": x.get("goal"), "feedback": x.get("feedback")} for x in history[:8]],
        "activities_to_avoid_when_possible": dislikes,
        "frequent_goals": Counter([x for x in goals if x]).most_common(3),
        "frequent_interests": Counter([x for x in interests if x and x != "Any activity"]).most_common(3),
        "activities_previously_enjoyed": enjoyed[:5],
    }, ensure_ascii=False)


# =========================================================
# PLACES, VOICE, AND MISSION VALIDATION
# =========================================================

def find_outdoor_destinations(location, minutes=20):
    location = " ".join(str(location or "").split()).strip()
    if not location:
        raise ValueError("Enter a city or neighborhood to search.")
    if len(location) > 120:
        raise ValueError("Please keep the location under 120 characters.")
    if not SERPAPI_API_KEY:
        raise ValueError("SERPAPI_API_KEY is missing. Add it to your local .env or Render environment variables.")
    response = requests.get("https://serpapi.com/search.json", params={
        "engine": "google_maps", "type": "search",
        "q": f"parks, public gardens, and outdoor walking places in {location}",
        "api_key": SERPAPI_API_KEY,
    }, timeout=(5, 25))
    if not response.ok:
        raise RuntimeError(f"SerpApi returned HTTP {response.status_code}.")
    data = response.json()
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data.get("local_results", [])[:8]


def generate_mission_audio(text):
    text = " ".join(str(text or "").split()).strip()[:4500]
    if not text:
        raise ValueError("There is no mission text to narrate.")
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is missing.")
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        json={"text": text, "model_id": "eleven_flash_v2_5"}, timeout=(5, 60),
    )
    if not response.ok:
        raise RuntimeError(f"ElevenLabs error ({response.status_code}): {response.text[:350]}")
    return response.content


def validate_mission(candidate, goal, minutes):
    if not isinstance(candidate, dict):
        raise ValueError("Mission response must be a JSON object.")
    steps_raw = candidate.get("steps")
    if not isinstance(steps_raw, list):
        raise ValueError("Mission steps must be a list.")
    steps = []
    for item in steps_raw:
        if isinstance(item, dict):
            item = item.get("text", "")
        step = clean_text(item, "", 240)
        if step:
            steps.append(step)
        if len(steps) >= 5:
            break
    if len(steps) < 2:
        raise ValueError("A mission must include at least two steps.")
    themes = {"forest", "garden", "meadow", "rain", "winter", "coast"}
    theme = clean_text(candidate.get("visual_theme", "forest"), "forest", 20).lower()
    if theme not in themes:
        theme = "forest"
    try:
        points = int(candidate.get("points", 20))
    except (TypeError, ValueError):
        points = 20
    duration = max(1, min(180, int(minutes)))
    # Add a consistent, easy-to-follow timeline even if the small model forgets it.
    # Divide the requested total across the steps so the timing is explicit and usable.
    timed_steps = []
    step_count = len(steps)
    for index, step in enumerate(steps):
        start_minute = round(index * duration / step_count)
        end_minute = round((index + 1) * duration / step_count)
        if end_minute <= start_minute:
            end_minute = start_minute + 1
        if re.match(r"^\s*(?:\d+\s*(?:-|–|to)\s*\d+\s*(?:min|minutes?)|(?:first|next|final)\s+\d+\s+minutes?)\b", step, re.IGNORECASE):
            timed_steps.append(step)
        else:
            timed_steps.append(f"{start_minute}–{end_minute} min: {step}")
    description = clean_text(candidate.get("description"), "Take a little breathing room and notice the nature around you, at your own pace.", 700)
    if not re.search(r"\b\d+\s*(?:min|minutes?)\b", description, re.IGNORECASE):
        description = f"{description.rstrip('. ')}. Give yourself about {duration} minutes for this; there is no need to do it perfectly—just show up and notice one small thing."[:700]
    return {
        "title": clean_text(candidate.get("title"), "A Small Nature Reset", 120),
        "description": description,
        "steps": timed_steps,
        "points": max(5, min(50, points)),
        "impact": clean_text(candidate.get("impact"), "This activity offers a chance to notice and appreciate your surroundings.", 500),
        "activity": clean_text(candidate.get("activity"), candidate.get("title", "Nature activity"), 100),
        "alternative": clean_text(candidate.get("alternative"), "Try a seated or window-based nature observation instead.", 400),
        "visual_theme": theme,
        "goal": clean_text(goal, "General", 100),
        "duration_minutes": duration,
        "ai_rationale": clean_text(candidate.get("ai_rationale"), "This option best fits the preferences and constraints you shared.", 400),
        "difficulty": clean_text(candidate.get("difficulty"), "Gentle", 40),
    }


FALLBACK_MISSIONS = [
    {"title": "Notice Five Small Details", "description": "Take a brief pause and notice natural details around you. Let curiosity guide your attention without needing to go anywhere special.", "steps": ["Choose a comfortable, safe place outdoors, by a doorway, or beside a window.", "Notice five natural details, such as light, clouds, leaves, shadows, or birdsong.", "Pick one detail and observe it for another minute."], "points": 20, "impact": "A short pause can create a moment of calm and connection with nature.", "activity": "Mindful nature observation", "alternative": "Observe the sky, a plant, or natural light through a window.", "visual_theme": "garden", "difficulty": "Gentle"},
    {"title": "A Gentle Green Break", "description": "Take a few minutes away from your usual task and notice nearby signs of plant life.", "steps": ["Choose a safe, accessible spot that costs nothing.", "Walk, roll, or sit comfortably and notice different shapes and shades of green.", "Pause for three comfortable breaths before returning to your day."], "points": 20, "impact": "A change of focus may help you appreciate the living things around you.", "activity": "Gentle outdoor reset", "alternative": "Look at a houseplant or a tree from a window.", "visual_theme": "forest", "difficulty": "Gentle"},
    {"title": "Listen to the World", "description": "Slow down and listen for ordinary sounds in your environment.", "steps": ["Settle in a safe, comfortable spot indoors or outdoors.", "Listen for one minute and notice sounds that are near and far away.", "Choose one sound to follow for a few more breaths."], "points": 15, "impact": "Careful listening can offer a simple grounding moment.", "activity": "Sound awareness", "alternative": "Listen to rain, wind, or other sounds from indoors; silence is also fine.", "visual_theme": "meadow", "difficulty": "Very gentle"},
]


def fallback_mission(goal, minutes):
    mission = random.choice(FALLBACK_MISSIONS).copy()
    mission["goal"] = goal
    mission["duration_minutes"] = minutes
    mission["ai_rationale"] = "The AI service was unavailable, so Fresh Air selected a ready-to-use fallback mission."
    return validate_mission(mission, goal, minutes)


def selected_destination_prompt(destination):
    if not isinstance(destination, dict):
        return "No specific destination selected; do not invent a named place."
    name = clean_text(destination.get("name"), "", 140)
    address = clean_text(destination.get("address"), "", 220)
    return f"{name} — {address}" if name and address else (name or "No specific destination selected")


def generate_mission_candidates(preferences, count=1):
    """Generate one concise, validated mission using the original local Ollama model.

    llama3.2:1b responds slowly through a laptop tunnel. Asking it for three full JSON
    candidates caused long generations and truncated JSON, so the stable path requests
    one high-quality candidate and retains deterministic validation and preference checks.
    """
    history = mission_history(20)
    memory = build_memory_summary(history)
    destination = selected_destination_prompt(preferences.get("destination"))
    compact_context = {
        "mood": preferences.get("mood", "unspecified"),
        "energy": preferences.get("energy", "unspecified"),
        "minutes": preferences.get("minutes", 10),
        "goal": preferences.get("goal", "General"),
        "access": preferences.get("access", "unspecified"),
        "interests": preferences.get("interests", []),
        "resources": preferences.get("resources", "none specified"),
        "accessibility": preferences.get("accessibility", "none specified"),
        "extra_context": clean_text(preferences.get("extra_context", ""), "", 220),
    }
    prompt = f"""Create ONE concise, personalized nature/wellbeing mission for Fresh Air.
USER: {json.dumps(compact_context, ensure_ascii=False)}
DESTINATION: {destination}
RECENT PREFERENCE MEMORY: {clean_text(memory, 'No prior feedback.', 300)}
Rules: free, safe, practical, no required purchases/supplies/travel; include an indoor/window alternative if needed; don't invent place details or claim measured environmental impact. Match the user's goal, mood, energy, accessibility, and interests. Make exactly 3 clear steps, each with a realistic time range in minutes; the ranges together should cover the requested {compact_context['minutes']} minutes. Make the description warm, personable, and encouraging: 3 short sentences (about 45–65 words), speak directly to the user, explain what the experience may feel like, include the total time, and reassure them that there is no pressure to do it perfectly. Do not make medical promises. Choose visual_theme from forest, garden, meadow, rain, winter, coast.
Return ONLY one valid JSON object with these keys: title, description, steps (array of 3 strings), points (integer 10-30), impact, activity, alternative, visual_theme, difficulty, ai_rationale, selection_rationale. Aim for 280–330 tokens total so the description feels personal but still finishes quickly. Do not add markdown or extra text."""
    try:
        raw = call_original_ai(prompt, temperature=0.45, timeout=150, json_mode=True, max_tokens=380)
        result = parse_json_object(raw)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as first_error:
        # A compact retry helps if the small model returns malformed or incomplete JSON.
        retry_prompt = f"Return one concise valid JSON nature mission for this user: {json.dumps(compact_context, ensure_ascii=False)}. Keys: title, description, steps (3 short strings), points (integer), impact, activity, alternative, visual_theme (forest/garden/meadow/rain/winter/coast), difficulty, ai_rationale, selection_rationale. Free, safe, no purchases or required travel. Output JSON only."
        try:
            raw = call_original_ai(retry_prompt, temperature=0.2, timeout=120, json_mode=True, max_tokens=220)
            result = parse_json_object(raw)
        except Exception:
            raise first_error
    candidate_data = result
    if isinstance(result.get("candidates"), list) and result["candidates"]:
        candidate_data = result["candidates"][0]
    try:
        candidate = validate_mission(candidate_data, preferences.get("goal", "General"), preferences.get("minutes", 15))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("The AI response did not contain a complete, valid mission. Please try again.")
    rationale = clean_text(result.get("selection_rationale"), "The mission was selected to match your stated preferences and access needs.", 400)

    # Deterministic checks remain in place even though the small model returns one option.
    combined = (candidate.get("description", "") + " " + " ".join(candidate.get("steps", []))).lower()
    access = str(preferences.get("access", "")).lower()
    accessibility = str(preferences.get("accessibility", "")).lower()
    if "cannot go outside" in access and not any(term in combined for term in ("window", "indoors", "inside", "doorway")):
        candidate["alternative"] = clean_text(candidate.get("alternative"), "Observe clouds, plants, or natural light from a window.", 400)
    if "seated" in accessibility and not any(term in combined for term in ("sit", "seated", "chair", "stationary")):
        candidate["alternative"] = clean_text(candidate.get("alternative"), "Try the activity seated by a window or in a comfortable chair.", 400)
    return [candidate], rationale, memory


def generate_single_mission(preferences):
    candidates, rationale, memory = generate_mission_candidates(preferences, count=1)
    selected = candidates[0]
    selected["ai_rationale"] = clean_text(selected.get("ai_rationale"), rationale, 400)
    return selected, candidates, rationale, memory


def apply_destination_context(mission, destination, access):
    if not isinstance(mission, dict) or not isinstance(destination, dict):
        return mission
    name = clean_text(destination.get("name"), "", 140)
    address = clean_text(destination.get("address"), "", 220)
    if not name:
        return mission
    url = destination.get("url", "")
    safe_destination = {"name": name, "address": address}
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        safe_destination["url"] = url[:1000]
    mission["destination"] = safe_destination
    if name.lower() not in str(mission.get("description", "")).lower():
        if "cannot go outside" in str(access).lower():
            mission["description"] += f" The place you selected, {name}, remains optional for another day; use the indoor-friendly version today."
        else:
            mission["description"] += f" Suggested setting: {name}" + (f" ({address})" if address else "") + ". Verify public access and current details before visiting."
    return mission


def run_temporal_mission(preferences):
    """Optional Temporal workflow integration; direct Ollama is used if unavailable."""
    async def _run():
        from temporalio.client import Client
        from temporal_workflow import MoodDividendWorkflow
        client = await asyncio.wait_for(Client.connect(get_setting("TEMPORAL_ADDRESS", "localhost:7233")), timeout=4)
        return await client.execute_workflow(MoodDividendWorkflow.run, preferences, id=f"fresh-air-{uuid.uuid4()}", task_queue=get_setting("TEMPORAL_TASK_QUEUE", "fresh-air-queue"))
    return asyncio.run(_run())


# =========================================================
# RESTORED ORIGINAL ANIMATED VISUALS
# =========================================================
# =========================================================
# ANIMATED ENVIRONMENTAL BACKGROUND
# =========================================================

# Ollama supplies a small, validated visual theme with each mission. The model
# selects a scene; CSS handles the actual photographic imagery and animation.
_existing_mission = st.session_state.get("mission") or {}
_visual_theme = str(_existing_mission.get("visual_theme", "forest")).strip().lower()
if _visual_theme not in {"forest", "garden", "meadow", "rain", "winter", "coast"}:
    _visual_theme = "forest"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
        --ink: #f4faf7;
        --muted: #d0e1dc;
        --glass: rgba(10, 30, 34, 0.76);
        --line: rgba(255,255,255,0.16);
        --mint: #a8f0ce;
    }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background: #102e37;
        color: var(--ink);
    }

    /* A photographic, layered environment replaces the floating-shape look. */
    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background: linear-gradient(180deg, rgba(5, 19, 24, .24) 0%, rgba(5, 24, 27, .30) 44%, rgba(4, 18, 20, .72) 100%);
    }

    .stApp::after {
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background: radial-gradient(ellipse at 50% 5%, rgba(255, 239, 198, .16), transparent 44%),
                    linear-gradient(90deg, rgba(3, 18, 18, .26), transparent 36%, transparent 70%, rgba(3, 18, 18, .20));
    }

    .environment {
        --scene-image: url("https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=2400&q=85");
        position: fixed;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        pointer-events: none;
        isolation: isolate;
        background: #193b32;
    }
    .environment.scene-forest { --scene-image: url("https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=2400&q=85"); }
    .environment.scene-garden { --scene-image: url("https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=2400&q=85"); }
    .environment.scene-meadow { --scene-image: url("https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=2400&q=85"); }
    .environment.scene-rain { --scene-image: url("https://images.unsplash.com/photo-1511497584788-876760111969?auto=format&fit=crop&w=2400&q=85"); }
    .environment.scene-winter { --scene-image: url("https://images.unsplash.com/photo-1418985991508-e47386d96a71?auto=format&fit=crop&w=2400&q=85"); }
    .environment.scene-coast { --scene-image: url("https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=2400&q=85"); }

    /* A cinematic scene carousel: photographic locations crossfade every six seconds. */
    .environment .scene-stack { position:absolute; inset:-4%; overflow:hidden; }
    .environment .scene-slide {
        position:absolute; inset:0; background-size:cover; background-position:center 48%;
        opacity:0; transform:scale(1.04); filter:saturate(.96) contrast(1.04);
        animation: sceneCrossfade 36s ease-in-out infinite, landscapeDrift 24s ease-in-out infinite alternate;
        will-change:opacity,transform;
    }
    .environment .scene-slide::after {
        content:""; position:absolute; inset:0;
        background:linear-gradient(180deg,rgba(10,29,29,.04) 0%,rgba(8,28,25,.12) 38%,rgba(4,18,17,.62) 100%);
    }
    .environment .scene-slide.primary { background-image:var(--scene-image); animation-delay:0s, -5s; }
    .environment .scene-slide.garden { background-image:url("https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=2400&q=85"); animation-delay:-30s,-11s; }
    .environment .scene-slide.meadow { background-image:url("https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=2400&q=85"); animation-delay:-24s,-8s; }
    .environment .scene-slide.rain { background-image:url("https://images.unsplash.com/photo-1511497584788-876760111969?auto=format&fit=crop&w=2400&q=85"); animation-delay:-18s,-13s; }
    .environment .scene-slide.winter { background-image:url("https://images.unsplash.com/photo-1418985991508-e47386d96a71?auto=format&fit=crop&w=2400&q=85"); animation-delay:-12s,-4s; }
    .environment .scene-slide.coast { background-image:url("https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=2400&q=85"); animation-delay:-6s,-10s; }
    @keyframes sceneCrossfade {
        0%, 15% { opacity:1; }
        19%, 96% { opacity:0; }
        100% { opacity:1; }
    }
    .environment .scene-slide.garden { animation-name:sceneCrossfade, landscapeDrift; }
    .environment .scene-slide.meadow { animation-name:sceneCrossfade, landscapeDrift; }
    .environment .scene-slide.rain { animation-name:sceneCrossfade, landscapeDrift; }
    .environment .scene-slide.winter { animation-name:sceneCrossfade, landscapeDrift; }
    .environment .scene-slide.coast { animation-name:sceneCrossfade, landscapeDrift; }
    .environment .light-haze {
        position: absolute;
        inset: -20%;
        background: radial-gradient(ellipse at 72% 17%, rgba(255, 226, 165, .22), transparent 27%),
                    radial-gradient(ellipse at 15% 55%, rgba(127, 214, 173, .12), transparent 35%);
        mix-blend-mode: screen;
        animation: hazeDrift 28s ease-in-out infinite alternate;
    }
    .environment .depth-vignette {
        position: absolute;
        inset: 0;
        box-shadow: inset 0 0 170px rgba(2, 15, 15, .48);
    }

    /* Restrained weather overlays: visible, but never the main subject. */
    .environment .rain-layer {
        position: absolute;
        inset: -25% -10%;
        opacity: 0;
        background-image: repeating-linear-gradient(108deg, transparent 0 28px, rgba(225, 244, 250, .42) 29px, transparent 30px 48px);
        background-size: 90px 120px;
        animation: rainDrift 1.1s linear infinite;
    }
    .environment.scene-rain .rain-layer { opacity: .26; }
    .environment .snow-layer {
        position: absolute;
        inset: -5% 0 0;
        opacity: 0;
        background-image: radial-gradient(circle, rgba(255,255,255,.92) 0 1.2px, transparent 2px),
                          radial-gradient(circle, rgba(255,255,255,.72) 0 2px, transparent 3px),
                          radial-gradient(circle, rgba(255,255,255,.8) 0 1px, transparent 2px);
        background-size: 91px 105px, 151px 169px, 63px 77px;
        animation: snowDrift 18s linear infinite;
    }
    .environment.scene-winter .snow-layer { opacity: .58; }
    .environment .wind-layer {
        position: absolute;
        inset: 0;
        opacity: .18;
        background: repeating-linear-gradient(174deg, transparent 0 95px, rgba(232, 249, 239, .22) 96px, transparent 98px 155px);
        mask-image: linear-gradient(90deg, transparent, black 28%, black 75%, transparent);
        animation: windDrift 13s ease-in-out infinite alternate;
    }

    /* Realistic foliage photography at the lower edges anchors the scene. */
    .environment .foliage {
        position: absolute;
        bottom: -5%;
        width: min(38vw, 470px);
        height: 47vh;
        min-height: 250px;
        background-image: url("https://images.unsplash.com/photo-1497250681960-ef046c08a56e?auto=format&fit=crop&w=1000&q=85");
        background-size: cover;
        background-position: center;
        opacity: .45;
        filter: saturate(.88) brightness(.66) contrast(1.08);
        -webkit-mask-image: linear-gradient(to top, #000 0%, #000 45%, transparent 100%);
        mask-image: linear-gradient(to top, #000 0%, #000 45%, transparent 100%);
        animation: foliageSway 15s ease-in-out infinite alternate;
    }
    .environment .foliage.left { left: -9%; transform-origin: bottom left; animation: foliageSway 7.5s ease-in-out infinite alternate; }
    .environment .foliage.right { right: -9%; transform: scaleX(-1); transform-origin: bottom right; animation: foliageSway 9s ease-in-out infinite alternate-reverse; animation-delay: -3s; }
    /* Soft moving light flecks mimic wind through a canopy, rather than floating geometric shapes. */
    .environment .canopy-light {
        position:absolute; inset:-12%; opacity:.2; mix-blend-mode:screen;
        background:radial-gradient(ellipse at 20% 24%,rgba(246,255,213,.22),transparent 13%),
                   radial-gradient(ellipse at 76% 36%,rgba(197,255,222,.16),transparent 17%),
                   radial-gradient(ellipse at 54% 8%,rgba(255,238,186,.17),transparent 19%);
        animation: canopyMove 19s ease-in-out infinite alternate; pointer-events:none;
    }

    @keyframes landscapeDrift {
        from { transform: scale(1.06) translate3d(-.4%, 0, 0); }
        to { transform: scale(1.13) translate3d(.5%, -1%, 0); }
    }
    @keyframes hazeDrift {
        from { transform: translate3d(-1.5%, .5%, 0) scale(1); opacity: .65; }
        to { transform: translate3d(1.5%, -1%, 0) scale(1.05); opacity: 1; }
    }
    @keyframes rainDrift { from { transform: translate3d(-2%, -3%, 0); } to { transform: translate3d(3%, 9%, 0); } }
    @keyframes snowDrift { from { transform: translate3d(-1%, -3%, 0); } to { transform: translate3d(2%, 8%, 0); } }
    @keyframes windDrift { from { transform: translateX(-2%); opacity: .08; } to { transform: translateX(2%); opacity: .22; } }
    @keyframes foliageSway { from { transform:rotate(-1.2deg) scale(1.02); background-position:48% 50%; } to { transform:rotate(1.8deg) scale(1.07); background-position:53% 50%; } }
    @keyframes canopyMove { from { transform:translate3d(-2%,0,0) scale(1); opacity:.12; } to { transform:translate3d(2%,-1.5%,0) scale(1.08); opacity:.3; } }

    @media (prefers-reduced-motion: reduce) {
        .environment *, .environment::before, .environment::after { animation: none !important; }
    }

    /* Ensure Streamlit content appears above scenery */
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] {
        position: relative;
        z-index: 1;
        background: transparent !important;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }

    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1150px;
    }

    @media (max-width: 700px) {
        .plant { opacity:.55; transform:scale(.52); }
        .plant.left { left:-62px; }
        .plant.right { right:-62px; }
        .crystal { opacity:.55; }
        .wind-streaks { opacity:.18; }
    }

    .hero {
        padding: 2.1rem 0 1.2rem;
        text-align: left;
    }

    .eyebrow {
        color: var(--mint);
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.19em;
        margin-bottom: 0.75rem;
    }

    .hero h1 {
        font-family: 'Manrope', sans-serif;
        font-size: clamp(2.8rem, 7vw, 5.4rem);
        line-height: 1.02;
        font-weight: 800;
        letter-spacing: -0.065em;
        color: #ffffff;
        margin: 0;
        text-shadow: 0 3px 30px rgba(0,0,0,0.15);
    }

    .hero h1 span {
        color: #a8f0ce;
    }

    .hero p {
        color: #e0eeea;
        font-size: 1.08rem;
        max-width: 650px;
        line-height: 1.8;
        margin-top: 1.15rem;
    }

    .section-heading {
        font-family: 'Manrope', sans-serif;
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.035em;
        color: #ffffff;
        margin: 0.7rem 0 0.2rem;
    }

    .muted {
        color: var(--muted);
        line-height: 1.65;
    }

    .glass-card {
        background: var(--glass);
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 1.25rem;
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        box-shadow: 0 16px 45px rgba(0,0,0,0.12);
        margin-bottom: 1rem;
    }

    .mission-prompt-card {
        position: relative;
        overflow: visible;
        padding-right: 4.6rem;
    }

    .mission-smiley {
        position: absolute;
        top: 1rem;
        right: 1rem;
        z-index: 2;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2.7rem;
        height: 2.7rem;
        border-radius: 50%;
        background: rgba(255,255,255,0.14);
        border: 1px solid rgba(255,255,255,0.42);
        font-size: 1.55rem;
        line-height: 1;
        cursor: pointer;
        user-select: none;
        transform: rotate(0deg) scale(1);
        transition: transform 180ms ease, background 180ms ease, box-shadow 180ms ease;
    }

    .mission-smiley:hover,
    .mission-smiley:active {
        background: rgba(168,240,206,0.30);
        transform: rotate(14deg) scale(1.18);
        box-shadow: 0 0 0 7px rgba(168,240,206,0.13), 0 8px 24px rgba(0,0,0,0.20);
    }

    .smiley-message {
        position: absolute;
        right: 0;
        top: 3rem;
        width: max-content;
        max-width: 12rem;
        padding: 0.4rem 0.65rem;
        border-radius: 999px;
        color: #123b32;
        background: #c9ffe4;
        font: 700 0.75rem 'DM Sans', sans-serif;
        opacity: 0;
        transform: translateY(-4px);
        pointer-events: none;
        transition: opacity 180ms ease, transform 180ms ease;
    }

    .mission-smiley:hover .smiley-message,
    .mission-smiley:active .smiley-message {
        opacity: 1;
        transform: translateY(0);
    }

    .metric-label {
        color: #d0e1dc;
        font-size: 0.83rem;
        font-weight: 600;
    }

    .metric-number {
        color: white;
        font-family: 'Manrope', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.05em;
        margin-top: 0.2rem;
    }

    .mission-label {
        color: #a8f0ce;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.13em;
        text-transform: uppercase;
    }

    .mission-title {
        color: #ffffff;
        font-family: 'Manrope', sans-serif;
        font-size: 1.65rem;
        font-weight: 800;
        line-height: 1.25;
        margin: 0.45rem 0 0.75rem;
    }

    .mission-description {
        color: #e0eeea;
        line-height: 1.75;
        font-size: 1rem;
    }

    .step-item {
        padding: 0.65rem 0;
        border-bottom: 1px solid rgba(255,255,255,0.10);
        color: #eef7f3;
        line-height: 1.6;
    }

    .step-item:last-child {
        border-bottom: none;
    }

    /* Inputs */
    [data-testid="stWidgetLabel"] p {
        color: #f1faf6 !important;
        font-weight: 600 !important;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div {
        background: rgba(255,255,255,0.94) !important;
        border: 1px solid rgba(255,255,255,0.4) !important;
        border-radius: 12px !important;
    }

    div[data-baseweb="select"] *,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        color: #173c3d !important;
    }

    .stSlider [data-testid="stTickBar"] {
        color: white;
    }

    /* Buttons */
    .stButton > button,
    .stFormSubmitButton > button {
        border-radius: 13px;
        border: 1px solid rgba(255,255,255,0.25);
        padding: 0.7rem 1rem;
        font-weight: 700;
        transition: all 0.2s ease;
    }

    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: #a8f0ce;
        color: #143a35;
        border: none;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        background: #d0ffe7;
        color: #143a35;
        transform: translateY(-2px);
    }

    .stButton > button[kind="secondary"] {
        background: rgba(255,255,255,0.10);
        color: white;
    }

    /* General text and separators */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: #f0f7f4;
    }

    hr {
        border-color: rgba(255,255,255,0.16) !important;
    }

    [data-testid="stAlert"] {
        border-radius: 14px;
    }

    @media (max-width: 700px) {
        [data-testid="stMainBlockContainer"] {
            padding: 1rem 1rem 3rem;
        }

        .hero {
            padding-top: 1.4rem;
        }

        .hero h1 {
            font-size: 3rem;
        }

        .hero p {
            font-size: 0.98rem;
        }

        .glass-card {
            padding: 1rem;
            border-radius: 18px;
        }

        .sun {
            width: 70px;
            height: 70px;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        .environment,
        .sun,
        .cloud,
        .mountain,
        .glacier,
        .forest,
        .waves, .orb, .crystal, .plant, .wind-streaks span {
            animation: none !important;
        }
        .environment::before, .environment::after { animation:none !important; }
    }
    </style>

    <div class="environment scene-__VISUAL_THEME__" id="fresh-air-environment">
        <div class="scene-stack" aria-hidden="true">
            <div class="scene-slide primary"></div>
            <div class="scene-slide garden"></div>
            <div class="scene-slide meadow"></div>
            <div class="scene-slide rain"></div>
            <div class="scene-slide winter"></div>
            <div class="scene-slide coast"></div>
        </div>
        <div class="light-haze"></div>
        <div class="canopy-light"></div>
        <div class="rain-layer"></div>
        <div class="snow-layer"></div>
        <div class="wind-layer"></div>
        <div class="foliage left"></div>
        <div class="foliage right"></div>
        <div class="depth-vignette"></div>
    </div>
    """.replace("__VISUAL_THEME__", _visual_theme),
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="eyebrow">YOUR WORLD. YOUR WELLBEING.</div>
        <h1>Fresh <span>Air.</span></h1>
        <p>An AI field companion that learns what works for you, plans nature missions around real life, and adapts when your day changes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# AI STATUS + SIDEBAR
# =========================================================
with st.sidebar:
    st.header("🌿 Fresh Air AI")
    st.caption(f"Original AI model: `{OLLAMA_MODEL}`")
    st.caption("Provider: Ollama only. Gemma/Gemini integration has been removed.")
    st.caption("For Render, OLLAMA_URL must point to a reachable Ollama server; localhost is only the app container.")
    if st.button("🧪 Test original AI connection", use_container_width=True):
        try:
            r = requests.post(ollama_endpoint("/api/show"), json={"model": OLLAMA_MODEL}, timeout=(5, 15))
            if r.ok:
                st.session_state.ai_model_test = {"ok": True, "message": f"{OLLAMA_MODEL} is available."}
            else:
                try: msg = r.json().get("error", r.text)
                except Exception: msg = r.text
                st.session_state.ai_model_test = {"ok": False, "message": str(msg)[:300]}
        except Exception as e:
            st.session_state.ai_model_test = {"ok": False, "message": str(e)[:300]}
    test = st.session_state.get("ai_model_test")
    if test:
        st.success(test["message"]) if test.get("ok") else st.error(test.get("message", "AI connection failed."))
    st.divider()
    st.markdown("**Connected services**")
    st.write("MongoDB journal: " + ("connected" if get_mongo_collection() is not None else "session-only mode"))
    st.write("SerpApi places: " + ("configured" if SERPAPI_API_KEY else "not configured"))
    st.write("ElevenLabs voice: " + ("configured" if ELEVENLABS_API_KEY else "not configured"))

# =========================================================
# METRICS + PREFERENCES
# =========================================================
history = mission_history(100)
total_points = sum(int(x.get("points", 0)) for x in history)
total_minutes = sum(int(x.get("duration_minutes", 0)) for x in history)
metrics = st.columns(3)
for col, label, value in zip(metrics, ["TOTAL POINTS", "MISSIONS COMPLETED", "AI MEMORY"], [total_points, len(history), "Active" if history else "Learning"]):
    with col:
        st.markdown(f'<div class="glass-card"><div class="metric-label">{label}</div><div class="metric-number">{html.escape(str(value))}</div></div>', unsafe_allow_html=True)

st.markdown('<div class="section-heading">Find your next mission</div>', unsafe_allow_html=True)
st.markdown('<p class="muted">Tell the AI what you need. It will create a personalized mission, check it against your constraints, and explain its recommendation.</p>', unsafe_allow_html=True)
left, right = st.columns(2)
with left:
    mood = st.selectbox("How are you feeling?", ["Stressed", "Overwhelmed", "Low energy", "Restless", "Curious", "Motivated", "Just need a reset"])
    energy = st.slider("Your energy level", 1, 5, 3, help="1 = very low energy; 5 = lots of energy")
    minutes = st.select_slider("How much time do you have?", options=[5, 10, 15, 20, 30, 45, 60], value=15, format_func=lambda x: f"{x} minutes")
with right:
    goal = st.selectbox("What would you like to focus on?", ["Feel calmer", "Move a little", "Connect with nature", "Help my community", "Learn about the environment", "Build a better routine"])
    access = st.selectbox("What access do you have today?", ["I can step outside near home", "I have access to a park or green space", "I can only use a balcony or doorway", "I cannot go outside right now", "I have limited mobility or accessibility needs"])
st.markdown("#### Make it yours")
p1, p2, p3 = st.columns(3)
with p1: interests = st.selectbox("Preferred activities", ["Any activity", "Mindful observation", "Gentle movement", "Gardening and plants", "Community care", "Learning and nature facts", "Photography or creativity", "Quiet time"])
with p2: resources = st.selectbox("Available resources", ["No special resources", "Phone only", "Notebook or pen", "A plant or garden", "A nearby public green space", "Household items already available"])
with p3: accessibility = st.selectbox("Accommodations", ["No additional needs", "Seated or low-movement activity", "Wheelchair / mobility access", "Sensory-friendly and quiet", "Indoor-only alternative", "Avoid heat / direct sun"])
extra_context = st.text_input("Anything else the AI should know? (optional)", placeholder="e.g., I have a short lunch break and don't want to walk far")

NATURE_FACTS = [
    ("🌱 Plants can help cool their surroundings.", "Shade and water released by plants can influence local temperatures; effects vary by plant, weather, and setting."),
    ("🐝 Pollinators do more than visit flowers.", "Bees, butterflies, moths, birds, and other animals help many flowering plants reproduce."),
    ("🌳 Trees support living communities.", "Trees can provide habitat, shade, and food for wildlife, while roots can help stabilize soil."),
    ("☁️ Clouds are part of the water cycle.", "Water evaporates, condenses into clouds, and can return to the surface as precipitation."),
    ("🍂 Fallen leaves have a role.", "As leaves break down, their nutrients can return to soil and support decomposers."),
    ("🌿 Repeated observation can reveal change.", "Noticing the same spot over time can help you see seasonal and weather-related changes."),
]
if "nature_fact_index" not in st.session_state:
    st.session_state.nature_fact_index = random.randrange(len(NATURE_FACTS))
fact_title, fact_body = NATURE_FACTS[st.session_state.nature_fact_index]
st.markdown(f'<div class="glass-card"><div class="metric-label">A LITTLE NATURE FACT</div><b>{html.escape(fact_title)}</b><p>{html.escape(fact_body)}</p></div>', unsafe_allow_html=True)
if st.button("🌱 Show another fun fact"):
    st.session_state.nature_fact_index = (st.session_state.nature_fact_index + 1) % len(NATURE_FACTS)
    st.rerun()

# =========================================================
# DESTINATION DISCOVERY — TOOL THE AGENT CAN USE
# =========================================================
st.markdown("---")
st.markdown('<div class="section-heading">📍 Somewhere to Go</div>', unsafe_allow_html=True)
st.caption("Optional: search for real public outdoor places. Search results do not guarantee access, opening hours, accessibility, or travel time.")
with st.form("outdoor_destination_form"):
    destination_location = st.text_input("City or neighborhood", placeholder="e.g., Miami, Florida", key="destination_location_input")
    available_minutes = st.selectbox("Available time for going out", [10, 20, 30, 45, 60], index=1, format_func=lambda n: f"{n} minutes (estimate only)")
    search_destinations = st.form_submit_button("🔎 Find Places")
if search_destinations:
    try:
        with st.spinner("Searching real places..."):
            places = find_outdoor_destinations(destination_location, available_minutes)
        st.session_state.destination_results = places or []
        st.session_state.destination_search_location = destination_location.strip()
        st.session_state.selected_destination = None
        if not places: st.info("No places returned. Try a nearby city or a more specific search.")
    except Exception as e:
        st.session_state.destination_results = []
        st.session_state.selected_destination = None
        st.error(f"Place search could not complete: {str(e)[:220]}")
places = st.session_state.get("destination_results", [])
destination_options = ["No specific destination"]
destination_map = {}
for place in places:
    if not isinstance(place, dict): continue
    name = clean_text(place.get("title"), "Outdoor destination", 140)
    address = clean_text(place.get("address"), "Address unavailable", 220)
    label = f"{name} — {address}"
    if label not in destination_map:
        links = place.get("links") or {}
        destination_options.append(label)
        destination_map[label] = {"name": name, "address": address, "url": place.get("link") or links.get("website") or links.get("directions") or ""}
if len(destination_options) > 1:
    selected_label = st.selectbox("Use this place as the mission setting (optional)", destination_options, key="destination_choice")
    st.session_state.selected_destination = None if selected_label == "No specific destination" else destination_map.get(selected_label)
    with st.expander("Review destination results"):
        for place in places:
            if not isinstance(place, dict): continue
            name = clean_text(place.get("title"), "Outdoor destination", 140)
            address = clean_text(place.get("address"), "Address unavailable", 220)
            with st.container(border=True):
                st.markdown(f"**{html.escape(name)}**")
                st.write(address)
                if place.get("rating") is not None: st.write(f"⭐ Rating: {place.get('rating')}")
                url = place.get("link") or (place.get("links") or {}).get("website") or (place.get("links") or {}).get("directions")
                if isinstance(url, str) and url.startswith(("http://", "https://")): st.link_button("View destination details", url)
                st.caption("Confirm current access, opening hours, accessibility, weather, and travel time before visiting.")
else:
    st.session_state.selected_destination = None
    st.caption("No destination selected. The AI can still create a mission without a place search.")
if st.session_state.get("selected_destination"):
    st.success("Selected: " + st.session_state.selected_destination["name"])

use_temporal = st.checkbox("Use optional Temporal retry workflow (requires a Temporal server and worker)", value=False)

# =========================================================
# MISSION CREATION — ADAPTIVE AGENT PLANNING + VALIDATION
# =========================================================
if st.button("✨ Ask Fresh Air AI to Plan My Mission", type="primary", use_container_width=True):
    preferences = {"mood": mood, "energy": energy, "minutes": int(minutes), "goal": goal, "access": access, "interests": interests, "resources": resources, "accessibility": accessibility, "extra_context": clean_text(extra_context, "", 500), "destination": st.session_state.get("selected_destination")}
    st.session_state.last_inputs = preferences
    st.session_state.mission_generation_error = None
    st.session_state.agent_trace = []
    try:
        with st.spinner("AI is reviewing your preferences and creating a personalized mission..."):
            # Temporal is attempted only when explicitly enabled. The workflow remains optional.
            if use_temporal:
                try:
                    temporal = run_temporal_mission(preferences)
                    candidate = temporal.get("mission") if isinstance(temporal, dict) else None
                    mission = validate_mission(candidate, goal, minutes)
                    candidates = [mission]
                    rationale = "Generated through the optional Temporal workflow."
                    memory = build_memory_summary(mission_history(20))
                    source = "Temporal workflow + original Ollama AI"
                except Exception as temporal_error:
                    st.session_state.agent_trace.append("Temporal unavailable; used direct Ollama generation.")
                    mission, candidates, rationale, memory = generate_single_mission(preferences)
                    source = "Direct Ollama agent"
            else:
                mission, candidates, rationale, memory = generate_single_mission(preferences)
                source = "Direct Ollama agent"
        mission = apply_destination_context(mission, preferences.get("destination"), access)
        st.session_state.mission = mission
        st.session_state.mission_candidates = candidates
        st.session_state.agent_trace.extend(["Retrieved recent mission history and feedback.", f"Generated and validated {len(candidates)} mission candidate(s).", "Applied preference and access checks before selecting a recommendation."])
        st.session_state.agent_rationale = rationale
        st.session_state.agent_memory_snapshot = memory
        st.session_state.current_mission_id = str(uuid.uuid4())
        st.session_state.mission_completed = False
        st.session_state.mission_feedback_saved = False
        st.session_state.mission_number += 1
        st.session_state.mission_used_ai = True
        st.session_state.mission_generation_model = OLLAMA_MODEL
        st.session_state.mission_generation_source = source
        st.rerun()
    except Exception as e:
        st.session_state.mission_generation_error = str(e)[:400]
        mission = fallback_mission(goal, minutes)
        mission = apply_destination_context(mission, st.session_state.get("selected_destination"), access)
        st.session_state.mission = mission
        st.session_state.mission_candidates = [mission]
        st.session_state.agent_rationale = "The original AI could not be reached, so a built-in fallback was selected."
        st.session_state.agent_trace = ["AI request failed validation or connection; fallback mission used."]
        st.session_state.current_mission_id = str(uuid.uuid4())
        st.session_state.mission_completed = False
        st.session_state.mission_feedback_saved = False
        st.session_state.mission_used_ai = False
        st.session_state.mission_generation_model = OLLAMA_MODEL
        st.session_state.mission_generation_source = "Fallback"
        st.rerun()

# =========================================================
# CURRENT MISSION + EXPLAINABLE AGENT TRACE
# =========================================================
mission = st.session_state.get("mission")
if mission:
    st.markdown("---")
    st.markdown('<div class="section-heading">Your AI-planned mission</div>', unsafe_allow_html=True)
    if not st.session_state.get("mission_used_ai"):
        st.warning("A built-in fallback mission is shown because the original AI could not be reached.")
        if st.session_state.get("mission_generation_error"):
            with st.expander("AI connection or generation details"):
                st.code(st.session_state.mission_generation_error)
    title = html.escape(str(mission.get("title", "Your mission")))
    description = html.escape(str(mission.get("description", "")))
    impact = html.escape(str(mission.get("impact", "")))
    st.markdown(f'<div class="glass-card mission-prompt-card" style="background:linear-gradient(120deg,rgba(25,105,92,.82),rgba(55,91,138,.78),rgba(119,81,137,.75));"><span class="mission-smiley" title="You got this! Hover or drag over me for a little encouragement" aria-label="Smiley face: you got this">☺️<span class="smiley-message">You got this!</span></span><div class="metric-label">YOUR NEXT SMALL WIN</div><h2>{title}</h2><p>{description}</p><div class="metric-label">WHY IT MATTERS</div><p>{impact}</p></div>', unsafe_allow_html=True)
    st.caption(f"⏱ About {mission.get('duration_minutes', minutes)} minutes · {html.escape(str(mission.get('difficulty', 'Gentle')))} · +{int(mission.get('points', 20))} points")
    with st.expander("🧠 Why the AI chose this mission", expanded=True):
        st.write(mission.get("ai_rationale", st.session_state.get("agent_rationale", "Chosen to fit your preferences.")))
        st.write(st.session_state.get("agent_rationale", "The recommendation considers your stated constraints and prior feedback."))
        for item in st.session_state.get("agent_trace", []): st.markdown(f"- {item}")
        with st.expander("Memory used for personalization"):
            st.caption("This is a compact summary of recent mission history used as context. It is not a diagnosis or a psychological profile.")
            st.code(st.session_state.get("agent_memory_snapshot", "No history available."), language="json")
    dest = mission.get("destination")
    if isinstance(dest, dict) and dest.get("name"):
        st.markdown("#### 📍 Suggested destination")
        st.write(f"**{dest.get('name')}**" + (f" — {dest.get('address')}" if dest.get("address") else ""))
        st.caption("This is a selected search result, not a guarantee of current access or travel time.")
        if isinstance(dest.get("url"), str) and dest["url"].startswith(("https://", "http://")): st.link_button("Open destination details", dest["url"])
    st.markdown("#### Your steps")
    for i, step in enumerate(mission.get("steps", []), 1):
        st.markdown(f'<div class="step-item"><b style="color:#a8f0ce">{i:02d}</b> &nbsp; {html.escape(str(step))}</div>', unsafe_allow_html=True)
    st.markdown("**If your plan changes:** " + str(mission.get("alternative", "Choose a comfortable alternative.")))
    with st.expander("🧪 Compare the AI's other mission ideas"):
        candidates = st.session_state.get("mission_candidates", [])
        if len(candidates) <= 1:
            st.caption("Only one valid candidate was returned for this request.")
        else:
            labels = [f"{i+1}. {c.get('title', 'Mission')} · {c.get('activity', '')}" for i, c in enumerate(candidates)]
            choice = st.selectbox("Choose another candidate", labels, key="candidate_choice")
            idx = labels.index(choice)
            alternative_candidate = candidates[idx]
            st.write(alternative_candidate.get("description", ""))
            st.write("**Why it may fit:** " + alternative_candidate.get("ai_rationale", "Alternative generated by the AI."))
            if st.button("Use this mission instead"):
                st.session_state.mission = apply_destination_context(alternative_candidate.copy(), st.session_state.get("selected_destination"), access)
                st.session_state.current_mission_id = str(uuid.uuid4())
                st.session_state.mission_completed = False
                st.session_state.mission_feedback_saved = False
                st.rerun()
    audio_col, complete_col, another_col = st.columns(3)
    with audio_col:
        if st.button("🎧 Listen to mission", use_container_width=True):
            narration = ". ".join([mission.get("title", "Your mission"), mission.get("description", ""), "Your steps."] + [f"Step {i}. {s}" for i, s in enumerate(mission.get("steps", []), 1)])
            try:
                with st.spinner("Creating voice guidance..."):
                    st.audio(generate_mission_audio(narration), format="audio/mpeg")
            except Exception as e:
                st.error(f"Voice generation failed: {str(e)[:250]}")
    with complete_col:
        if st.button(f"✅ Complete (+{int(mission.get('points', 20))} points)", type="primary", use_container_width=True):
            mission_id = st.session_state.current_mission_id or str(uuid.uuid4())
            if mission_id not in st.session_state.completed_mission_ids:
                st.session_state.points += int(mission.get("points", 20))
                st.session_state.completed_mission_ids.append(mission_id)
                st.session_state.completed.append({"title": mission.get("title"), "points": mission.get("points", 20), "goal": mission.get("goal", goal)})
            save_completed_mission(mission_id, mission, st.session_state.get("last_inputs", {}))
            st.session_state.mission_completed = True
            st.success("Mission saved. You can now tell the AI how it went.")
            st.rerun()
    with another_col:
        if st.button("🔄 New mission", use_container_width=True):
            st.session_state.mission = None
            st.session_state.chat_messages = []
            st.rerun()

# =========================================================
# CONVERSATIONAL ADAPTATION — AI CAN REPLAN CURRENT MISSION
# =========================================================
if st.session_state.get("mission"):
    st.markdown("---")
    st.markdown('<div class="section-heading">Talk to your AI field companion</div>', unsafe_allow_html=True)
    st.caption("Ask to shorten, simplify, change, or explain your mission. The AI receives the current mission and your original preferences to make an updated plan.")
    for message in st.session_state.get("chat_messages", []):
        with st.chat_message(message["role"]): st.markdown(message["content"])
    user_message = st.chat_input("e.g., I only have five minutes left. Adapt my mission.", key="mission_chat_input")
    if user_message:
        st.session_state.chat_messages.append({"role": "user", "content": user_message})
        current = st.session_state.mission
        chat_history = st.session_state.chat_messages[-8:]
        prompt = f"""You are Fresh Air's conversational nature-mission agent. Help adapt the mission safely and practically.
User preferences: {json.dumps(st.session_state.get('last_inputs', {}), ensure_ascii=False)}
Current mission: {json.dumps(current, ensure_ascii=False)}
Recent conversation: {json.dumps(chat_history, ensure_ascii=False)}
User's latest request: {user_message}
If the user asks to adapt/change the mission, return JSON with keys: reply, update_mission (boolean), mission (object or null).
If updating, mission must contain title, description, steps (list of 2-5 strings), points (keep same points unless the task is clearly shorter; never inflate points), impact, activity, alternative, visual_theme, difficulty, ai_rationale.
If they ask a general question, answer it in reply and set update_mission false, mission null.
Respect time, access, mobility, available resources, safety, and no-cost constraints. Do not claim to have checked weather or location unless tools returned that information. Do not diagnose or promise mental-health outcomes. Return only valid JSON.
"""
        try:
            with st.spinner("Your AI is responding..."):
                result = parse_json_object(call_original_ai(prompt, temperature=0.55, timeout=75, json_mode=True))
            reply = clean_text(result.get("reply"), "I can help adapt that. Tell me what you'd like to change.", 1200)
            if result.get("update_mission") and isinstance(result.get("mission"), dict):
                updated = validate_mission(result["mission"], current.get("goal", goal), st.session_state.get("last_inputs", {}).get("minutes", minutes))
                updated = apply_destination_context(updated, st.session_state.get("selected_destination"), access)
                st.session_state.mission = updated
                st.session_state.current_mission_id = str(uuid.uuid4())
                st.session_state.mission_completed = False
                st.session_state.mission_feedback_saved = False
                reply += "\n\nI've updated the mission above. Review the new steps before starting."
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            st.session_state.chat_messages.append({"role": "assistant", "content": f"I couldn't reach the AI just now. Your current mission is unchanged. Check the Ollama connection. ({str(e)[:180]})"})
        st.rerun()

# =========================================================
# FEEDBACK, MEMORY, REWARDS, AND AI REFLECTION
# =========================================================
st.markdown("---")
st.markdown('<div class="section-heading">Your journey</div>', unsafe_allow_html=True)
st.caption(f"You have logged approximately {total_minutes} minutes of planned nature-focused time. This is based on mission duration, not verified outdoor time.")
rewards = [("First Steps", 0), ("Green Explorer", 40), ("Nature Champion", 100), ("Earth Guardian", 200)]
for name, threshold in rewards:
    earned = total_points >= threshold
    st.markdown(f'<div class="glass-card"><b>{"🌿" if earned else "🔒"} {name}</b><span style="float:right;color:#a8f0ce">{"Unlocked" if earned else f"{threshold-total_points} points needed"}</span></div>', unsafe_allow_html=True)

if st.session_state.get("mission_completed") and st.session_state.get("current_mission_id"):
    st.markdown("#### Help your AI learn")
    feedback = st.radio("How did that mission work for you?", ["No feedback", "Enjoyed it", "It was okay", "Didn't enjoy it"], horizontal=True, key="mission_feedback_radio")
    feedback_note = st.text_input("Optional: what should the AI do differently next time?", key="mission_feedback_note", placeholder="e.g., less walking, more creative, quieter setting")
    if st.button("Save feedback to AI memory"):
        normalized = None if feedback == "No feedback" else feedback
        update_feedback(st.session_state.current_mission_id, normalized)
        # Save optional note alongside the journal entry where available.
        for entry in st.session_state.get("journal", []):
            if entry.get("mission_id") == st.session_state.current_mission_id:
                entry["feedback_note"] = clean_text(feedback_note, "", 300)
        collection = get_mongo_collection()
        if collection is not None:
            try: collection.update_one({"session_key": get_user_key(), "mission_id": st.session_state.current_mission_id}, {"$set": {"feedback_note": clean_text(feedback_note, "", 300)}})
            except Exception: pass
        st.session_state.mission_feedback_saved = True
        st.success("Feedback saved. Future mission prompts can use this preference.")
        st.rerun()

journal = mission_history(30)
st.markdown("---")
st.markdown('<div class="section-heading">📖 My Mission Journal</div>', unsafe_allow_html=True)
st.caption("MongoDB persistence is enabled when MONGODB_URI is configured and reachable. Otherwise, the journal is stored in the active Streamlit session only.")
st.metric("Completed missions available", len(journal))
if not journal:
    st.info("Complete a mission to begin your journal and give the AI feedback to learn from.")
else:
    saved_interests = [x.get("preferences", {}).get("interests") for x in journal if x.get("preferences", {}).get("interests") not in (None, "Any activity")]
    saved_goals = [x.get("preferences", {}).get("goal") for x in journal if x.get("preferences", {}).get("goal")]
    a, b = st.columns(2)
    with a: st.write("**Most common interest:** " + (Counter(saved_interests).most_common(1)[0][0] if saved_interests else "Not enough data yet"))
    with b: st.write("**Most common goal:** " + (Counter(saved_goals).most_common(1)[0][0] if saved_goals else "Not enough data yet"))
    for entry in journal:
        with st.container(border=True):
            st.subheader(entry.get("title", "Outdoor Mission"))
            st.caption(f"Activity: {entry.get('activity', 'Outdoor activity')} · +{entry.get('points', 0)} points · {entry.get('duration_minutes', 0)} minutes planned")
            if entry.get("completed_at"):
                try: st.caption("Completed: " + entry["completed_at"].strftime("%b %d, %Y %I:%M %p UTC"))
                except Exception: pass
            if entry.get("feedback"): st.write("Feedback: " + str(entry["feedback"]))
            if entry.get("feedback_note"): st.write("Note for AI: " + str(entry["feedback_note"]))
    if st.button("🪄 Generate my AI progress reflection"):
        memory = build_memory_summary(journal)
        reflection_prompt = f"You are Fresh Air's supportive reflection assistant. Based only on this mission summary, write a concise, non-clinical reflection with: (1) patterns in activities/goals, (2) what the user seems to prefer based on explicit feedback, (3) one practical next experiment. Do not diagnose, infer sensitive traits, exaggerate progress, or claim health benefits. If there is too little data, say so. Mission data: {memory}"
        try:
            with st.spinner("Reflecting on your mission history..."):
                st.session_state.ai_reflection = call_original_ai(reflection_prompt, temperature=0.5, timeout=60)
        except Exception as e:
            st.session_state.ai_reflection = f"The AI reflection could not be generated. Check the Ollama connection. ({str(e)[:180]})"
    if st.session_state.get("ai_reflection"):
        st.markdown("#### Your AI reflection")
        st.write(st.session_state.ai_reflection)

# AI evaluation panel: lightweight usage signals for hackathon demo
with st.expander("📊 AI quality and usage signals"):
    all_journal = mission_history(100)
    rated = [x for x in all_journal if x.get("feedback")]
    enjoyed_count = sum(1 for x in rated if x.get("feedback") == "Enjoyed it")
    completion_count = len(all_journal)
    st.write(f"Completed missions recorded: **{completion_count}**")
    st.write(f"Missions with explicit feedback: **{len(rated)}**")
    if rated:
        st.write(f"Positive feedback among rated missions: **{round(100 * enjoyed_count / len(rated))}%**")
    else:
        st.caption("Feedback metrics will become meaningful after users rate several missions.")
    st.caption("These are descriptive prototype metrics, not a controlled evaluation or proof that the AI improves wellbeing.")

if st.session_state.get("completed"):
    st.markdown("#### Recent wins")
    for item in reversed(st.session_state.completed[-10:]):
        st.markdown(f'<div class="glass-card"><b>✓ {html.escape(str(item.get("title", "Outdoor Mission")))}</b><span style="float:right;color:#a8f0ce">+{int(item.get("points", 0))} points</span></div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown("<div style='text-align:center;padding:1.2rem 0;color:#d0e9df'><div style='font-size:1.4rem'>🌍 🌿 🌊 🏔️</div><p>Small actions. Real places. A better connection with the world.</p><p style='font-size:.75rem;opacity:.8'>Fresh Air is a prototype for outdoor engagement and community action. It does not diagnose or treat mental health conditions. The original Ollama AI generates missions and reflections; place search uses SerpApi; voice uses ElevenLabs; MongoDB persistence is optional.</p></div>", unsafe_allow_html=True)
