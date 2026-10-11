import asyncio
import json
import os
import html
import random
import requests
import uuid
from datetime import datetime, timezone

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_setting(name, default=""):
    """Read Streamlit Cloud Secrets first, then local environment variables."""
    try:
        value = st.secrets.get(name)
        if value not in (None, ""):
            return str(value)
    except Exception:
        # Local development may not have a Streamlit secrets.toml file.
        pass
    value = os.getenv(name)
    return str(value) if value not in (None, "") else default


def find_outdoor_destinations(location, minutes):
    """Search for real outdoor places using SerpApi."""
    location = " ".join(str(location or "").split()).strip()
    if not location:
        raise ValueError("Enter a city or neighborhood to search.")
    if len(location) > 120:
        raise ValueError("Please keep the location under 120 characters.")

    api_key = get_setting("SERPAPI_API_KEY")

    if not api_key:
        raise ValueError(
            "SerpApi API key is missing. "
            "Check your .env file."
        )

    query = (
        f"parks, public gardens, and outdoor walking "
        f"places in {location}"
    )

    params = {
        "engine": "google_maps",
        "type": "search",
        "q": query,
        "api_key": api_key,
    }

    response = requests.get(
        "https://serpapi.com/search.json",
        params=params,
        timeout=(5, 25),
    )

    if not response.ok:
        raise RuntimeError(
            f"SerpApi returned HTTP {response.status_code}."
        )

    data = response.json()

    if data.get("error"):
        raise RuntimeError(data["error"])

    # A time limit guides the mission, but search results
    # do not prove that a destination fits that travel time.
    places = data.get("local_results", [])

    return places[:8]

def generate_mission_audio(text):
    """Convert mission text into speech with ElevenLabs."""
    text = " ".join(str(text or "").split()).strip()
    if not text:
        raise ValueError("There is no mission text to narrate.")
    text = text[:4500]

    api_key = get_setting("ELEVENLABS_API_KEY")

    if not api_key:
        raise ValueError(
            "ElevenLabs API key is missing. "
            "Check your .env file."
        )

    voice_id = "JBFqnCBsd6RMkjVDRZzb"

    url = (
        f"https://api.elevenlabs.io/v1/"
        f"text-to-speech/{voice_id}"
    )

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        "model_id": "eleven_flash_v2_5",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=(5, 60),
    )

    if not response.ok:
        raise RuntimeError(
            f"ElevenLabs error ({response.status_code}): "
            f"{response.text[:500]}"
        )

    return response.content

def save_completed_mission(
    mission_id, title, activity, feedback=None, preferences=None,
    points=0, duration_minutes=0,
):
    """Save a completed mission to this Streamlit session's local journal.

    This intentionally uses no external database. Entries are available during
    the current Streamlit session and are not permanent across new sessions.
    """
    entry = {
        "mission_id": mission_id,
        "title": title,
        "activity": activity,
        "completed_at": datetime.now(timezone.utc),
        "feedback": feedback,
        "preferences": preferences or {},
        "points": int(points),
        "duration_minutes": int(duration_minutes),
        "status": "completed",
    }
    journal = st.session_state.setdefault("journal", [])
    for index, existing in enumerate(journal):
        if existing.get("mission_id") == mission_id:
            journal[index] = entry
            break
    else:
        journal.insert(0, entry)


def get_mission_history(limit=20):
    """Return recent completed missions from the current session."""
    journal = st.session_state.get("journal", [])
    completed = [entry for entry in journal if entry.get("status") == "completed"]
    return completed[:limit]


# =========================================================
# FRESH AIR
# =========================================================

st.set_page_config(
    page_title="Fresh Air | Guided Nature Missions",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

with st.sidebar:
    st.header("⚙️ Mission Settings")
    selected_model = st.selectbox(
        "Ollama model",
        options=list(dict.fromkeys([get_setting("OLLAMA_MODEL", "llama3.2:1b"), "llama3.2:1b", "gemma2:2b"])),
        index=0,
        help="Choose a model available on the Ollama server configured for this deployment.",
    )
    st.caption(
        "Mission generation uses the Ollama server in OLLAMA_URL. For a cloud deployment, "
        "that must be a reachable hosted Ollama endpoint; localhost refers to the app container. "
        "Audio and destination search use external services only when requested."
    )

MODEL = selected_model
OLLAMA_BASE_URL = get_setting("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_URL = OLLAMA_BASE_URL if OLLAMA_BASE_URL.endswith("/api/generate") else f"{OLLAMA_BASE_URL}/api/generate"
DEFAULT_MODEL = get_setting("OLLAMA_MODEL", "llama3.2:1b")

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

# Distinct animated promise panel at the top of the experience.
st.markdown("""
<div class="promise-panel">
  <div class="promise-kicker">OUR PROMISE</div>
  <div class="promise-copy">No purchases required. No perfect day required.</div>
  <div class="promise-subcopy">Fresh Air meets you where you are. Your time, energy, access, and resources matter.</div>
</div>
<style>
.promise-panel { margin: 1rem 0 1.3rem; padding: 1.15rem 1.35rem; border-radius: 18px; border: 1px solid rgba(255,255,255,.25); background: linear-gradient(115deg,rgba(25,105,92,.92),rgba(55,91,138,.92),rgba(119,81,137,.92)); background-size: 220% 220%; animation: promiseShift 12s ease infinite; box-shadow: 0 10px 30px rgba(0,0,0,.16); }
.promise-kicker { font-size:.72rem; letter-spacing:.18em; font-weight:800; color:#d8ffe9; }
.promise-copy { font-size:1.2rem; font-weight:800; margin:.25rem 0; color:#fff; }
.promise-subcopy { color:#edf8f5; font-size:.93rem; }
@keyframes promiseShift { 0%,100% { background-position:0% 50%; } 50% { background-position:100% 50%; } }
@media (prefers-reduced-motion: reduce) { .promise-panel { animation:none; } }
</style>
""", unsafe_allow_html=True)


# =========================================================
# SESSION STATE
# =========================================================

if "points" not in st.session_state:
    st.session_state.points = 0

if "completed" not in st.session_state:
    st.session_state.completed = []

if "journal" not in st.session_state:
    st.session_state.journal = []

if "completed_mission_ids" not in st.session_state:
    st.session_state.completed_mission_ids = []

if "current_mission_id" not in st.session_state:
    st.session_state.current_mission_id = None

if "mission_completed" not in st.session_state:
    st.session_state.mission_completed = False

if "mission" not in st.session_state:
    st.session_state.mission = None

if "mission_number" not in st.session_state:
    st.session_state.mission_number = 0

if "last_inputs" not in st.session_state:
    st.session_state.last_inputs = {}

# =========================================================
# FALLBACK MISSIONS
# =========================================================

FALLBACK_MISSIONS = [
    {
        "title": "Notice Five Signs of Nature",
        "description": "Take a short break outdoors and reconnect with the environment by noticing details you might normally overlook.",
        "steps": [
            "Find a safe outdoor place you can access.",
            "Notice five natural details, such as clouds, leaves, shadows, or birds.",
            "Pause for a few slow breaths.",
            "Choose one detail you want to remember.",
        ],
        "points": 20,
        "impact": "Builds awareness of your surroundings without requiring equipment or money.",
    },
    {
        "title": "Give Your Neighborhood a Little Care",
        "description": "Make a small, safe contribution to a shared outdoor space using only what you already have.",
        "steps": [
            "Choose a familiar, safe public area.",
            "Look for one small improvement you can make without touching hazardous materials.",
            "If it is safe, tidy a small area or report a maintenance issue to the appropriate organization.",
            "Notice how the space feels afterward.",
        ],
        "points": 25,
        "impact": "Encourages shared responsibility for welcoming community spaces.",
    },
    {
        "title": "Take a Mindful Micro-Walk",
        "description": "Use a few minutes of movement and observation to create a little breathing room in your day.",
        "steps": [
            "Choose a safe route you already have access to.",
            "Walk or roll at a comfortable pace for five to ten minutes.",
            "Notice colors, textures, sounds, and changes in the weather.",
            "Finish by identifying one thing you appreciated.",
        ],
        "points": 20,
        "impact": "Encourages outdoor awareness and accessible everyday movement.",
    },
    {
        "title": "Become a Local Nature Observer",
        "description": "Learn something about the environment around you without disturbing plants or wildlife.",
        "steps": [
            "Look at the sky, trees, or other natural features from a safe place.",
            "Observe one change in the weather, light, or landscape.",
            "Think about how that change might affect the local environment.",
            "Write down your observation if you have a device or paper available.",
        ],
        "points": 20,
        "impact": "Builds environmental curiosity and observation skills.",
    },
    {
        "title": "Share One Useful Environmental Tip",
        "description": "Turn something you know about environmental care into a small act of community learning.",
        "steps": [
            "Think of one practical way to reduce waste or save energy.",
            "Make sure the tip is accurate and realistic.",
            "Share it with a friend or in an appropriate community space if you wish.",
            "Reflect on how small actions can spread through a community.",
        ],
        "points": 25,
        "impact": "Supports environmental learning and encourages practical action.",
    },
]

# =========================================================
# AI MISSION GENERATION
# =========================================================

def make_fallback_mission(goal):
    candidates = FALLBACK_MISSIONS.copy()
    random.shuffle(candidates)
    mission = candidates[0].copy()
    mission["goal"] = goal
    mission.setdefault("activity", mission.get("title", goal))
    mission.setdefault("alternative", "If this is not practical today, notice nature from a doorway or window for five minutes.")
    mission.setdefault("visual_theme", "forest")
    return mission


def get_disliked_activities():
    """Return activities disliked earlier in this Streamlit session."""
    return {
        str(entry.get("activity"))
        for entry in st.session_state.get("journal", [])
        if entry.get("feedback") == "Didn't enjoy it" and entry.get("activity")
    }


def _clean_text(value, fallback, max_length=700):
    """Normalize a generated field to bounded plain text."""
    if not isinstance(value, str):
        return fallback
    value = " ".join(value.replace("\x00", "").split()).strip()
    return value[:max_length] if value else fallback


def validate_mission(candidate, goal):
    """Validate and normalize a model response before rendering or scoring it."""
    if not isinstance(candidate, dict):
        raise ValueError("The model response was not a JSON object.")

    title = _clean_text(candidate.get("title"), "A Small Nature Reset", 120)
    description = _clean_text(
        candidate.get("description"),
        "Take a few minutes to notice the natural details around you.",
        600,
    )
    impact = _clean_text(
        candidate.get("impact"),
        "This activity offers a small opportunity to notice and appreciate your surroundings.",
        500,
    )

    raw_steps = candidate.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Mission steps must be a list.")
    steps = []
    for item in raw_steps:
        if isinstance(item, dict):
            item = item.get("text", "")
        step = _clean_text(item, "", 240)
        if step:
            steps.append(step)
        if len(steps) >= 5:
            break
    if len(steps) < 2:
        raise ValueError("A mission must contain at least two useful steps.")

    try:
        points = int(candidate.get("points", 20))
    except (TypeError, ValueError, OverflowError):
        points = 20
    points = max(5, min(50, points))

    allowed_themes = {"forest", "garden", "meadow", "rain", "winter", "coast"}
    theme = _clean_text(candidate.get("visual_theme", "forest"), "forest", 20).lower()
    if theme not in allowed_themes:
        theme = "forest"

    activity = _clean_text(candidate.get("activity"), title, 100)
    alternative = _clean_text(
        candidate.get("alternative"),
        "If this is not practical today, notice nature from a safe doorway or window for five minutes.",
        400,
    )

    return {
        "title": title,
        "description": description,
        "steps": steps,
        "points": points,
        "impact": impact,
        "activity": activity,
        "alternative": alternative,
        "visual_theme": theme,
        "goal": _clean_text(goal, "General", 100),
    }


def generate_mission(mood, energy, minutes, goal, access, interests="Any activity", resources="No special resources", accessibility="No additional needs"):
    """Generate a personalized mission, safely falling back when AI is unavailable."""
    disliked = get_disliked_activities()
    prompt = f"""
You create safe, realistic, adaptive nature and wellbeing missions for an app called Fresh Air.

Create one short mission using these user preferences:
Mood: {mood}
Energy: {energy}/5
Available time: {minutes} minutes
Goal: {goal}
Outdoor access: {access}
Interests: {interests}
Available resources: {resources}
Accessibility needs: {accessibility}

Rules:
- Make the mission achievable within the available time.
- Do not require spending money, buying supplies, or traveling.
- Prefer free places the user can already access.
- Include a practical alternative if the first idea is blocked by weather, access, energy, time, or missing supplies.
- Match the activity to stated interests, resources, and accessibility needs.
- If the user cannot go outside, provide a genuine indoor/doorway alternative rather than pressuring them.
- Never recommend trespassing, entering dangerous areas, touching hazardous waste, disturbing wildlife, damaging plants, or approaching unsafe water or roads.
- Do not claim that an environmental impact has been measured.
- Keep instructions practical, welcoming, and accessible.
- Choose visual_theme from: forest, garden, meadow, rain, winter, coast. It is an atmospheric theme only, not a claim about local weather.
- Return ONLY valid JSON, without Markdown.

Use exactly this JSON structure:
{{
  "title": "Short mission title",
  "description": "Two short sentences explaining the mission",
  "steps": ["First step", "Second step", "Third step"],
  "points": 20,
  "impact": "A realistic explanation of the possible benefit",
  "activity": "Short activity category/name",
  "alternative": "A realistic no-cost alternative if the original is impractical",
  "visual_theme": "forest"
}}
"""

    if disliked:
        prompt += (
            "\nAvoid these activities where possible because they were previously disliked: "
            + ", ".join(sorted(disliked))
            + ". Suggest a different activity instead."
        )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.7},
            },
            timeout=(5, 75),
        )
        response.raise_for_status()
        result = response.json()
        raw_text = result.get("response", "") if isinstance(result, dict) else ""
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("The model returned an empty response.")
        candidate = json.loads(raw_text)
        mission = validate_mission(candidate, goal)
        st.session_state["mission_generation_note"] = "ai"
        return mission, True

    except (requests.RequestException, ValueError, TypeError, KeyError, json.JSONDecodeError):
        st.session_state["mission_generation_note"] = "fallback"
        mission = make_fallback_mission(goal)
        return validate_mission(mission, goal), False
    except Exception:
        # Keep the app available if an unexpected model/server issue occurs.
        st.session_state["mission_generation_note"] = "fallback"
        mission = make_fallback_mission(goal)
        return validate_mission(mission, goal), False

async def run_temporal_mission(preferences):
    """Run mission generation and validation through a local Temporal worker."""
    from temporalio.client import Client
    from temporal_workflow import MoodDividendWorkflow

    client = await asyncio.wait_for(
        Client.connect(get_setting("TEMPORAL_ADDRESS", "localhost:7233")),
        timeout=4,
    )
    return await client.execute_workflow(
        MoodDividendWorkflow.run,
        preferences,
        id=f"mood-mission-{uuid.uuid4()}",
        task_queue=get_setting("TEMPORAL_TASK_QUEUE", "fresh-air-queue"),
    )


# =========================================================
# HEADER
# =========================================================

st.markdown(
    """
    <div class="hero">
        <div class="eyebrow">YOUR WORLD. YOUR WELLBEING.</div>
        <h1>Fresh <span>Air.</span></h1>
        <p>
            Small actions can change how we experience the world around us.
            Find your next outdoor mission, reconnect with your surroundings,
            and make every little action count.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# PROGRESS METRICS
# =========================================================

# Session-only progress: no MongoDB or external journal connection.
_session_journal = st.session_state.get("journal", [])
persistent_total = sum(1 for entry in _session_journal if entry.get("status") == "completed")
persistent_points = sum(int(entry.get("points", 0)) for entry in _session_journal if entry.get("status") == "completed")
persistent_minutes = sum(int(entry.get("duration_minutes", 0)) for entry in _session_journal if entry.get("status") == "completed")

metric1, metric2, metric3 = st.columns(3)

with metric1:
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">TOTAL POINTS</div>
            <div class="metric-number">{persistent_points}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with metric2:
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">MISSIONS COMPLETED</div>
            <div class="metric-number">{persistent_total}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with metric3:
    if persistent_points >= 200:
        reward = "Earth Guardian"
    elif persistent_points >= 100:
        reward = "Nature Champion"
    elif persistent_points >= 40:
        reward = "Green Explorer"
    else:
        reward = "First Steps"

    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">CURRENT TITLE</div>
            <div class="metric-number" style="font-size:1.45rem;">
                {reward}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# MISSION PREFERENCES
# =========================================================

st.markdown(
    '<div class="section-heading">Find your next mission</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="muted">Tell us what you need today. Your mission should fit your life, not the other way around.</p>',
    unsafe_allow_html=True,
)

left, right = st.columns(2)

with left:
    mood = st.selectbox(
        "How are you feeling?",
        [
            "Stressed",
            "Overwhelmed",
            "Low energy",
            "Restless",
            "Curious",
            "Motivated",
            "Just need a reset",
        ],
    )

    energy = st.slider(
        "Your energy level",
        min_value=1,
        max_value=5,
        value=3,
        help="1 means very low energy; 5 means lots of energy.",
    )

    minutes = st.select_slider(
        "How much time do you have?",
        options=[5, 10, 15, 20, 30, 45, 60],
        value=15,
        format_func=lambda x: f"{x} minutes",
    )

with right:
    goal = st.selectbox(
        "What would you like to focus on?",
        [
            "Feel calmer",
            "Move a little",
            "Connect with nature",
            "Help my community",
            "Learn about the environment",
            "Build a better routine",
        ],
    )

    access = st.selectbox(
        "What access do you have today?",
        [
            "I can step outside near home",
            "I have access to a park or green space",
            "I can only use a balcony or doorway",
            "I cannot go outside right now",
            "I have limited mobility or accessibility needs",
        ],
    )



st.markdown("#### Make it yours")
preference_col1, preference_col2, preference_col3 = st.columns(3)
with preference_col1:
    interests = st.selectbox("What kinds of activities do you prefer?", ["Any activity", "Mindful observation", "Gentle movement", "Gardening and plants", "Community care", "Learning and nature facts", "Photography or creativity", "Quiet time"])
with preference_col2:
    resources = st.selectbox("What can you use today?", ["No special resources", "Phone only", "Notebook or pen", "A plant or garden", "A nearby public green space", "Household items already available"])
with preference_col3:
    accessibility = st.selectbox("Anything to accommodate?", ["No additional needs", "Seated or low-movement activity", "Wheelchair / mobility access", "Sensory-friendly and quiet", "Indoor-only alternative", "Avoid heat / direct sun"])

NATURE_FACTS = [
    ("🌱 Plants can help cool their surroundings.", "Shade and water released by plants can influence local temperatures; effects vary by plant, weather, and setting."),
    ("🐝 Pollinators do more than visit flowers.", "Bees, butterflies, moths, birds, and other animals help many flowering plants reproduce."),
    ("🌳 Trees support living communities.", "Trees can provide habitat, shade, and food for wildlife, while roots can help stabilize soil."),
    ("☁️ Clouds are part of the water cycle.", "Water evaporates, condenses into clouds, and can return to the surface as precipitation."),
    ("🍂 Fallen leaves have a role.", "As leaves break down, their nutrients can return to soil and support decomposers."),
    ("🌿 Small observations build nature awareness.", "Noticing the same spot over time can help you observe seasonal and weather-related changes."),
]
if "nature_fact_index" not in st.session_state:
    st.session_state.nature_fact_index = random.randrange(len(NATURE_FACTS))
fact_title, fact_body = NATURE_FACTS[st.session_state.nature_fact_index]
st.markdown(
    f"""
    <div class="glass-card" style="margin:.9rem 0 1rem; border-left:4px solid #a8f0ce;">
        <div class="metric-label">🌿 A LITTLE NATURE FACT</div>
        <div style="font-size:1.05rem;font-weight:800;margin:.35rem 0;">{html.escape(str(fact_title))}</div>
        <div style="line-height:1.55;">{html.escape(str(fact_body))}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
if st.button("🌱 Show another fun fact", key="next_nature_fact"):
    st.session_state.nature_fact_index = (st.session_state.nature_fact_index + 1) % len(NATURE_FACTS)
    st.rerun()

use_temporal = st.checkbox(
    "Use Temporal retry workflow (requires Temporal server and worker)",
    value=False,
    help="Generation and validation run as retryable Temporal activities. "
         "If Temporal is unavailable, the app falls back to local Ollama.",
)

if st.button("✨ Create My Mission", type="primary", use_container_width=True):
    with st.spinner("Finding a mission that fits your day..."):
        mission = None
        used_ai = False
        preferences = {
            "mood": mood,
            "energy": energy,
            "minutes": minutes,
            "goal": goal,
            "access": access,
            "model": MODEL,
            "interests": interests,
            "resources": resources,
            "accessibility": accessibility,
        }

        if use_temporal:
            try:
                temporal_result = asyncio.run(run_temporal_mission(preferences))
                mission = validate_mission(temporal_result.get("mission"), goal)
                used_ai = bool(temporal_result.get("used_ai", True))
                st.success("Mission generated and validated through Temporal.")
            except Exception as error:
                st.warning(
                    "Temporal was unavailable or the workflow failed. "
                    "Trying direct AI generation instead. If that is unavailable, "
                    "Fresh Air will provide a ready-to-go mission."
                )

        if mission is None:
            mission, used_ai = generate_mission(
                mood, energy, minutes, goal, access, interests, resources, accessibility
            )

        st.session_state.mission = mission
        st.session_state.current_mission_id = str(uuid.uuid4())
        st.session_state.mission_completed = False
        st.session_state.mission_number += 1
        st.session_state.last_inputs = preferences
        st.session_state.mission_used_ai = used_ai
        # Rerun so the newly generated mission renders directly below the Create My Mission button.
        st.rerun()

# Voice feature: read the current mission aloud
st.caption(
    "🔊 Voice uses ElevenLabs. "
    "Mission text is sent to an external service "
    "when you request audio."
)

if st.button("🎧 Listen to My Mission"):
    mission = st.session_state.get("mission")

    if mission:
        # Build a readable narration from the mission fields.
        narration_parts = []

        if mission.get("title"):
            narration_parts.append(mission["title"])

        if mission.get("description"):
            narration_parts.append(mission["description"])

        steps = mission.get("steps", [])

        if steps:
            narration_parts.append("Here are your steps.")

            for index, step in enumerate(steps, start=1):
                if isinstance(step, dict):
                    step_text = step.get("text", str(step))
                else:
                    step_text = str(step)

                narration_parts.append(
                    f"Step {index}. {step_text}"
                )

        narration = ". ".join(narration_parts)

        try:
            with st.spinner("Creating your audio..."):
                audio_bytes = generate_mission_audio(narration)

            st.audio(audio_bytes, format="audio/mpeg")
            st.success("Your mission is ready to listen to!")

        except Exception as error:
            st.error(
                "Could not generate audio. Check the ElevenLabs key, service status, "
                "and account usage limits, then try again."
            )
    else:
        st.warning("Generate a mission before listening.")


# =========================================================
# CURRENT MISSION
# =========================================================

if st.session_state.mission:
    mission = st.session_state.mission

    st.markdown("---")
    st.markdown(
        '<div class="section-heading">Your mission</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("mission_used_ai", False):
        st.caption(
            "Using a ready-to-go mission right now. Your local AI can be "
            "connected for more personalized missions."
        )

    safe_mission_title = html.escape(str(mission.get("title", "Your mission")))
    safe_mission_description = html.escape(str(mission.get("description", "")))
    safe_mission_impact = html.escape(str(mission.get("impact", "")))

    st.markdown(
        f"""
        <style>
        .mission-rainbow-card {{
            padding: 1.35rem 1.45rem;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,.28);
            background: linear-gradient(115deg,
                rgba(25,105,92,.96), rgba(55,91,138,.96),
                rgba(119,81,137,.96), rgba(25,105,92,.96));
            background-size: 300% 300%;
            animation: missionRainbowShift 10s ease infinite;
            box-shadow: 0 12px 32px rgba(0,0,0,.20);
            color: #fff;
            margin: .6rem 0 1rem;
        }}
        .mission-rainbow-card .mission-label {{
            color: #d8ffe9; font-size: .72rem; letter-spacing: .15em;
            font-weight: 800; text-transform: uppercase;
        }}
        .mission-rainbow-card .mission-title {{
            color: #fff; font-size: 1.55rem; line-height: 1.25;
            font-weight: 850; margin: .35rem 0 .7rem;
        }}
        .mission-rainbow-card .mission-description {{
            color: #f3fbf8; font-size: 1rem; line-height: 1.6;
        }}
        @keyframes missionRainbowShift {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            .mission-rainbow-card {{ animation: none; }}
        }}
        </style>
        <div class="mission-rainbow-card">
            <div class="mission-label">YOUR NEXT SMALL WIN</div>
            <div class="mission-title">{safe_mission_title}</div>
            <div class="mission-description">{safe_mission_description}</div>
            <br>
            <div class="mission-label">WHY IT MATTERS</div>
            <div class="mission-description">{safe_mission_impact}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Your steps")

    for i, step in enumerate(mission["steps"], start=1):
        safe_step = html.escape(str(step))
        st.markdown(
            f"""
            <div class="step-item">
                <strong style="color:#a8f0ce;">{i:02d}</strong>
                &nbsp;&nbsp; {safe_step}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("")

    complete_col, another_col = st.columns(2)

    with complete_col:
        if st.button(
            f"✅ Complete Mission (+{mission['points']} points)",
            type="primary",
            use_container_width=True,
        ):
            mission_id = st.session_state.current_mission_id or str(uuid.uuid4())
            st.session_state.current_mission_id = mission_id
            awarded_points = max(5, min(50, int(mission.get("points", 20))))

            # Avoid awarding points twice for the same mission ID.
            completed_ids = st.session_state.completed_mission_ids
            if mission_id not in completed_ids:
                st.session_state.points += awarded_points
                st.session_state.completed.append(
                    {
                        "title": mission["title"],
                        "points": awarded_points,
                        "goal": mission.get("goal", "General"),
                    }
                )
                completed_ids.append(mission_id)

            save_completed_mission(
                mission_id=mission_id,
                title=str(mission.get("title", "Outdoor Mission")),
                activity=str(mission.get("activity", mission.get("goal", mission.get("title", "Outdoor activity")))),
                preferences=st.session_state.get("last_inputs", {}),
                points=awarded_points,
                duration_minutes=int(st.session_state.get("last_inputs", {}).get("minutes", 0)),
            )
            st.session_state.mission_completed = True
            st.success("Mission added to your session journal.")

            st.session_state.last_completed_points = awarded_points
            st.session_state.last_completed_duration = int(st.session_state.get("last_inputs", {}).get("minutes", 0))
            st.session_state.mission = None
            st.success(
                f"Mission completed! You earned {awarded_points} points."
            )
            st.rerun()

    with another_col:
        if st.button("🔄 Try Another Mission", use_container_width=True):
            st.session_state.mission = None
            st.rerun()




# =========================================================
# REWARDS
# =========================================================

st.markdown("---")
st.markdown(
    '<div class="section-heading">Your journey</div>',
    unsafe_allow_html=True,
)
st.caption(f"Across saved missions, you have logged approximately {persistent_minutes} minutes of planned outdoor or nature-focused time. This is based on mission duration, not a verified measurement of time spent outside.")

reward_levels = [
    ("First Steps", 0),
    ("Green Explorer", 40),
    ("Nature Champion", 100),
    ("Earth Guardian", 200),
]

for title, threshold in reward_levels:
    earned = persistent_points >= threshold
    symbol = "🌿" if earned else "🔒"
    status = "Unlocked" if earned else f"{threshold} points needed"

    st.markdown(
        f"""
        <div class="glass-card"
             style="padding:0.9rem 1.1rem; margin-bottom:0.65rem;">
            <div style="display:flex; justify-content:space-between;
                        align-items:center; gap:1rem;">
                <div style="font-weight:700; color:white;">
                    {symbol} &nbsp; {title}
                </div>
                <div style="color:#a8f0ce; font-size:0.85rem;">
                    {status}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# MISSION HISTORY
# =========================================================

if st.session_state.completed:
    st.markdown("---")
    st.markdown(
        '<div class="section-heading">Completed missions</div>',
        unsafe_allow_html=True,
    )

    for item in reversed(st.session_state.completed):
        safe_completed_title = html.escape(str(item.get("title", "Outdoor Mission")))
        safe_completed_points = max(0, min(10000, int(item.get("points", 0))))
        st.markdown(
            f"""
            <div class="glass-card"
                 style="padding:0.9rem 1.1rem;">
                <div style="font-weight:700; color:white;">
                    ✓ {safe_completed_title}
                </div>
                <div style="color:#a8f0ce; font-size:0.85rem;">
                    +{item["points"]} points
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# =========================================================
# SESSION MISSION JOURNAL (NO CLOUD DATABASE)
# =========================================================

st.markdown("---")
st.markdown(
    '<div class="section-heading">📖 My Mission Journal</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Your completed missions and optional feedback are kept in this active "
    "Streamlit session only. They are not uploaded to a database and may not "
    "be available after the session ends."
)

journal = get_mission_history(limit=30)
st.metric("Missions in this session's journal", len(st.session_state.get("journal", [])))

if not journal:
    st.info("Your session journal is empty. Complete a mission to begin.")
else:
    saved_interests = [
        entry.get("preferences", {}).get("interests")
        for entry in journal
        if entry.get("preferences", {}).get("interests")
        and entry.get("preferences", {}).get("interests") != "Any activity"
    ]
    saved_goals = [
        entry.get("preferences", {}).get("goal")
        for entry in journal
        if entry.get("preferences", {}).get("goal")
    ]
    if saved_interests or saved_goals:
        from collections import Counter
        preference_col, goal_col = st.columns(2)
        if saved_interests:
            with preference_col:
                st.caption("Most common activity preference")
                st.write(Counter(saved_interests).most_common(1)[0][0])
        if saved_goals:
            with goal_col:
                st.caption("Most common mission goal")
                st.write(Counter(saved_goals).most_common(1)[0][0])

    for entry in journal:
        with st.container(border=True):
            st.subheader(entry.get("title", "Outdoor Mission"))
            st.caption("Activity: " + str(entry.get("activity", "Outdoor activity")))
            completed_at = entry.get("completed_at")
            if completed_at:
                if getattr(completed_at, "tzinfo", None) is not None:
                    completed_label = completed_at.strftime("%b %d, %Y at %I:%M %p UTC")
                else:
                    completed_label = completed_at.strftime("%b %d, %Y at %I:%M %p")
                st.caption("Completed: " + completed_label)
            if entry.get("feedback"):
                st.write("Your feedback: " + str(entry["feedback"]))

if st.session_state.get("mission_completed") and st.session_state.get("current_mission_id"):
    feedback_choice = st.radio(
        "How did you feel about your last completed mission?",
        ["No feedback", "Enjoyed it", "It was okay", "Didn't enjoy it"],
        key="journal_feedback_choice",
    )
    if st.button("Save Mission Feedback"):
        current_id = st.session_state.get("current_mission_id")
        for entry in st.session_state.get("journal", []):
            if entry.get("mission_id") == current_id:
                entry["feedback"] = None if feedback_choice == "No feedback" else feedback_choice
                break
        st.success("Feedback saved to this session's journal.")
        st.rerun()

# =========================================================
# FOOTER
# =========================================================

st.markdown(
    """
    <div style="
        text-align:center;
        padding:1.5rem 0 0.5rem;
        color:#d0e9df;
    ">
        <div style="font-size:1.4rem;">🌍 🌿 🌊 🏔️</div>
        <p style="font-size:0.82rem;">
            Small actions. Real places. A better connection with the world.
        </p>
        <p style="font-size:0.72rem; opacity:0.8;">
            Fresh Air is a prototype for outdoor engagement and community action.
            It does not diagnose or treat mental health conditions. Mission ideas use Ollama;
            mission history is session-only; optional voice and place search use ElevenLabs and SerpApi.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
# =========================================================
# FIND SOMEWHERE TO GO
# =========================================================

st.divider()

st.header("📍 Find Somewhere to Go")

st.write(
    "Turn your mission into a real destination when going somewhere works for you. "
    "Enter a city or neighborhood to discover places to visit."
)

with st.form("outdoor_destination_form"):
    destination_location = st.text_input(
        "City or neighborhood",
        placeholder="e.g., Miami, Florida",
    )

    available_minutes = st.selectbox(
        "How much time do you have?",
        [10, 20, 30, 45, 60],
        index=1,
        format_func=lambda n: f"{n} minutes",
    )

    search_destinations = st.form_submit_button(
        "Find Somewhere to Go"
    )

if search_destinations:
    if not destination_location.strip():
        st.warning("Please enter a city or neighborhood.")

    else:
        try:
            with st.spinner("Finding outdoor destinations..."):
                places = find_outdoor_destinations(
                    destination_location.strip(),
                    available_minutes,
                )

            if not places:
                st.info(
                    "No places were returned. Try a nearby "
                    "city or a more specific search."
                )

            else:
                st.subheader("Outdoor destinations to explore")

                st.caption(
                    f"You selected {available_minutes} minutes. "
                    "Check travel time, opening hours, and access "
                    "before choosing a destination."
                )

                for place in places:
                    name = place.get("title", "Outdoor destination")
                    address = place.get("address", "Address unavailable")
                    rating = place.get("rating")
                    open_state = place.get("open_state")
                    description = place.get("description")
                    links = place.get("links") or {}

                    # Prefer an available direct place link.
                    place_url = (
                        place.get("link")
                        or links.get("website")
                        or links.get("directions")
                    )

                    with st.container(border=True):
                        st.subheader(name)
                        st.write(address)

                        if rating is not None:
                            st.write(f"⭐ Rating: {rating}")

                        if open_state:
                            st.write(f"Hours/status: {open_state}")

                        if description:
                            st.write(description)

                        if isinstance(place_url, str) and place_url.startswith(("https://", "http://")):
                            st.link_button(
                                "View destination and verify details",
                                place_url,
                                use_container_width=True,
                            )

                        st.caption(
                            "Verify the destination, access, and "
                            "current conditions before visiting."
                        )

        except Exception as error:
            st.error(
                "Destination search failed. Check the SerpApi key, connection, "
                "and available search quota, then try again."
            )
            st.info(
                "Check your internet connection, SerpApi key, "
                "and remaining API searches."
            )
