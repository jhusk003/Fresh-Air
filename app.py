import asyncio
import json
import os
import random
import requests
import uuid
from datetime import datetime, timezone

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def find_outdoor_destinations(location, minutes):
    """Search for real outdoor places using SerpApi."""

    api_key = os.getenv("SERPAPI_API_KEY")

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
        timeout=30,
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

    api_key = os.getenv("ELEVENLABS_API_KEY")

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
        timeout=60,
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
        options=[os.getenv("OLLAMA_MODEL", "llama3.2:1b"), "llama3.2:1b", "gemma2:2b"],
        index=0,
        help="Choose a model available on the Ollama server configured for this deployment.",
    )
    st.caption(
        "Mission generation uses the Ollama server in OLLAMA_URL. For a cloud deployment, "
        "that must be a reachable hosted Ollama endpoint; localhost refers to the app container. "
        "Audio and destination search use external services only when requested."
    )

MODEL = selected_model
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_URL = OLLAMA_BASE_URL if OLLAMA_BASE_URL.endswith("/api/generate") else f"{OLLAMA_BASE_URL}/api/generate"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

# =========================================================
# ANIMATED ENVIRONMENTAL BACKGROUND
# =========================================================

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

    /* Keep the animated scenery behind all app content */
    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background:
            linear-gradient(
                180deg,
                rgba(5, 22, 33, 0.35),
                rgba(5, 22, 33, 0.60)
            ),
            linear-gradient(
                90deg,
                rgba(8, 30, 36, 0.35),
                transparent 60%
            );
    }

    .stApp::after {
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        opacity: 0.8;
        background:
            radial-gradient(
                ellipse at 80% 15%,
                rgba(255, 220, 155, 0.18),
                transparent 35%
            ),
            radial-gradient(
                ellipse at 10% 75%,
                rgba(94, 211, 173, 0.15),
                transparent 40%
            );
    }

    /* Animated scene behind the app */
    .environment {
        position: fixed;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        pointer-events: none;
        background: linear-gradient(
            180deg,
            #497f91 0%,
            #8cb9ba 48%,
            #274f56 100%
        );
        animation: skyCycle 32s infinite;
    }

    .sun {
        position: absolute;
        width: 105px;
        height: 105px;
        top: 11%;
        right: 15%;
        border-radius: 50%;
        background: rgba(255, 230, 171, 0.88);
        box-shadow: 0 0 70px rgba(255, 223, 153, 0.4);
        animation: sunGlow 5s ease-in-out infinite alternate;
    }

    .cloud {
        position: absolute;
        top: 16%;
        left: -30%;
        width: 180px;
        height: 38px;
        border-radius: 50px;
        background: rgba(255,255,255,0.26);
        filter: blur(2px);
        animation: cloudMove 38s linear infinite;
    }

    .cloud::before,
    .cloud::after {
        content: "";
        position: absolute;
        border-radius: 50%;
        background: inherit;
    }

    .cloud::before {
        width: 65px;
        height: 65px;
        left: 28px;
        top: -30px;
    }

    .cloud::after {
        width: 85px;
        height: 75px;
        right: 25px;
        top: -40px;
    }

    .cloud.two {
        top: 28%;
        animation-duration: 52s;
        animation-delay: -18s;
        transform: scale(0.7);
        opacity: 0.65;
    }

    .mountain {
        position: absolute;
        bottom: 0;
        width: 0;
        height: 0;
        border-left: 35vw solid transparent;
        border-right: 35vw solid transparent;
        border-bottom: 52vh solid #335c59;
        left: -12%;
        animation: mountainCycle 32s infinite;
    }

    .mountain.back {
        left: 32%;
        border-left-width: 29vw;
        border-right-width: 29vw;
        border-bottom-width: 43vh;
        border-bottom-color: #47766d;
        opacity: 0.85;
    }

    .mountain.front {
        left: 52%;
        border-left-width: 34vw;
        border-right-width: 34vw;
        border-bottom-width: 35vh;
        border-bottom-color: #203f43;
    }

    .glacier {
        position: absolute;
        inset: 42% -10% 0;
        opacity: 0;
        background:
            linear-gradient(
                135deg,
                transparent 0 27%,
                rgba(225, 249, 251, 0.85) 27.2% 35%,
                transparent 35.2% 42%,
                rgba(181, 229, 239, 0.85) 42.2% 50%,
                transparent 50.2%
            ),
            linear-gradient(
                180deg,
                #a8dbe4 0%,
                #5e9ba9 50%,
                #285666 100%
            );
        clip-path: polygon(
            0 45%, 13% 20%, 25% 38%, 40% 0,
            53% 31%, 66% 8%, 78% 37%, 91% 16%,
            100% 40%, 100% 100%, 0 100%
        );
        animation: glacierCycle 32s infinite;
    }

    .forest {
        position: absolute;
        inset: 48% 0 0;
        opacity: 0;
        background:
            repeating-linear-gradient(
                90deg,
                transparent 0 25px,
                rgba(13, 53, 43, 0.9) 26px 40px,
                transparent 41px 65px
            ),
            linear-gradient(180deg, #477c63, #163e37);
        clip-path: polygon(
            0 35%, 5% 10%, 10% 42%, 15% 5%,
            22% 44%, 28% 0, 35% 39%, 42% 9%,
            50% 45%, 58% 0, 65% 42%, 73% 8%,
            80% 40%, 89% 2%, 96% 42%, 100% 18%,
            100% 100%, 0 100%
        );
        animation: forestCycle 32s infinite;
    }

    .waves {
        position: absolute;
        bottom: -5%;
        left: -10%;
        width: 120%;
        height: 42%;
        border-radius: 48% 52% 0 0;
        background: linear-gradient(
            180deg,
            rgba(80, 179, 183, 0.85),
            rgba(20, 85, 105, 0.98)
        );
        opacity: 0;
        animation: waveCycle 32s infinite;
    }

    .waves.second {
        bottom: -12%;
        height: 34%;
        left: -20%;
        background: linear-gradient(
            180deg,
            rgba(139, 220, 206, 0.65),
            rgba(31, 106, 122, 0.95)
        );
        animation: waveCycle 32s infinite, waveMove 7s ease-in-out infinite;
    }

    @keyframes skyCycle {
        0%, 24% {
            background: linear-gradient(180deg, #477f96, #9bc7c6 55%, #345d5c);
        }
        25%, 49% {
            background: linear-gradient(180deg, #8dbac9, #d5e8e9 55%, #628c99);
        }
        50%, 74% {
            background: linear-gradient(180deg, #426c87, #93b5c3 55%, #3e727a);
        }
        75%, 100% {
            background: linear-gradient(180deg, #254f55, #659b88 55%, #183d37);
        }
    }

    @keyframes mountainCycle {
        0%, 24% { opacity: 1; }
        25%, 49% { opacity: 0.12; }
        50%, 74% { opacity: 0.75; }
        75%, 100% { opacity: 0.35; }
    }

    @keyframes glacierCycle {
        0%, 24% { opacity: 0; }
        25%, 49% { opacity: 0.92; }
        50%, 100% { opacity: 0; }
    }

    @keyframes forestCycle {
        0%, 74% { opacity: 0; }
        75%, 100% { opacity: 0.9; }
    }

    @keyframes waveCycle {
        0%, 49% { opacity: 0; }
        50%, 74% { opacity: 0.95; }
        75%, 100% { opacity: 0; }
    }

    @keyframes waveMove {
        0%, 100% { transform: translateX(-2%) rotate(-2deg); }
        50% { transform: translateX(2%) rotate(2deg); }
    }

    @keyframes cloudMove {
        from { left: -30%; }
        to { left: 120%; }
    }

    @keyframes sunGlow {
        from { transform: scale(0.96); opacity: 0.8; }
        to { transform: scale(1.04); opacity: 1; }
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
        .waves {
            animation: none !important;
        }
    }
    </style>

    <div class="environment">
        <div class="sun"></div>
        <div class="cloud"></div>
        <div class="cloud two"></div>
        <div class="mountain"></div>
        <div class="mountain back"></div>
        <div class="mountain front"></div>
        <div class="glacier"></div>
        <div class="forest"></div>
        <div class="waves"></div>
        <div class="waves second"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
    return mission


def get_disliked_activities():
    """Return activities disliked earlier in this Streamlit session."""
    return {
        str(entry.get("activity"))
        for entry in st.session_state.get("journal", [])
        if entry.get("feedback") == "Didn't enjoy it" and entry.get("activity")
    }


def generate_mission(mood, energy, minutes, goal, access, interests="Any activity", resources="No special resources", accessibility="No additional needs"):
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
- Never recommend trespassing, entering dangerous areas, touching hazardous waste,
  disturbing wildlife, damaging plants, or approaching unsafe water or roads.
- Do not claim that an environmental impact has been measured.
- Keep instructions practical, welcoming, and accessible.
- Return ONLY valid JSON. Do not use Markdown.

Use exactly this JSON structure:
{{
  "title": "Short mission title",
  "description": "Two short sentences explaining the mission",
  "steps": [
    "First step",
    "Second step",
    "Third step"
  ],
  "points": 20,
  "impact": "A realistic explanation of the possible benefit",
  "activity": "Short activity category/name",
  "alternative": "A realistic no-cost alternative if the original is impractical"
}}
"""

    if disliked:
        prompt += (
            "\nAvoid these activities where possible because they were "
            "previously disliked: "
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
                "options": {"temperature": 0.8},
            },
            timeout=90,
        )
        response.raise_for_status()

        result = response.json()
        raw_text = result.get("response", "")
        mission = json.loads(raw_text)

        if not all(
            key in mission
            for key in ["title", "description", "steps", "points", "impact"]
        ):
            raise ValueError("The AI response is missing required fields.")

        if not isinstance(mission["steps"], list):
            raise ValueError("Mission steps must be a list.")

        mission["points"] = max(
            5, min(50, int(mission["points"]))
        )
        mission["goal"] = goal
        mission.setdefault("activity", mission.get("title", goal))
        mission.setdefault("alternative", "If this does not fit today, spend five minutes noticing nature from a safe, accessible place or window.")
        return mission, True

    except Exception:
        mission = make_fallback_mission(goal)
        mission.setdefault("activity", mission.get("title", goal))
        mission.setdefault("alternative", "If this does not fit today, observe the sky, a plant, or natural light from a safe indoor spot for five minutes.")
        return mission, False

async def run_temporal_mission(preferences):
    """Run mission generation and validation through a local Temporal worker."""
    from temporalio.client import Client
    from temporal_workflow import MoodDividendWorkflow

    client = await asyncio.wait_for(
        Client.connect(os.getenv("TEMPORAL_ADDRESS", "localhost:7233")),
        timeout=4,
    )
    return await client.execute_workflow(
        MoodDividendWorkflow.run,
        preferences,
        id=f"mood-mission-{uuid.uuid4()}",
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "fresh-air-queue"),
    )


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
                f"Could not generate audio: {error}"
            )
    else:
        st.warning("Generate a mission before listening.")


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
with st.expander("🌿 Nature Facts — a tiny curiosity break", expanded=False):
    fact_title, fact_body = NATURE_FACTS[st.session_state.nature_fact_index]
    st.markdown(f"**{fact_title}**")
    st.write(fact_body)
    if st.button("Show another nature fact", key="next_nature_fact"):
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
                mission = temporal_result["mission"]
                used_ai = bool(temporal_result.get("used_ai", True))
                st.success("Mission generated and validated through Temporal.")
            except Exception as error:
                st.warning(
                    "Temporal was unavailable or the workflow failed. "
                    "Trying direct local Ollama generation instead. "
                    f"Details: {error}"
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

    st.markdown(
        f"""
        <div class="glass-card">
            <div class="mission-label">YOUR NEXT SMALL WIN</div>
            <div class="mission-title">{mission["title"]}</div>
            <div class="mission-description">{mission["description"]}</div>
            <br>
            <div class="mission-label">WHY IT MATTERS</div>
            <div class="mission-description">{mission["impact"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Your steps")

    for i, step in enumerate(mission["steps"], start=1):
        st.markdown(
            f"""
            <div class="step-item">
                <strong style="color:#a8f0ce;">{i:02d}</strong>
                &nbsp;&nbsp; {step}
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

            # Avoid awarding points twice for the same mission ID.
            completed_ids = st.session_state.completed_mission_ids
            if mission_id not in completed_ids:
                st.session_state.points += mission["points"]
                st.session_state.completed.append(
                    {
                        "title": mission["title"],
                        "points": mission["points"],
                        "goal": mission.get("goal", "General"),
                    }
                )
                completed_ids.append(mission_id)

            save_completed_mission(
                mission_id=mission_id,
                title=str(mission.get("title", "Outdoor Mission")),
                activity=str(mission.get("activity", mission.get("goal", mission.get("title", "Outdoor activity")))),
                preferences=st.session_state.get("last_inputs", {}),
                points=int(mission.get("points", 0)),
                duration_minutes=int(st.session_state.get("last_inputs", {}).get("minutes", 0)),
            )
            st.session_state.mission_completed = True
            st.success("Mission added to your session journal.")

            st.session_state.last_completed_points = int(mission.get("points", 0))
            st.session_state.last_completed_duration = int(st.session_state.get("last_inputs", {}).get("minutes", 0))
            st.session_state.mission = None
            st.success(
                f"Mission completed! You earned {mission['points']} points."
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
        st.markdown(
            f"""
            <div class="glass-card"
                 style="padding:0.9rem 1.1rem;">
                <div style="font-weight:700; color:white;">
                    ✓ {item["title"]}
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

                        if place_url:
                            st.markdown(
                                f"[View destination and verify details]"
                                f"({place_url})"
                            )

                        st.caption(
                            "Verify the destination, access, and "
                            "current conditions before visiting."
                        )

        except Exception as error:
            st.error(
                f"Destination search failed: {error}"
            )
            st.info(
                "Check your internet connection, SerpApi key, "
                "and remaining API searches."
            )
